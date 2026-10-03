"""Pure helpers: MAC parsing, OUI lookup, environment detection. No side effects."""
import os
import platform
import random
import re
import shutil

VERSION = "1.0.0"
APP_NAME = "MAC-OUT"
TAGLINE = "MAC Address Management & Network Identity Observatory"

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2})([:\-]?)([0-9A-Fa-f]{2}(?:\2[0-9A-Fa-f]{2}){4})$")


class MacError(ValueError):
    pass


def normalize_mac(text):
    """Return aa:bb:cc:dd:ee:ff (lowercase) or raise MacError."""
    if not isinstance(text, str):
        raise MacError("MAC address must be text")
    t = text.strip()
    if re.fullmatch(r"[0-9A-Fa-f]{12}", t):
        t = ":".join(t[i:i + 2] for i in range(0, 12, 2))
    t = t.replace("-", ":")
    parts = t.split(":")
    if len(parts) != 6 or not all(re.fullmatch(r"[0-9A-Fa-f]{2}", p) for p in parts):
        raise MacError("Not a valid MAC address (expected six hex pairs like 02:11:22:33:44:55)")
    return ":".join(p.lower() for p in parts)


def is_valid_mac(text):
    try:
        normalize_mac(text)
        return True
    except MacError:
        return False


def _first_octet(mac):
    return int(normalize_mac(mac)[:2], 16)


def is_multicast(mac):
    return bool(_first_octet(mac) & 1)


def is_locally_administered(mac):
    return bool(_first_octet(mac) & 2)


def is_zero(mac):
    return normalize_mac(mac) == "00:00:00:00:00:00"


def oui_of(mac):
    return normalize_mac(mac)[:8].upper()


def random_local_mac(rng=random):
    """Random unicast, locally administered MAC."""
    first = (rng.randrange(256) | 0x02) & 0xFE
    rest = [rng.randrange(256) for _ in range(5)]
    return ":".join("%02x" % b for b in [first] + rest)


def mac_from_oui(oui, rng=random):
    parts = oui.replace("-", ":").split(":")
    if len(parts) != 3 or not all(re.fullmatch(r"[0-9A-Fa-f]{2}", p) for p in parts):
        raise MacError("OUI must look like AA:BB:CC")
    mac = ":".join(p.lower() for p in parts) + ":" + ":".join("%02x" % rng.randrange(256) for _ in range(3))
    if is_multicast(mac):
        raise MacError("That OUI is multicast and cannot be used for a normal interface")
    return mac


def mac_from_pattern(pattern, rng=random):
    """Pattern like 02:xx:xx:aa:xx:xx where x is a random hex digit."""
    p = pattern.strip().lower().replace("-", ":")
    parts = p.split(":")
    if len(parts) != 6 or not all(re.fullmatch(r"[0-9a-fx]{2}", q) for q in parts):
        raise MacError("Pattern needs six pairs of hex digits or x, e.g. 02:xx:xx:xx:xx:xx")
    out = "".join(c if c != "x" else "%x" % rng.randrange(16) for c in ":".join(parts))
    mac = normalize_mac(out)
    if is_multicast(mac):
        raise MacError("Pattern produces a multicast address (first byte must be even)")
    return mac


def describe_mac(mac, vendor_lookup=None):
    mac = normalize_mac(mac)
    vendor = vendor_lookup(mac) if vendor_lookup else None
    local = is_locally_administered(mac)
    return {
        "mac": mac,
        "cast": "Multicast" if is_multicast(mac) else "Unicast",
        "administration": "Locally administered" if local else "Globally unique (manufacturer assigned)",
        "oui": oui_of(mac),
        "vendor": vendor if (vendor and not local) else ("n/a (locally administered)" if local else "Unknown"),
    }


class OuiDatabase:
    """Vendor database read from local files only (no internet needed)."""
    CANDIDATES = ["/usr/share/macchanger/OUI.list", "/usr/share/ieee-data/oui.txt",
                  "/var/lib/ieee-data/oui.txt"]

    def __init__(self, path=None):
        self.map = {}
        self.path = None
        paths = [path] if path else ([os.environ["MACOUT_OUI"]] if os.environ.get("MACOUT_OUI") else self.CANDIDATES)
        for p in paths:
            if p and os.path.isfile(p):
                try:
                    self._load(p)
                    self.path = p
                    break
                except OSError:
                    continue

    def _load(self, p):
        with open(p, "r", errors="replace") as f:
            for line in f:
                m = re.match(r"^([0-9A-Fa-f]{2}) ([0-9A-Fa-f]{2}) ([0-9A-Fa-f]{2}) (.+)$", line)  # macchanger
                if m:
                    self.map["%s:%s:%s" % (m.group(1).upper(), m.group(2).upper(), m.group(3).upper())] = m.group(4).strip()
                    continue
                m = re.match(r"^([0-9A-Fa-f]{6})\s+\(base 16\)\s+(.+)$", line)  # ieee-data
                if m:
                    h = m.group(1).upper()
                    self.map["%s:%s:%s" % (h[0:2], h[2:4], h[4:6])] = m.group(2).strip()

    def __len__(self):
        return len(self.map)

    def lookup(self, mac):
        try:
            return self.map.get(oui_of(mac))
        except MacError:
            return None

    def search(self, text, limit=200):
        t = text.strip().lower()
        out = []
        for oui, name in self.map.items():
            if not t or t in name.lower() or t in oui.lower():
                out.append((oui, name))
        out.sort(key=lambda x: (x[1].lower(), x[0]))
        return out[:limit]

    def count_for(self, name):
        return sum(1 for v in self.map.values() if v == name)


# ---------------------------------------------------------------- environment
EXTRA_PATHS = "/usr/sbin:/sbin:/usr/local/sbin:/usr/bin:/bin:/usr/local/bin"


def find_tool(name, override=None):
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        return override
    return shutil.which(name, path=os.environ.get("PATH", "") + ":" + EXTRA_PATHS)


def normalize_arch(machine):
    m = machine.lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("aarch64", "arm64", "armv8l"):
        return "aarch64"
    return m


def read_os_release(path="/etc/os-release"):
    info = {}
    try:
        with open(path) as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip().split("=", 1)
                    info[k] = v.strip('"')
    except OSError:
        pass
    return info


def detect_environment(macchanger_path=None):
    osr = read_os_release()
    env = {
        "arch_raw": platform.machine(),
        "arch": normalize_arch(platform.machine()),
        "kernel": platform.release(),
        "system": platform.system(),
        "distro": osr.get("PRETTY_NAME", "Unknown Linux"),
        "distro_id": osr.get("ID", ""),
        "distro_like": osr.get("ID_LIKE", ""),
        "root": hasattr(os, "geteuid") and os.geteuid() == 0,
        "tools": {t: find_tool(t, macchanger_path if t == "macchanger" else None)
                  for t in ("macchanger", "ip", "nmcli", "iw", "ping", "ethtool", "systemctl", "dhclient", "networkctl")},
    }
    env["debian_family"] = "debian" in (env["distro_id"] + " " + env["distro_like"]) or "ubuntu" in env["distro_id"]
    env["supported_arch"] = env["arch"] in ("x86_64", "aarch64")
    env["systemd"] = os.path.isdir("/run/systemd/system")
    env["network_manager"] = bool(env["tools"]["nmcli"])
    return env
