"""System abstraction layer. Everything that touches the OS goes through here.
All commands use argument lists (never a shell) and every user value is validated."""
import json
import os
import re
import socket
import subprocess
import time

from .core import find_tool, normalize_mac, is_zero, MacError

IFACE_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,15}$")


class BackendError(Exception):
    pass


def valid_iface(name):
    return isinstance(name, str) and bool(IFACE_RE.match(name)) and not name.startswith("-")


class Result:
    def __init__(self, rc, out, err):
        self.rc, self.out, self.err = rc, out, err

    @property
    def ok(self):
        return self.rc == 0


def run(argv, timeout=10):
    """Run an argument list. Returns Result, never raises for command failures."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, LC_ALL="C", PATH=os.environ.get("PATH", "") + ":/usr/sbin:/sbin"))
        return Result(p.returncode, p.stdout, p.stderr)
    except FileNotFoundError:
        return Result(127, "", "command not found: %s" % argv[0])
    except subprocess.TimeoutExpired:
        return Result(124, "", "timed out after %ss: %s" % (timeout, " ".join(argv)))


class SystemBackend:
    """Real backend: macchanger + iproute2 + NetworkManager (when present)."""
    name = "system"

    def __init__(self, macchanger_path=None):
        self.macchanger = find_tool("macchanger", macchanger_path)
        self.ip = find_tool("ip")
        self.nmcli = find_tool("nmcli")
        self.iw = find_tool("iw")
        self.ping = find_tool("ping")

    # ---- discovery
    def macchanger_version(self):
        if not self.macchanger:
            return None
        r = run([self.macchanger, "--version"])
        first = (r.out or r.err).strip().splitlines()
        return first[0] if first else None

    def list_interfaces(self):
        base = "/sys/class/net"
        try:
            names = sorted(os.listdir(base))
        except OSError:
            return []
        return [n for n in names if n != "lo"]

    def iface_type(self, name):
        base = "/sys/class/net/%s" % name
        if os.path.isdir(base + "/wireless") or os.path.isdir(base + "/phy80211"):
            return "Wi-Fi"
        if os.path.isdir(base + "/bridge"):
            return "Bridge"
        try:
            with open(base + "/uevent") as f:
                dt = re.search(r"DEVTYPE=(\w+)", f.read())
            if dt:
                return {"wlan": "Wi-Fi", "bridge": "Bridge", "vlan": "VLAN", "bond": "Bond"}.get(dt.group(1), dt.group(1).capitalize())
        except OSError:
            pass
        if name.startswith(("veth", "docker", "br-", "virbr")):
            return "Virtual"
        if name.startswith("dummy"):
            return "Dummy"
        if name.startswith(("tun", "tap", "wg")):
            return "Tunnel"
        return "Ethernet"

    def current_mac(self, iface):
        self._check(iface)
        try:
            with open("/sys/class/net/%s/address" % iface) as f:
                return normalize_mac(f.read().strip())
        except (OSError, MacError) as e:
            raise BackendError("Cannot read MAC of %s: %s" % (iface, e))

    def permanent_mac(self, iface):
        """Hardware MAC if the driver exposes one, else None."""
        self._check(iface)
        if self.macchanger:
            r = run([self.macchanger, "-s", iface])
            m = re.search(r"Permanent MAC:\s+([0-9a-fA-F:]{17})", r.out)
            if m and not is_zero(m.group(1)):
                return normalize_mac(m.group(1))
        ethtool = find_tool("ethtool")
        if ethtool:
            r = run([ethtool, "-P", iface])
            m = re.search(r"Permanent address:\s+([0-9a-fA-F:]{17})", r.out)
            if m and not is_zero(m.group(1)):
                return normalize_mac(m.group(1))
        return None

    def link_info(self, iface):
        """Operstate, carrier, flags, addresses, gateway."""
        self._check(iface)
        info = {"state": "unknown", "up": False, "ipv4": [], "ipv6": [], "gateway": None,
                "dynamic4": False, "mtu": None}
        r = run([self.ip, "-j", "addr", "show", "dev", iface]) if self.ip else Result(127, "", "no ip")
        try:
            data = json.loads(r.out)[0]
            info["state"] = data.get("operstate", "UNKNOWN").lower()
            info["up"] = "UP" in data.get("flags", [])
            info["mtu"] = data.get("mtu")
            for a in data.get("addr_info", []):
                s = "%s/%s" % (a.get("local"), a.get("prefixlen"))
                if a.get("family") == "inet":
                    info["ipv4"].append(s)
                    if a.get("dynamic"):
                        info["dynamic4"] = True
                elif a.get("family") == "inet6" and not str(a.get("local", "")).startswith("fe80"):
                    info["ipv6"].append(s)
                elif a.get("family") == "inet6":
                    info.setdefault("ll6", s)
        except (ValueError, IndexError, KeyError):
            pass
        info["gateway"] = self.gateway(iface)
        return info

    def gateway(self, iface):
        r = run([self.ip, "-j", "route", "show", "default", "dev", iface]) if self.ip else Result(127, "", "")
        try:
            for rt in json.loads(r.out):
                if rt.get("gateway"):
                    return rt["gateway"]
        except ValueError:
            pass
        return None

    def routes(self, iface):
        r = run([self.ip, "route", "show", "dev", iface]) if self.ip else Result(127, "", "")
        return [l.strip() for l in r.out.splitlines() if l.strip()]

    def neighbors(self, iface):
        r = run([self.ip, "neigh", "show", "dev", iface]) if self.ip else Result(127, "", "")
        return [l.strip() for l in r.out.splitlines() if l.strip()]

    def wifi_info(self, iface):
        """SSID/BSSID/signal when the system exposes them, else None."""
        if self.iface_type(iface) != "Wi-Fi":
            return None
        out = {"ssid": None, "bssid": None, "signal": None}
        if self.iw:
            r = run([self.iw, "dev", iface, "link"])
            m = re.search(r"Connected to ([0-9a-fA-F:]{17})", r.out)
            if m:
                out["bssid"] = m.group(1).lower()
            m = re.search(r"SSID: (.+)", r.out)
            if m:
                out["ssid"] = m.group(1).strip()
            m = re.search(r"signal: (-?\d+) dBm", r.out)
            if m:
                out["signal"] = int(m.group(1))
        elif self.nmcli:
            r = run([self.nmcli, "-t", "-f", "ACTIVE,SSID,BSSID,SIGNAL", "dev", "wifi", "list", "ifname", iface])
            for line in r.out.splitlines():
                if line.startswith("yes:"):
                    parts = line.replace("\\:", "\x00").split(":")
                    out["ssid"] = parts[1]
                    out["bssid"] = parts[2].replace("\x00", ":").lower() if len(parts) > 2 else None
                    out["signal"] = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
        return out

    def nm_status(self, iface):
        if not self.nmcli:
            return "NetworkManager not installed"
        r = run([self.nmcli, "-t", "-f", "DEVICE,STATE,CONNECTION", "device"])
        if not r.ok:
            return "NetworkManager not running"
        for line in r.out.splitlines():
            p = line.split(":")
            if p and p[0] == iface:
                return "%s%s" % (p[1], " (%s)" % p[2] if len(p) > 2 and p[2] else "")
        return "not managed"

    def nm_connection(self, iface):
        if not self.nmcli:
            return None
        r = run([self.nmcli, "-t", "-f", "DEVICE,NAME", "connection", "show", "--active"])
        for line in r.out.splitlines():
            p = line.rsplit(":", 1) if False else line.split(":", 1)
            if p[0] == iface and len(p) > 1:
                return p[1]
        return None

    # ---- MAC changes (macchanger does the work)
    def _check(self, iface):
        if not valid_iface(iface):
            raise BackendError("Invalid interface name: %r" % (iface,))
        if not os.path.isdir("/sys/class/net/%s" % iface):
            raise BackendError("Interface %s does not exist" % iface)

    def _need_macchanger(self):
        if not self.macchanger:
            raise BackendError("macchanger is not installed. Install it with: sudo apt install macchanger")

    def _set_link(self, iface, up):
        r = run([self.ip, "link", "set", "dev", iface, "up" if up else "down"])
        if not r.ok:
            raise BackendError("ip link set %s %s failed: %s" % (iface, "up" if up else "down", r.err.strip()))

    def macchanger_apply(self, iface, mode, mac=None):
        """mode: random | set | permanent. Interface is taken down for the change and
        brought back up afterwards, even when macchanger fails."""
        self._check(iface)
        self._need_macchanger()
        if mode == "random":
            args = ["-r"]
        elif mode == "set":
            args = ["-m", normalize_mac(mac)]
        elif mode == "permanent":
            args = ["-p"]
        else:
            raise BackendError("Unknown mode %r" % mode)
        was_up = self.link_info(iface)["up"]
        if was_up:
            self._set_link(iface, False)
        try:
            r = run([self.macchanger] + args + [iface])
        finally:
            if was_up:
                run([self.ip, "link", "set", "dev", iface, "up"])
        if not r.ok:
            raise BackendError("macchanger failed: %s" % ((r.err or r.out).strip() or "exit %d" % r.rc))
        return r.out

    # ---- network actions
    def renew_dhcp(self, iface):
        self._check(iface)
        if self.nmcli:
            r = run([self.nmcli, "device", "reapply", iface], timeout=20)
            if r.ok:
                return "NetworkManager reapply"
            r = run([self.nmcli, "device", "reconnect", iface], timeout=30)
            if r.ok:
                return "NetworkManager reconnect"
        nw = find_tool("networkctl")
        if nw:
            r = run([nw, "renew", iface], timeout=20)
            if r.ok:
                return "systemd-networkd renew"
        dh = find_tool("dhclient")
        if dh:
            run([dh, "-r", iface], timeout=15)
            r = run([dh, iface], timeout=30)
            if r.ok:
                return "dhclient"
        raise BackendError("No supported DHCP client found to renew the lease")

    def ping_gateway(self, gw):
        if not self.ping or not gw:
            return None
        return run([self.ping, "-c", "1", "-W", "2", gw], timeout=5).ok

    def dns_ok(self, host="example.com"):
        try:
            socket.setdefaulttimeout(3)
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            return False

    def tcp_ok(self, host, port, family=socket.AF_INET, timeout=3):
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            return True
        except OSError:
            return False

    def internet_v4(self):
        return self.tcp_ok("1.1.1.1", 443)

    def internet_v6(self):
        return self.tcp_ok("2606:4700:4700::1111", 443, socket.AF_INET6)

    def nm_set_cloned_mac(self, iface, mac):
        """Persist a MAC in the NetworkManager connection profile. mac may be a MAC, 'permanent' or ''."""
        conn = self.nm_connection(iface)
        if not conn:
            raise BackendError("No active NetworkManager connection on %s" % iface)
        prop = "802-11-wireless.cloned-mac-address" if self.iface_type(iface) == "Wi-Fi" else "802-3-ethernet.cloned-mac-address"
        value = mac if mac in ("permanent", "") else normalize_mac(mac)
        r = run([self.nmcli, "connection", "modify", conn, prop, value])
        if not r.ok:
            raise BackendError("nmcli modify failed: %s" % r.err.strip())
        return conn, prop

    def now(self):
        return time.time()
