"""In-memory backend so core logic can be tested without touching a real interface."""
from macout_app.backend import BackendError, valid_iface
from macout_app.core import normalize_mac, random_local_mac


class MockBackend:
    name = "mock"
    macchanger = "/usr/bin/macchanger"

    def __init__(self):
        self.ifaces = {"wlan0": {"mac": "a4:83:e7:12:34:56", "perm": "a4:83:e7:12:34:56", "up": True, "type": "Wi-Fi"},
                       "eth0": {"mac": "00:1b:44:11:3a:b7", "perm": "00:1b:44:11:3a:b7", "up": True, "type": "Ethernet"}}
        self.fail_next = False
        self.lie_next = False
        self.calls = []
        self.dhcp_renewals = 0

    def macchanger_version(self):
        return "GNU MAC Changer 1.7.0 (mock)"

    def list_interfaces(self):
        return sorted(self.ifaces)

    def iface_type(self, n):
        return self.ifaces[n]["type"]

    def _i(self, n):
        if not valid_iface(n) or n not in self.ifaces:
            raise BackendError("Interface %s does not exist" % n)
        return self.ifaces[n]

    def current_mac(self, n):
        return self._i(n)["mac"]

    def permanent_mac(self, n):
        return self._i(n)["perm"]

    def link_info(self, n):
        i = self._i(n)
        return {"state": "up" if i["up"] else "down", "up": i["up"], "ipv4": ["192.168.1.42/24"] if i["up"] else [],
                "ipv6": [], "gateway": "192.168.1.1" if i["up"] else None, "dynamic4": True, "mtu": 1500}

    def routes(self, n):
        return []

    def neighbors(self, n):
        return []

    def wifi_info(self, n):
        return {"ssid": "HomeNet", "bssid": "aa:bb:cc:dd:ee:ff", "signal": -55} if self._i(n)["type"] == "Wi-Fi" else None

    def nm_status(self, n):
        return "connected (Home)"

    def nm_connection(self, n):
        return "Home"

    def macchanger_apply(self, n, mode, mac=None):
        i = self._i(n)
        self.calls.append((n, mode, mac))
        if self.fail_next:
            self.fail_next = False
            raise BackendError("macchanger failed: Operation not permitted")
        if mode == "random":
            new = random_local_mac()
        elif mode == "set":
            new = normalize_mac(mac)
        else:
            new = i["perm"]
        if self.lie_next:
            self.lie_next = False
            return "ok"  # claims success but MAC stays the same
        i["mac"] = new
        return "ok"

    def renew_dhcp(self, n):
        self.dhcp_renewals += 1
        return "mock"

    def ping_gateway(self, gw):
        return True

    def dns_ok(self, host="example.com"):
        return True

    def internet_v4(self):
        return True

    def internet_v6(self):
        return False

    def nm_set_cloned_mac(self, n, mac):
        self.calls.append(("nm", n, mac))
        return "Home", "802-11-wireless.cloned-mac-address"
