"""Application services: logging, history, profiles, MAC manager, rotation, observer,
diagnostics, sessions, persistence and reports. No GUI code in here."""
import csv
import io
import json
import os
import re
import threading
import time
import zipfile
import base64
import pkgutil
from datetime import datetime, timedelta

from . import core
from .core import MacError, normalize_mac
from .backend import BackendError, valid_iface

CATEGORIES = ["MAC", "NETWORK", "DHCP", "DNS", "ROUTING", "SYSTEM", "PROFILE", "ROTATION", "ERROR"]
LEVELS = ["ERROR", "WARNING", "INFO", "DEBUG", "TRACE"]
VERBOSITY = {"Errors only": "ERROR", "Normal": "INFO", "Detailed": "DEBUG", "Debug": "TRACE"}


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def data_dir():
    if os.environ.get("MACOUT_HOME"):
        d = os.environ["MACOUT_HOME"]
    elif hasattr(os, "geteuid") and os.geteuid() == 0:
        d = "/var/lib/macout"
    else:
        d = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "macout")
    for sub in ("", "profiles", "sessions", "logs", "reports"):
        os.makedirs(os.path.join(d, sub), mode=0o700, exist_ok=True)
    return d


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, obj):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


# ------------------------------------------------------------------ settings
DEFAULT_SETTINGS = {
    "theme": "system", "startup_page": "Dashboard", "notifications": True,
    "verbosity": "Normal", "log_retention_days": 30, "history_retention_days": 90,
    "redact_ip_local": True, "redact_ip_public": True, "redact_bssid": True, "redact_ssid": True,
    "redact_perm_mac": True, "redact_cur_mac": True, "include_system": False,
    "min_rotation_minutes": 1, "diag_interval_sec": 5, "macchanger_path": "", "debug": False,
    "reconnect_timeout_sec": 25, "first_run_done": False, "confirm_actions": True,
}


class Settings:
    def __init__(self, base):
        self.path = os.path.join(base, "settings.json")
        self.data = dict(DEFAULT_SETTINGS)
        self.data.update(_read_json(self.path, {}))

    def get(self, k):
        return self.data.get(k, DEFAULT_SETTINGS.get(k))

    def set(self, k, v):
        self.data[k] = v
        self.save()

    def save(self):
        _write_json(self.path, self.data)


# ------------------------------------------------------------------- logging
class EventLog:
    """Structured records: {time, epoch, level, category, message, iface, data}."""

    def __init__(self, base, settings=None):
        self.path = os.path.join(base, "logs", "macout.jsonl")
        self.settings = settings
        self.records = []
        self.listeners = []
        self.lock = threading.Lock()
        self.threshold = "INFO"
        if settings:
            self.threshold = VERBOSITY.get(settings.get("verbosity"), "INFO")

    def set_verbosity(self, name):
        self.threshold = VERBOSITY.get(name, "INFO")

    def emit(self, category, message, level="INFO", iface=None, **data):
        rec = {"time": ts(), "epoch": time.time(), "level": level, "category": category,
               "message": message, "iface": iface, "data": data}
        with self.lock:
            self.records.append(rec)
            if len(self.records) > 5000:
                self.records = self.records[-4000:]
            if LEVELS.index(level) <= LEVELS.index(self.threshold):
                try:
                    fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    with os.fdopen(fd, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                except OSError:
                    pass
            ls = list(self.listeners)
        for cb in ls:
            try:
                cb(rec)
            except Exception:
                pass
        return rec

    def visible(self, category=None, level=None):
        lim = LEVELS.index(level or self.threshold)
        with self.lock:
            return [r for r in self.records if LEVELS.index(r["level"]) <= lim and (not category or r["category"] == category)]

    def prune(self, days):
        cutoff = time.time() - days * 86400
        try:
            with open(self.path) as f:
                keep = [l for l in f if json.loads(l).get("epoch", 0) >= cutoff]
            with open(self.path, "w") as f:
                f.writelines(keep)
        except (OSError, ValueError):
            pass


# ------------------------------------------------------------------- history
class History:
    FIELDS = ["time", "iface", "old_mac", "new_mac", "profile", "operation", "result", "duration"]

    def __init__(self, base):
        self.path = os.path.join(base, "history.jsonl")
        self.lock = threading.Lock()

    def add(self, **rec):
        rec.setdefault("time", ts())
        rec["epoch"] = time.time()
        with self.lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def all(self):
        out = []
        try:
            with open(self.path) as f:
                for l in f:
                    try:
                        out.append(json.loads(l))
                    except ValueError:
                        pass
        except OSError:
            pass
        return out

    def query(self, days=None, text="", since=None, until=None):
        rows = self.all()
        if days:
            cut = time.time() - days * 86400
            rows = [r for r in rows if r.get("epoch", 0) >= cut]
        if since:
            rows = [r for r in rows if r.get("epoch", 0) >= since]
        if until:
            rows = [r for r in rows if r.get("epoch", 0) <= until]
        if text:
            t = text.lower()
            rows = [r for r in rows if t in json.dumps(r).lower()]
        return rows

    def prune(self, days):
        cut = time.time() - days * 86400
        keep = [r for r in self.all() if r.get("epoch", 0) >= cut]
        with self.lock:
            with open(self.path, "w") as f:
                for r in keep:
                    f.write(json.dumps(r) + "\n")

    def clear(self):
        with self.lock:
            open(self.path, "w").close()

    def to_csv(self, rows):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=self.FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        return buf.getvalue()


# ------------------------------------------------------------------ profiles
STRATEGIES = {"random": "Random (macchanger -r)", "vendor": "Vendor-specific", "local": "Locally administered",
              "pattern": "Custom pattern", "fixed": "Specific MAC", "permanent": "Restore permanent"}


def new_profile(name="New profile", **kw):
    p = {"name": name, "interface": "", "strategy": "random", "mac": "", "vendor_oui": "", "vendor_name": "",
         "pattern": "02:xx:xx:xx:xx:xx", "persistent": False,
         "rotation": {"enabled": False, "interval_min": 30, "on_wifi_reconnect": False, "on_nm_reconnect": False,
                      "on_iface_restart": False, "on_resume": False, "on_start": False},
         "reconnect": True, "diagnostics": True, "log_level": "Normal", "notes": ""}
    p.update(kw)
    return p


def validate_profile(p):
    errs = []
    if not str(p.get("name", "")).strip():
        errs.append("Profile needs a name")
    if p.get("interface") and not valid_iface(p["interface"]):
        errs.append("Invalid interface name")
    if p.get("strategy") not in STRATEGIES:
        errs.append("Unknown strategy")
    if p.get("strategy") == "fixed":
        try:
            m = normalize_mac(p.get("mac", ""))
            if core.is_multicast(m):
                errs.append("A multicast MAC cannot be used on an interface")
        except MacError as e:
            errs.append(str(e))
    if p.get("strategy") == "vendor":
        try:
            core.mac_from_oui(p.get("vendor_oui", ""))
        except MacError as e:
            errs.append(str(e))
    if p.get("strategy") == "pattern":
        try:
            core.mac_from_pattern(p.get("pattern", ""))
        except MacError as e:
            errs.append(str(e))
    try:
        if int(p.get("rotation", {}).get("interval_min", 30)) < 1:
            errs.append("Rotation interval must be at least 1 minute")
    except (TypeError, ValueError):
        errs.append("Rotation interval must be a number")
    return errs


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "profile"


class ProfileManager:
    PRESETS = [("Home", dict(strategy="permanent", notes="Use the real hardware MAC at home.")),
               ("Work", dict(strategy="local", notes="Locally administered MAC for work networks.")),
               ("Privacy", dict(strategy="random", rotation={"enabled": True, "interval_min": 30, "on_wifi_reconnect": True,
                                                              "on_nm_reconnect": False, "on_iface_restart": False,
                                                              "on_resume": True, "on_start": False},
                                notes="Random MAC, rotates every 30 minutes.")),
               ("Testing", dict(strategy="local", notes="Throw-away MAC for lab experiments."))]

    def __init__(self, base, log):
        self.dir = os.path.join(base, "profiles")
        self.state_path = os.path.join(base, "active_profiles.json")
        self.log = log
        if not os.listdir(self.dir):
            for n, kw in self.PRESETS:
                self.save(new_profile(n, **kw), quiet=True)

    def list(self):
        out = []
        for f in sorted(os.listdir(self.dir)):
            if f.endswith(".json"):
                p = _read_json(os.path.join(self.dir, f), None)
                if isinstance(p, dict) and "name" in p:
                    out.append(p)
        return out

    def get(self, name):
        for p in self.list():
            if p["name"] == name:
                return p

    def save(self, p, quiet=False):
        errs = validate_profile(p)
        if errs:
            raise ValueError("; ".join(errs))
        _write_json(os.path.join(self.dir, slug(p["name"]) + ".json"), p)
        if not quiet:
            self.log.emit("PROFILE", "Profile saved: %s" % p["name"])

    def delete(self, name):
        try:
            os.remove(os.path.join(self.dir, slug(name) + ".json"))
        except OSError:
            pass
        act = self.active_map()
        for k in [k for k, v in act.items() if v == name]:
            del act[k]
        _write_json(self.state_path, act)
        self.log.emit("PROFILE", "Profile deleted: %s" % name)

    def duplicate(self, name):
        p = self.get(name)
        if not p:
            raise ValueError("No such profile")
        q = json.loads(json.dumps(p))
        base = name + " copy"
        existing = {x["name"] for x in self.list()}
        n, i = base, 2
        while n in existing:
            n, i = "%s %d" % (base, i), i + 1
        q["name"] = n
        self.save(q)
        return q

    def export(self, name, path):
        p = self.get(name)
        if not p:
            raise ValueError("No such profile")
        _write_json(path, {"macout_profile": 1, "profile": p})

    def import_file(self, path):
        d = _read_json(path, None)
        if not isinstance(d, dict) or "profile" not in d:
            raise ValueError("Not a MAC-OUT profile file")
        p = new_profile()
        p.update(d["profile"])
        self.save(p)
        return p

    def active_map(self):
        return _read_json(self.state_path, {})

    def set_active(self, iface, name):
        m = self.active_map()
        if name:
            m[iface] = name
        else:
            m.pop(iface, None)
        _write_json(self.state_path, m)

    def active_for(self, iface):
        return self.active_map().get(iface)


# ------------------------------------------------------------------ observer
class Observer:
    def __init__(self, backend):
        self.b = backend

    def snapshot(self, iface, connectivity=False):
        b = self.b
        s = {"iface": iface, "time": ts(), "type": b.iface_type(iface), "mac": b.current_mac(iface)}
        s["permanent"] = b.permanent_mac(iface)
        s.update({k: v for k, v in b.link_info(iface).items()})
        s["wifi"] = b.wifi_info(iface)
        s["nm"] = b.nm_status(iface)
        s["dhcp"] = "Lease active" if s.get("dynamic4") else ("Static or unmanaged address" if s["ipv4"] else "No IPv4 address")
        s["association"] = ("Connected" if s["state"] in ("up", "unknown") and s["up"] and (s["ipv4"] or s["ipv6"])
                            else ("Link up, no address" if s["up"] else "Interface down"))
        if s["wifi"] is not None and not s["wifi"].get("bssid"):
            s["association"] = "Not associated" if s["up"] else "Interface down"
        if connectivity:
            s.update(self.connectivity(s))
        return s

    def connectivity(self, s):
        b = self.b
        r = {"gateway_reachable": b.ping_gateway(s.get("gateway")) if s.get("gateway") else None}
        r["dns"] = b.dns_ok()
        r["internet_v4"] = b.internet_v4()
        r["internet_v6"] = b.internet_v6() if s.get("ipv6") else None
        return r

    @staticmethod
    def health(s):
        if not s.get("up") or not s.get("ipv4") and not s.get("ipv6"):
            return "DOWN"
        if "dns" not in s:
            return "UNKNOWN"
        if s.get("dns") and s.get("internet_v4"):
            return "HEALTHY"
        if s.get("gateway_reachable") or s.get("internet_v4") or s.get("dns"):
            return "DEGRADED"
        return "DOWN"


# --------------------------------------------------------------- MAC manager
class MacManager:
    def __init__(self, backend, observer, log, history, profiles, settings, base):
        self.b, self.obs, self.log, self.hist, self.profiles, self.settings = backend, observer, log, history, profiles, settings
        self.oui = core.OuiDatabase()
        self.state_path = os.path.join(base, "originals.json")
        self.lock = threading.Lock()

    # remember the first MAC we ever saw, for interfaces with no readable permanent MAC
    def original_mac(self, iface):
        perm = self.b.permanent_mac(iface)
        if perm:
            return perm
        st = _read_json(self.state_path, {})
        return st.get(iface)

    def remember_original(self, iface):
        st = _read_json(self.state_path, {})
        if iface not in st:
            st[iface] = self.b.current_mac(iface)
            _write_json(self.state_path, st)

    def resolve_target(self, strategy, p):
        """Return ('random'|'permanent'|'set', mac or None)."""
        if strategy == "random":
            return "random", None
        if strategy == "permanent":
            return "permanent", None
        if strategy == "local":
            return "set", core.random_local_mac()
        if strategy == "vendor":
            return "set", core.mac_from_oui(p.get("vendor_oui", ""))
        if strategy == "pattern":
            return "set", core.mac_from_pattern(p.get("pattern", "02:xx:xx:xx:xx:xx"))
        if strategy == "fixed":
            m = normalize_mac(p.get("mac", ""))
            if core.is_multicast(m):
                raise MacError("A multicast MAC cannot be used on an interface")
            return "set", m
        raise MacError("Unknown strategy %r" % strategy)

    def apply(self, iface, strategy, p=None, profile=None, operation=None, reconnect=True, wait=None):
        """request -> execute -> verify -> report. Returns a result dict."""
        p = p or {}
        t0 = time.time()
        operation = operation or STRATEGIES.get(strategy, strategy)
        res = {"ok": False, "iface": iface, "operation": operation, "profile": profile, "message": "", "before": None,
               "after": None, "requested": None, "observed": None, "recovery_seconds": None, "verified": False}
        with self.lock:
            try:
                if not valid_iface(iface):
                    raise BackendError("Invalid interface name")
                mode, mac = self.resolve_target(strategy, p)
                res["requested"] = mac
                self.remember_original(iface)
                before = self.obs.snapshot(iface, connectivity=True)
                res["before"] = before
                old = before["mac"]
                self.log.emit("MAC", "MAC change requested (%s)" % operation, iface=iface, old=old, requested=mac)
                if before["up"]:
                    self.log.emit("NETWORK", "Interface going down for the change", iface=iface)
                try:
                    self.b.macchanger_apply(iface, mode, mac)
                except BackendError as e:
                    self.log.emit("ERROR", str(e), "ERROR", iface=iface)
                    after_fail = self.b.current_mac(iface)
                    if after_fail != old:
                        self.log.emit("ERROR", "Interface MAC changed unexpectedly, attempting recovery", "WARNING", iface=iface)
                        self._recover(iface, old)
                    raise
                observed = self.b.current_mac(iface)
                res["observed"] = observed
                if mac and observed != mac:
                    self.log.emit("ERROR", "Requested %s but interface reports %s" % (mac, observed), "ERROR", iface=iface)
                    self._recover(iface, old)
                    raise BackendError("Verification failed: requested %s, observed %s. Previous MAC restored." % (mac, observed))
                if mode == "permanent":
                    res["requested"] = observed
                res["verified"] = True
                self.log.emit("MAC", "MAC change successful: %s -> %s (verified)" % (old, observed), iface=iface)
                self.log.emit("NETWORK", "Interface restored", iface=iface)
                rec = {"seconds": None}
                if reconnect:
                    rec = self._reconnect(iface, before, wait or self.settings.get("reconnect_timeout_sec"))
                after = self.obs.snapshot(iface, connectivity=True)
                res.update(after=after, recovery_seconds=rec.get("seconds"))
                res["ok"] = True
                res["message"] = self._summary(old, observed, before, after, rec)
                res["degraded"] = rec.get("failed", False)
                self.log.emit("MAC" if not rec.get("failed") else "ERROR", res["message"].splitlines()[0],
                              "INFO" if not rec.get("failed") else "WARNING", iface=iface)
            except (BackendError, MacError) as e:
                res["message"] = str(e)
                self.log.emit("ERROR", "MAC operation failed: %s" % e, "ERROR", iface=iface)
        dur = round(time.time() - t0, 2)
        self.hist.add(iface=iface, old_mac=(res["before"] or {}).get("mac"), new_mac=res["observed"],
                      profile=profile or "", operation=operation, result="Success" if res["ok"] else "Failed: " + res["message"][:120],
                      duration=dur)
        res["duration"] = dur
        return res

    def _recover(self, iface, old):
        try:
            self.b.macchanger_apply(iface, "set", old)
            self.log.emit("MAC", "Recovered previous MAC %s" % old, "WARNING", iface=iface)
        except BackendError as e:
            self.log.emit("ERROR", "Recovery failed: %s" % e, "ERROR", iface=iface)

    def _reconnect(self, iface, before, timeout):
        """Wait for the link to come back; renew DHCP if a lease was in use. Returns timing."""
        t0 = time.time()
        wanted_lease = before.get("dynamic4") or before.get("nm", "").startswith("connected")
        if wanted_lease:
            self.log.emit("DHCP", "DHCP renewal started", iface=iface)
            try:
                how = self.b.renew_dhcp(iface)
                self.log.emit("DHCP", "DHCP renewal requested via %s" % how, iface=iface)
            except BackendError as e:
                self.log.emit("DHCP", "Could not renew DHCP: %s" % e, "WARNING", iface=iface)
        failed = False
        while True:
            s = self.obs.snapshot(iface)
            if s["up"] and (s["ipv4"] or not before["ipv4"]):
                break
            if time.time() - t0 > timeout:
                failed = True
                break
            time.sleep(1)
        secs = round(time.time() - t0, 1)
        if not failed:
            self.log.emit("DHCP" if wanted_lease else "NETWORK", "Address present after %.1f s" % secs, iface=iface)
            s = self.obs.snapshot(iface, connectivity=True)
            self.log.emit("DNS", "DNS test %s" % ("successful" if s.get("dns") else "failed"), "INFO" if s.get("dns") else "WARNING", iface=iface)
            if s.get("internet_v4"):
                self.log.emit("NETWORK", "Connectivity verified", iface=iface)
        else:
            self.log.emit("DHCP", "No address after %ds" % timeout, "WARNING", iface=iface)
        return {"seconds": secs, "failed": failed}

    @staticmethod
    def _summary(old, new, before, after, rec):
        lines = []
        if old == new:
            lines.append("MAC unchanged (%s)." % new)
        else:
            lines.append("MAC changed from %s to %s and verified." % (old, new))
        if rec.get("seconds") is not None:
            if rec.get("failed"):
                lines.append("MAC changed successfully, but the interface did not get an address back within %.0f seconds." % rec["seconds"])
                lines.append("Recommended action: renew DHCP or reconnect the interface.")
            else:
                if before.get("ipv4") or before.get("ipv6"):
                    lines.append("Network connectivity restored in %.1f seconds." % rec["seconds"])
        if after.get("dns") is False and before.get("dns"):
            lines.append("DNS worked before the change but fails now.")
        return "\n".join(lines)

    def restore(self, iface, profile=None):
        mode_perm = self.b.permanent_mac(iface)
        if mode_perm:
            return self.apply(iface, "permanent", profile=profile, operation="Restore permanent MAC")
        orig = self.original_mac(iface)
        if not orig:
            return {"ok": False, "message": "No permanent or original MAC is known for %s" % iface, "iface": iface}
        return self.apply(iface, "fixed", {"mac": orig}, profile=profile, operation="Restore original MAC")


# ------------------------------------------------------------------ rotation
class RotationState:
    """Pure scheduler: no threads, takes a clock so tests control time."""

    def __init__(self, interval_min, clock=time.time):
        self.clock = clock
        self.interval = max(1, int(interval_min)) * 60
        self.running = False
        self.paused = False
        self.next_at = None
        self.paused_left = None
        self.count = 0

    def start(self):
        self.running, self.paused = True, False
        self.next_at = self.clock() + self.interval

    def stop(self):
        self.running, self.paused, self.next_at = False, False, None

    def pause(self):
        if self.running and not self.paused:
            self.paused = True
            self.paused_left = max(0, self.next_at - self.clock())

    def resume(self):
        if self.running and self.paused:
            self.paused = False
            self.next_at = self.clock() + self.paused_left

    def remaining(self):
        if not self.running:
            return None
        return self.paused_left if self.paused else max(0, self.next_at - self.clock())

    def due(self):
        return self.running and not self.paused and self.clock() >= self.next_at

    def mark_done(self):
        self.count += 1
        self.next_at = self.clock() + self.interval


class RotationEngine:
    """One RotationState per interface, driven by a background thread. Also watches for
    link events (reconnect, restart, resume) when the profile asks for them."""

    def __init__(self, manager, log, settings):
        self.m, self.log, self.settings = manager, log, settings
        self.jobs = {}  # iface -> dict(state, profile, strategy_profile, last_snap)
        self.stop_evt = threading.Event()
        self.thread = None
        self.last_tick = time.time()

    def start_rotation(self, iface, profile, interval_min=None):
        rot = profile.get("rotation", {})
        interval = int(interval_min or rot.get("interval_min", 30))
        minimum = int(self.settings.get("min_rotation_minutes"))
        if interval < minimum:
            raise ValueError("Interval is below the safeguard minimum (%d min). Change it in Settings > Rotation." % minimum)
        if profile.get("strategy") in ("fixed", "permanent"):
            raise ValueError("Rotation needs a changing strategy (random, vendor, locally administered or pattern)")
        st = RotationState(interval)
        st.start()
        self.jobs[iface] = {"state": st, "profile": profile, "snap": None, "busy": False}
        self.log.emit("ROTATION", "Rotation started every %d min (%s)" % (interval, STRATEGIES[profile["strategy"]]), iface=iface)
        self._ensure_thread()
        if rot.get("on_start"):
            self.rotate_now(iface, "On application start")

    def stop_rotation(self, iface):
        if iface in self.jobs:
            self.jobs[iface]["state"].stop()
            del self.jobs[iface]
            self.log.emit("ROTATION", "Rotation stopped", iface=iface)

    def pause(self, iface, on=True):
        j = self.jobs.get(iface)
        if j:
            (j["state"].pause if on else j["state"].resume)()
            self.log.emit("ROTATION", "Rotation %s" % ("paused" if on else "resumed"), iface=iface)

    def status(self, iface):
        j = self.jobs.get(iface)
        if not j:
            return None
        st = j["state"]
        return {"running": st.running, "paused": st.paused, "remaining": st.remaining(), "count": st.count,
                "interval_min": st.interval // 60, "profile": j["profile"]["name"]}

    def rotate_now(self, iface, reason="Manual rotation"):
        j = self.jobs.get(iface)
        prof = j["profile"] if j else self.m.profiles.active_for(iface) and self.m.profiles.get(self.m.profiles.active_for(iface))
        if not prof:
            raise ValueError("No profile is active on %s" % iface)
        if j and j["busy"]:
            return None
        if j:
            j["busy"] = True
        try:
            self.log.emit("ROTATION", "Rotation triggered: %s" % reason, iface=iface)
            res = self.m.apply(iface, prof["strategy"], prof, profile=prof["name"], operation="Rotation (%s)" % reason)
            if j:
                j["state"].mark_done()
            if not res["ok"]:
                self.log.emit("ROTATION", "Rotation failed: %s. Will retry next interval." % res["message"], "WARNING", iface=iface)
            return res
        finally:
            if j:
                j["busy"] = False

    def _ensure_thread(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_evt.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="macout-rotation")
        self.thread.start()

    def _loop(self):
        while not self.stop_evt.wait(1.0):
            now = time.time()
            resumed = now - self.last_tick > 30  # clock jumped: system was suspended
            self.last_tick = now
            for iface, j in list(self.jobs.items()):
                rot = j["profile"].get("rotation", {})
                try:
                    if j["state"].due() and not j["busy"]:
                        self.rotate_now(iface, "Scheduled")
                        continue
                    if resumed and rot.get("on_resume"):
                        self.log.emit("SYSTEM", "System resume detected", iface=iface)
                        self.rotate_now(iface, "System resume")
                        continue
                    self._check_events(iface, j, rot)
                except Exception as e:  # never kill the loop
                    self.log.emit("ERROR", "Rotation loop error: %s" % e, "ERROR", iface=iface)
        return

    def _check_events(self, iface, j, rot):
        if not (rot.get("on_wifi_reconnect") or rot.get("on_nm_reconnect") or rot.get("on_iface_restart")):
            return
        if j["busy"]:
            return
        try:
            s = self.m.b.link_info(iface)
            wifi = self.m.b.wifi_info(iface) or {}
            nm = self.m.b.nm_status(iface)
        except BackendError:
            return
        cur = {"up": s["up"], "bssid": wifi.get("bssid"), "nm": nm.split(" ")[0]}
        prev = j["snap"]
        j["snap"] = cur
        if not prev:
            return
        if rot.get("on_iface_restart") and not prev["up"] and cur["up"]:
            self.rotate_now(iface, "Interface restart")
        elif rot.get("on_wifi_reconnect") and not prev["bssid"] and cur["bssid"]:
            self.rotate_now(iface, "Wi-Fi reconnect")
        elif rot.get("on_nm_reconnect") and prev["nm"] != "connected" and cur["nm"] == "connected":
            self.rotate_now(iface, "NetworkManager reconnect")

    def shutdown(self):
        self.stop_evt.set()


# --------------------------------------------------------------- diagnostics
def run_diagnostics(backend, observer, env, iface=None):
    """Return list of {name, status: ok|warn|fail, detail, advice, advanced}."""
    out = []

    def add(name, status, detail="", advice="", advanced=""):
        out.append({"name": name, "status": status, "detail": detail, "advice": advice, "advanced": advanced})

    add("Linux detected", "ok" if env["system"] == "Linux" else "fail", env["distro"])
    add("Architecture supported", "ok" if env["supported_arch"] else "warn", env["arch_raw"],
        "" if env["supported_arch"] else "MAC-OUT is tested on x86_64 and aarch64 only.")
    ver = backend.macchanger_version()
    add("macchanger available", "ok" if ver else "fail", ver or "not found",
        "" if ver else "Install it with: sudo apt install macchanger", "path: %s" % getattr(backend, "macchanger", None))
    add("iproute2 available", "ok" if env["tools"]["ip"] else "fail", env["tools"]["ip"] or "not found",
        "" if env["tools"]["ip"] else "Install it with: sudo apt install iproute2")
    add("Permissions", "ok" if env["root"] else "warn", "running as root" if env["root"] else "not root",
        "" if env["root"] else "Start MAC-OUT with: sudo ./macout (read-only views still work).")
    ifs = backend.list_interfaces()
    add("Network interfaces found", "ok" if ifs else "fail", ", ".join(ifs) or "none")
    add("Network backend", "ok" if env["network_manager"] else "warn",
        "NetworkManager detected" if env["network_manager"] else "NetworkManager not found; persistence uses a systemd unit",
        "" if env["network_manager"] else "Reconnect/resume persistence is limited without NetworkManager.")
    if iface:
        try:
            s = observer.snapshot(iface, connectivity=True)
            add("Interface %s state" % iface, "ok" if s["up"] else "warn", "%s, %s" % (s["state"], s["association"]),
                "" if s["up"] else "Bring the interface up first.")
            if s["type"] in ("Virtual", "Tunnel"):
                add("Interface supports MAC change", "warn", "%s interfaces may reject MAC changes" % s["type"])
            else:
                add("Interface supports MAC change", "ok", "%s interface" % s["type"])
            add("Address configured", "ok" if s["ipv4"] else "warn", ", ".join(s["ipv4"]) or "no IPv4",
                "" if s["ipv4"] else "Renew DHCP or reconnect the interface.")
            if s["ipv4"] and not s.get("dynamic4") and s["nm"].startswith("connected"):
                add("DHCP lease", "warn", "address is not marked dynamic", "Check the connection profile.")
            elif s.get("dynamic4"):
                add("DHCP lease", "ok", "dynamic lease present")
            if s.get("gateway"):
                add("Gateway reachable", "ok" if s["gateway_reachable"] else ("warn" if s["gateway_reachable"] is False else "warn"),
                    s["gateway"], "" if s["gateway_reachable"] else "Gateway did not answer ping (some routers block ping).")
            add("DNS resolution", "ok" if s["dns"] else "fail", "example.com", "" if s["dns"] else "Check DNS servers or reconnect.")
            add("IPv4 Internet", "ok" if s["internet_v4"] else "fail", "TCP connect to 1.1.1.1:443")
            if s.get("internet_v6") is not None:
                add("IPv6 Internet", "ok" if s["internet_v6"] else "warn", "TCP connect to Cloudflare IPv6")
        except BackendError as e:
            add("Interface %s" % iface, "fail", str(e))
    return out


# ------------------------------------------------------------------ sessions
class SessionRecorder:
    def __init__(self, base, log):
        self.dir = os.path.join(base, "sessions")
        self.log = log
        self.active = None
        self.log.listeners.append(self._on_event)
        self.lock = threading.Lock()

    def _next_id(self):
        n = len([f for f in os.listdir(self.dir) if f.endswith(".json")])
        return n + 1

    def start(self):
        with self.lock:
            if self.active:
                return self.active["id"]
            self.active = {"id": self._next_id(), "started": ts(), "start_epoch": time.time(), "events": []}
        self.log.emit("SYSTEM", "Recording session #%d started" % self.active["id"])
        return self.active["id"]

    def _on_event(self, rec):
        with self.lock:
            if self.active:
                self.active["events"].append({k: rec[k] for k in ("time", "category", "level", "message", "iface")})

    def stop(self):
        with self.lock:
            s = self.active
        if not s:
            return None
        self.log.emit("SYSTEM", "Recording session #%d stopped" % s["id"])
        with self.lock:
            s = self.active
            self.active = None
        s["ended"] = ts()
        s["summary"] = self.summarize(s["events"])
        _write_json(os.path.join(self.dir, "session-%04d.json" % s["id"]), s)
        return s

    @staticmethod
    def summarize(events):
        ok = sum(1 for e in events if e["category"] == "MAC" and "change successful" in e["message"])
        failed = sum(1 for e in events if e["category"] == "ERROR" and "MAC operation failed" in e["message"])
        times = [float(m.group(1)) for e in events for m in [re.search(r"Address present after ([\d.]+) s", e["message"])] if m]
        conn_fail = sum(1 for e in events if "No address after" in e["message"] or ("DNS test failed" in e["message"]))
        return {"mac_changes": ok + failed, "successful": ok, "failed": failed,
                "avg_reconnect_seconds": round(sum(times) / len(times), 1) if times else None,
                "connectivity_failures": conn_fail, "events": len(events)}

    def list(self):
        out = []
        for f in sorted(os.listdir(self.dir)):
            if f.endswith(".json"):
                s = _read_json(os.path.join(self.dir, f), None)
                if s:
                    out.append(s)
        return out


# --------------------------------------------------------------- persistence
SERVICE_PATH = "/etc/systemd/system/macout-persist.service"


class Persistence:
    def __init__(self, backend, env, base, log, launcher=None):
        self.b, self.env, self.log = backend, env, log
        self.path = os.path.join(base, "persistent.json")
        self.launcher = launcher or os.path.abspath(os.sys.argv[0])

    def entries(self):
        return _read_json(self.path, {})

    def mechanism(self, iface):
        if self.env["network_manager"] and self.b.nm_connection(iface):
            return "NetworkManager"
        if self.env["systemd"]:
            return "systemd"
        return None

    def explain(self, iface):
        m = self.mechanism(iface)
        if m == "NetworkManager":
            return ("Stored as the cloned MAC of the active NetworkManager connection. NetworkManager re-applies it on reboot, "
                    "reconnect and resume. This only covers that one connection profile.")
        if m == "systemd":
            return ("A systemd unit (macout-persist.service) re-applies the MAC at boot only. Reconnects, interface restarts and "
                    "resume are NOT covered without NetworkManager.")
        return "No supported persistence mechanism was detected on this system. Changes are temporary."

    def enable(self, iface, mac):
        mac = normalize_mac(mac)
        if core.is_multicast(mac):
            raise MacError("Multicast MAC cannot be persistent")
        mech = self.mechanism(iface)
        if not mech:
            raise BackendError(self.explain(iface))
        if not self.env["root"]:
            raise BackendError("Persistence changes system configuration and needs root (run with sudo)")
        if mech == "NetworkManager":
            conn, prop = self.b.nm_set_cloned_mac(iface, mac)
            self.log.emit("SYSTEM", "Persistent MAC set in NetworkManager connection '%s'" % conn, iface=iface)
        else:
            unit = ("[Unit]\nDescription=MAC-OUT persistent MAC addresses\nAfter=network-pre.target\nBefore=network.target\n\n"
                    "[Service]\nType=oneshot\nExecStart=%s --apply-persistent\n\n[Install]\nWantedBy=multi-user.target\n" % self.launcher)
            try:
                with open(SERVICE_PATH, "w") as f:
                    f.write(unit)
            except OSError as e:
                raise BackendError("Could not write %s: %s" % (SERVICE_PATH, e))
            from .backend import run
            run(["systemctl", "daemon-reload"])
            r = run(["systemctl", "enable", "macout-persist.service"])
            if not r.ok:
                raise BackendError("systemctl enable failed: %s" % r.err.strip())
            self.log.emit("SYSTEM", "systemd unit macout-persist.service enabled", iface=iface)
        d = self.entries()
        d[iface] = {"mac": mac, "mechanism": mech, "since": ts()}
        _write_json(self.path, d)
        return mech

    def disable(self, iface):
        d = self.entries()
        e = d.pop(iface, None)
        if e and e["mechanism"] == "NetworkManager":
            self.b.nm_set_cloned_mac(iface, "")
        _write_json(self.path, d)
        if not d and os.path.exists(SERVICE_PATH) and self.env["root"]:
            from .backend import run
            run(["systemctl", "disable", "macout-persist.service"])
            os.remove(SERVICE_PATH)
        self.log.emit("SYSTEM", "Persistence removed", iface=iface)

    def apply_all(self):
        """Used at boot by the systemd unit."""
        out = []
        for iface, e in self.entries().items():
            if e["mechanism"] != "systemd":
                continue
            try:
                self.b.macchanger_apply(iface, "set", e["mac"])
                out.append((iface, True))
            except BackendError:
                out.append((iface, False))
        return out


# ------------------------------------------------------------------- reports
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
IPV6_RE = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}(?:/\d{1,3})?\b")
MAC_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")


def _is_private4(s):
    m = re.match(r"(\d+)\.(\d+)\.", s)
    if not m:
        return False
    a, b = int(m.group(1)), int(m.group(2))
    return a in (10, 127) or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or (a == 169 and b == 254)


class Redactor:
    def __init__(self, opts, known):
        self.o = opts
        self.known = known  # {"cur": set, "perm": set, "bssid": set, "ssid": set}
        self.applied = []

    def text(self, s):
        if not isinstance(s, str):
            return s
        o = self.o
        for v in sorted(self.known.get("ssid", ()), key=len, reverse=True):
            if o.get("redact_ssid") and v and v in s:
                s = s.replace(v, "[SSID redacted]")
        def mac_sub(m):
            v = m.group(0).lower()
            if v in self.known.get("bssid", ()):
                return "[BSSID redacted]" if o.get("redact_bssid") else m.group(0)
            if v in self.known.get("perm", ()):
                return "[permanent MAC redacted]" if o.get("redact_perm_mac") else m.group(0)
            return "[MAC redacted]" if o.get("redact_cur_mac") else m.group(0)
        s = MAC_RE.sub(mac_sub, s)
        def ip4(m):
            v = m.group(0)
            if _is_private4(v):
                return "[local IP redacted]" if o.get("redact_ip_local") else v
            return "[public IP redacted]" if o.get("redact_ip_public") else v
        s = IPV4_RE.sub(ip4, s)
        def ip6(m):
            v = m.group(0)
            if MAC_RE.fullmatch(v):
                return v
            local = v.lower().startswith(("fe80", "fd", "fc", "::1"))
            if local:
                return "[local IP redacted]" if o.get("redact_ip_local") else v
            return "[public IP redacted]" if o.get("redact_ip_public") else v
        return IPV6_RE.sub(ip6, s)

    def walk(self, x):
        if isinstance(x, dict):
            return {k: self.walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [self.walk(v) for v in x]
        return self.text(x) if isinstance(x, str) else x


def redaction_summary(opts):
    names = {"redact_ip_public": "public IP addresses", "redact_ip_local": "local IP addresses", "redact_bssid": "BSSID (access point MAC)",
             "redact_ssid": "SSID (Wi-Fi name)", "redact_perm_mac": "permanent MAC", "redact_cur_mac": "current/previous MACs"}
    gone = [v for k, v in names.items() if opts.get(k)]
    keep = "System information (OS, kernel) is %s." % ("included" if opts.get("include_system") else "left out")
    return ("Removed from the export: " + ", ".join(gone) + ". " if gone else "Nothing is redacted. ") + keep


class ReportGenerator:
    def __init__(self, env, backend, observer, manager, log, history, sessions, profiles, rotation=None):
        self.env, self.b, self.obs, self.m, self.log = env, backend, observer, manager, log
        self.hist, self.sessions, self.profiles, self.rotation = history, sessions, profiles, rotation

    def collect(self, ifaces=None, opts=None):
        opts = opts or {}
        ifaces = ifaces or self.b.list_interfaces()
        snaps = []
        for i in ifaces:
            try:
                snaps.append(self.obs.snapshot(i, connectivity=True))
            except BackendError:
                pass
        events = self.log.visible()
        errors = [e for e in events if e["level"] == "ERROR"]
        warns = [e for e in events if e["level"] == "WARNING"]
        hist = self.hist.all()[-200:]
        data = {
            "macout_version": core.VERSION, "generated": ts(),
            "system": ({"os": self.env["distro"], "kernel": self.env["kernel"], "architecture": self.env["arch_raw"]}
                       if opts.get("include_system") else {"note": "System information excluded"}),
            "interfaces": snaps,
            "profiles_active": self.profiles.active_map(),
            "operations": hist,
            "timeline": [{k: e[k] for k in ("time", "category", "level", "message", "iface")} for e in events],
            "warnings": [w["message"] for w in warns], "errors": [e["message"] for e in errors],
            "rotation_history": [h for h in hist if "Rotation" in str(h.get("operation"))],
            "observed_behavior_note": "These are locally observed values. MAC-OUT cannot see what the upstream network records.",
        }
        ok = sum(1 for h in hist if h.get("result") == "Success")
        data["summary"] = {"operations": len(hist), "successful": ok, "failed": len(hist) - ok, "errors": len(errors), "warnings": len(warns)}
        return data

    def redact(self, data, opts):
        known = {"cur": set(), "perm": set(), "bssid": set(), "ssid": set()}
        for s in data["interfaces"]:
            if s.get("permanent"):
                known["perm"].add(s["permanent"])
            if s.get("wifi"):
                if s["wifi"].get("bssid"):
                    known["bssid"].add(s["wifi"]["bssid"])
                if s["wifi"].get("ssid"):
                    known["ssid"].add(s["wifi"]["ssid"])
        r = Redactor(opts, known)
        return r.walk(data)

    # ---- renderers
    @staticmethod
    def to_txt(d):
        L = ["MAC-OUT diagnostic report", "Version %s  |  %s" % (d["macout_version"], d["generated"]), "=" * 56, ""]
        L.append("SYSTEM")
        for k, v in d["system"].items():
            L.append("  %s: %s" % (k, v))
        for s in d["interfaces"]:
            L += ["", "INTERFACE %s (%s)" % (s["iface"], s["type"]), "  MAC: %s" % s["mac"], "  Permanent MAC: %s" % (s.get("permanent") or "not available"),
                  "  State: %s / %s" % (s["state"], s["association"]), "  IPv4: %s" % (", ".join(s["ipv4"]) or "none"),
                  "  IPv6: %s" % (", ".join(s["ipv6"]) or "none"), "  Gateway: %s" % (s.get("gateway") or "none"),
                  "  DHCP: %s" % s["dhcp"], "  DNS test: %s" % s.get("dns"), "  IPv4 Internet: %s" % s.get("internet_v4")]
            if s.get("wifi"):
                L.append("  Wi-Fi: SSID %s, BSSID %s, signal %s" % (s["wifi"].get("ssid"), s["wifi"].get("bssid"), s["wifi"].get("signal")))
        L += ["", "SUMMARY"] + ["  %s: %s" % kv for kv in d["summary"].items()]
        L += ["", "OPERATIONS"] + ["  %s  %s  %s -> %s  %s  %s" % (o.get("time"), o.get("iface"), o.get("old_mac"), o.get("new_mac"), o.get("operation"), o.get("result")) for o in d["operations"]]
        L += ["", "TIMELINE"] + ["  %s  %-8s %s" % (e["time"][11:], e["category"], e["message"]) for e in d["timeline"]]
        if d["warnings"]:
            L += ["", "WARNINGS"] + ["  " + w for w in d["warnings"]]
        if d["errors"]:
            L += ["", "ERRORS"] + ["  " + w for w in d["errors"]]
        L += ["", d["observed_behavior_note"], ""]
        return "\n".join(L)

    @staticmethod
    def to_csv(d):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["time", "category", "level", "iface", "message"])
        for e in d["timeline"]:
            w.writerow([e["time"], e["category"], e["level"], e.get("iface") or "", e["message"]])
        return buf.getvalue()

    @staticmethod
    def logo_data_uri():
        try:
            raw = pkgutil.get_data("macout_app", "assets/makaut_logo.jpg")
            return "data:image/jpeg;base64," + base64.b64encode(raw).decode()
        except Exception:
            return ""

    def to_html(self, d):
        esc = lambda x: ("%s" % x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rows = ""
        for s in d["interfaces"]:
            w = s.get("wifi")
            rows += ("<div class='card'><h3>%s <span class='tag'>%s</span></h3><table>" % (esc(s["iface"]), esc(s["type"])) +
                     "".join("<tr><td>%s</td><td>%s</td></tr>" % (esc(k), esc(v)) for k, v in [
                         ("Current MAC", s["mac"]), ("Permanent MAC", s.get("permanent") or "not available"),
                         ("State", "%s, %s" % (s["state"], s["association"])), ("IPv4", ", ".join(s["ipv4"]) or "none"),
                         ("IPv6", ", ".join(s["ipv6"]) or "none"), ("Gateway", s.get("gateway") or "none"), ("DHCP", s["dhcp"]),
                         ("DNS test", "OK" if s.get("dns") else "Failed"), ("IPv4 Internet", "OK" if s.get("internet_v4") else "Failed")] +
                         ([("Wi-Fi", "SSID %s / BSSID %s / %s dBm" % (w.get("ssid"), w.get("bssid"), w.get("signal")))] if w else [])) +
                     "</table></div>")
        ops = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % tuple(
            esc(o.get(k, "")) for k in ("time", "iface", "old_mac", "new_mac", "operation", "result")) for o in d["operations"])
        tl = "".join("<div class='ev'><span class='t'>%s</span><span class='c c-%s'>%s</span>%s</div>" % (
            esc(e["time"][11:]), esc(e["category"]), esc(e["category"]), esc(e["message"])) for e in d["timeline"])
        logo = self.logo_data_uri()
        sysrows = "".join("<tr><td>%s</td><td>%s</td></tr>" % (esc(k), esc(v)) for k, v in d["system"].items())
        summ = "".join("<div class='stat'><b>%s</b><span>%s</span></div>" % (esc(v), esc(k)) for k, v in d["summary"].items())
        return """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>MAC-OUT report</title>
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f4f6fa;color:#1b2430;margin:0}
.wrap{max-width:960px;margin:0 auto;padding:32px 24px}
header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #d9dfe8;padding-bottom:18px;margin-bottom:24px}
h1{margin:0;font-size:28px;letter-spacing:.5px} .sub{color:#5b6778;font-size:14px;margin-top:4px}
header img{height:64px;opacity:.95;border-radius:6px}
.card{background:#fff;border:1px solid #e0e5ee;border-radius:12px;padding:16px 20px;margin:14px 0}
h2{font-size:18px;margin:28px 0 8px} h3{margin:0 0 8px}
.tag{font-size:12px;background:#e7eefc;color:#2a55b8;border-radius:10px;padding:2px 8px;margin-left:6px}
table{border-collapse:collapse;width:100%%;font-size:14px} td,th{padding:6px 8px;border-bottom:1px solid #eef1f6;text-align:left;vertical-align:top}
td:first-child{color:#5b6778;width:160px}
.stats{display:flex;gap:12px;flex-wrap:wrap}.stat{background:#fff;border:1px solid #e0e5ee;border-radius:12px;padding:12px 18px;display:flex;flex-direction:column}
.stat b{font-size:24px}.stat span{font-size:12px;color:#5b6778;text-transform:capitalize}
.ev{font-family:ui-monospace,Menlo,monospace;font-size:13px;padding:3px 0}.t{color:#7a8597;margin-right:10px}
.c{display:inline-block;min-width:70px;font-size:11px;border-radius:6px;padding:1px 6px;margin-right:8px;background:#e8ecf3}
.c-ERROR{background:#fde2e2;color:#a31b1b}.c-MAC{background:#e1f0ff;color:#0b5cad}.c-DHCP{background:#e9f7e9;color:#1f7a1f}
.note{font-size:13px;color:#5b6778;margin-top:28px;border-top:1px solid #d9dfe8;padding-top:12px}
</style></head><body><div class="wrap"><header><div><h1>MAC-OUT</h1><div class="sub">Diagnostic report &middot; version %s &middot; %s<br>Designed for CA-1 &mdash; MAKAUT, WB</div></div>%s</header>
<h2>Summary</h2><div class="stats">%s</div>
<h2>System</h2><div class="card"><table>%s</table></div>
<h2>Interfaces</h2>%s
<h2>Operations</h2><div class="card"><table><tr><th>Time</th><th>Interface</th><th>Old MAC</th><th>New MAC</th><th>Operation</th><th>Result</th></tr>%s</table></div>
<h2>Event timeline</h2><div class="card">%s</div>
<p class="note">%s<br>Made by Arnab Mandal &middot; arnabmandal.com &middot; arnab@ik.me</p></div></body></html>""" % (
            esc(d["macout_version"]), esc(d["generated"]), ("<img alt='MAKAUT logo' src='%s'>" % logo) if logo else "",
            summ, sysrows, rows, ops, tl, esc(d["observed_behavior_note"]))

    def export(self, fmt, path, ifaces=None, opts=None):
        opts = opts or {}
        data = self.redact(self.collect(ifaces, opts), opts)
        data["redaction"] = redaction_summary(opts)
        renderers = {"txt": self.to_txt, "json": lambda d: json.dumps(d, indent=2), "csv": self.to_csv, "html": self.to_html}
        if fmt == "zip":
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for k, fn in renderers.items():
                    z.writestr("macout-report." + k, fn(data))
        elif fmt in renderers:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(renderers[fmt](data))
        else:
            raise ValueError("Unknown format %s" % fmt)
        self.log.emit("SYSTEM", "Report exported: %s" % os.path.basename(path))
        return path


# ----------------------------------------------------------------- app facade
class App:
    """Wires all services together. The GUI and tests both create this."""

    def __init__(self, backend=None, base=None, env=None):
        from .backend import SystemBackend
        self.base = base or data_dir()
        self.settings = Settings(self.base)
        self.env = env or core.detect_environment(self.settings.get("macchanger_path") or None)
        self.backend = backend or SystemBackend(self.settings.get("macchanger_path") or None)
        self.log = EventLog(self.base, self.settings)
        self.history = History(self.base)
        self.profiles = ProfileManager(self.base, self.log)
        self.observer = Observer(self.backend)
        self.manager = MacManager(self.backend, self.observer, self.log, self.history, self.profiles, self.settings, self.base)
        self.rotation = RotationEngine(self.manager, self.log, self.settings)
        self.sessions = SessionRecorder(self.base, self.log)
        self.persistence = Persistence(self.backend, self.env, self.base, self.log)
        self.reports = ReportGenerator(self.env, self.backend, self.observer, self.manager, self.log, self.history,
                                       self.sessions, self.profiles, self.rotation)
        self.log.prune(int(self.settings.get("log_retention_days")))
        self.history.prune(int(self.settings.get("history_retention_days")))
        self.log.emit("SYSTEM", "MAC-OUT %s started on %s (%s)%s" % (core.VERSION, self.env["distro"], self.env["arch"],
                                                                    ", root" if self.env["root"] else ", not root"))

    def activate_profile(self, iface, name, apply=True):
        p = self.profiles.get(name)
        if not p:
            raise ValueError("No such profile")
        self.profiles.set_active(iface, name)
        self.log.set_verbosity(p.get("log_level", self.settings.get("verbosity")))
        self.log.emit("PROFILE", "Profile activated: %s" % name, iface=iface)
        res = None
        if apply:
            res = self.manager.apply(iface, p["strategy"], p, profile=name, operation="Profile activation", reconnect=p.get("reconnect", True))
            if res["ok"] and p.get("persistent") and res.get("observed"):
                try:
                    self.persistence.enable(iface, res["observed"])
                except (BackendError, MacError) as e:
                    self.log.emit("ERROR", "Persistence not applied: %s" % e, "WARNING", iface=iface)
        if p.get("rotation", {}).get("enabled") and p["strategy"] not in ("fixed", "permanent"):
            try:
                self.rotation.start_rotation(iface, p)
            except ValueError as e:
                self.log.emit("ROTATION", str(e), "WARNING", iface=iface)
        return res

    def deactivate_profile(self, iface):
        self.rotation.stop_rotation(iface)
        name = self.profiles.active_for(iface)
        self.profiles.set_active(iface, None)
        self.log.emit("PROFILE", "Profile deactivated: %s" % name, iface=iface)
