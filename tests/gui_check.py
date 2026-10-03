"""Exercises every page of the real GUI against a real (dummy) interface and asserts results.
Run via tests/run_gui_check.sh."""
import os, sys, time, json, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from macout_app import services, gui, core

OUT = os.environ.get("SHOTS", "/tmp/shots2")
os.makedirs(OUT, exist_ok=True)
app = services.App()
app.settings.data.update(confirm_actions=False, first_run_done=True, reconnect_timeout_sec=5, theme=os.environ.get("THEME", "light"))
win = gui.MacOutWindow(app)
win.resize(1200, 800)
results = []

def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.01)

def wait(cond, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        pump(0.1)
        if cond():
            return True
    return False

def idle():
    return wait(lambda: not win.busy, 25)

def shot(name):
    import cairo
    pump(0.4)
    w = win.get_window()
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w.get_width(), w.get_height())
    win.draw(cairo.Context(surf))
    surf.write_to_png("%s/%s.png" % (OUT, name))

def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" - " + str(detail)) if detail else ""), flush=True)

def mac():
    return app.backend.current_mac("wlan0")

pump(2.5)
orig = mac()
check("dashboard shows interface card", "wlan0" in win.snaps and len(win.dash_cards.get_children()) >= 1)
shot("a-dashboard")

# specific MAC, valid and invalid
win.goto("MAC Control"); pump()
win.mac_entry.set_text("zz:11"); pump(0.2)
check("invalid MAC flagged live", "not a valid" in win.mac_hint.get_text(), win.mac_hint.get_text())
win.mac_entry.set_text("01:00:5e:00:00:01"); pump(0.2)
check("multicast MAC flagged live", "multicast" in win.mac_hint.get_text(), win.mac_hint.get_text())
win.mac_entry.set_text("02:11:22:33:44:55"); pump(0.2)
win.apply_manual(); idle()
check("specific MAC applied and verified", mac() == "02:11:22:33:44:55" and win.last_result["verified"], mac())
check("MAC info card refreshed", "02:11:22:33:44:55" in "".join(c.get_text() for c in win.mc_info.get_children()[1].get_children() if hasattr(c, "get_text")))

# locally administered
win.do_apply("local", {}); idle()
check("locally administered MAC applied", core.is_locally_administered(mac()) and not core.is_multicast(mac()), mac())

# vendor
win.vendor_search.set_text("cisco"); pump(0.5)
check("vendor search lists results", len(win.vendor_store) > 0, len(win.vendor_store))
win.vendor_tv.get_selection().select_path(Gtk.TreePath.new_first()); pump(0.2)
win.vendor_generate(); pump(0.2)
cand = win.vendor_candidate
check("vendor preview generated", cand and cand.startswith(win.vendor_pick[0].lower()), cand)
win.vendor_apply(); idle()
check("vendor MAC applied", mac() == cand, mac())
shot("b-mac-control-vendor")

# restore
win.do_restore(); idle()
check("restore returns first-seen MAC", mac() == orig, "%s vs %s" % (mac(), orig))

# failure path on real interface: bad MAC through manager
r = app.manager.apply("wlan0", "fixed", {"mac": "01:00:5e:00:00:01"})
check("multicast request refused by manager", not r["ok"] and mac() == orig)
r = app.manager.apply("nosuch0", "random")
check("missing interface reported cleanly", not r["ok"] and "does not exist" in r["message"], r["message"])

# profiles
win.goto("Profiles"); pump()
before = len(win.pf_store)
win.pf_new(); pump(0.3)
check("profile created", len(win.pf_store) == before + 1)
win.pf["strategy"].set_active_id("fixed"); win.pf["mac"].set_text("02:aa:bb:cc:dd:ee"); win.pf["name"].set_text("Lab test")
win.pf_save(); pump(0.3)
check("profile saved", app.profiles.get("Lab test") and app.profiles.get("Lab test")["mac"] == "02:aa:bb:cc:dd:ee")
win.pf["mac"].set_text("nope"); win.pf_save(); pump(0.2)
check("invalid profile rejected", "Not saved" in win.pf_msg.get_text(), win.pf_msg.get_text())
win.pf["mac"].set_text("02:aa:bb:cc:dd:ee"); win.pf_save(); pump(0.2)
win.pf_activate(); idle()
check("profile activation applied MAC", mac() == "02:aa:bb:cc:dd:ee" and app.profiles.active_for("wlan0") == "Lab test", mac())
dup = app.profiles.duplicate("Lab test")
path = "/tmp/lab.macout.json"; app.profiles.export("Lab test", path); app.profiles.delete(dup["name"]); imp = app.profiles.import_file(path)
check("profile duplicate/export/import/delete", imp["name"] == "Lab test copy" or imp["name"] == "Lab test")
shot("c-profiles-active")
win.pf_deactivate()

# rotation: timer + event
win.goto("Rotation"); pump()
app.settings.data["min_rotation_minutes"] = 1
win.rot_interval.get_child().set_text("1"); win.rot_trig["on_iface_restart"].set_active(True)
win.start_rotation(); pump(0.5)
st = app.rotation.status("wlan0")
check("rotation started", st and st["running"] and 55 <= st["remaining"] <= 60, st)
win.pause_rotation(); pump(1.2); r1 = app.rotation.status("wlan0")["remaining"]; pump(1.5); r2 = app.rotation.status("wlan0")["remaining"]
check("pause freezes countdown", app.rotation.status("wlan0")["paused"] and abs(r1 - r2) < 0.5, (r1, r2))
win.pause_rotation()
job = app.rotation.jobs["wlan0"]["state"]
job.interval = 3; job.next_at = time.time() + 3
m0 = mac(); wait(lambda: app.rotation.status("wlan0")["count"] >= 2, 30)
check("timed rotation fired twice", app.rotation.status("wlan0")["count"] >= 2 and mac() != m0, app.rotation.status("wlan0"))
job.interval = 600; job.next_at = time.time() + 600
pump(2.5)  # let event watcher record up state
n0 = app.rotation.status("wlan0")["count"]; m1 = mac()
os.system("ip link set wlan0 down"); pump(2.5); os.system("ip link set wlan0 up")
wait(lambda: app.rotation.status("wlan0")["count"] > n0, 15); idle()
check("interface-restart event triggered rotation", app.rotation.status("wlan0")["count"] > n0 and mac() != m1)
win.rotate_now(); idle()
check("rotate now works", win.last_result and win.last_result["ok"])
shot("d-rotation")
win.stop_rotation(); pump(0.3)
check("rotation stopped", app.rotation.status("wlan0") is None)

# session recording
win.goto("Network Observer"); pump()
win.toggle_recording(); pump(0.3)
check("recording started", app.sessions.active is not None)
win.do_apply("random", {}); idle()
win.do_restore(); idle()
win.toggle_recording(); pump(0.3)
sm = app.sessions.list()[-1]["summary"]
check("session summary counts the 2 changes", sm["mac_changes"] == 2 and sm["successful"] == 2, sm)
check("before/after panel filled", len(win.ba_box.get_children()) == 1)
win.refresh_observer(); shot("e-observer-session")

# persistence (no NetworkManager here; systemd unit write must fail cleanly or work)
try:
    app.persistence.enable("wlan0", "02:00:00:00:00:77"); ok, msg = True, "enabled"
except (services.BackendError, core.MacError) as e:
    ok, msg = True, "clean error: %s" % e
check("persistence returns result or clean error", ok, msg)
check("persistence explanation text mentions mechanism", len(app.persistence.explain("wlan0")) > 30, app.persistence.explain("wlan0")[:90])

# diagnostics
win.goto("Diagnostics"); win.run_diag(); wait(lambda: len(win.diag_box.get_children()) and isinstance(win.diag_box.get_children()[0], Gtk.Box) and "MAC-OUT Diagnostics" in str([c.get_text() for c in win.diag_box.get_children()[0].get_children() if hasattr(c, "get_text")]), 15)
check("diagnostics rendered", len(win.diag_box.get_children()) == 1)
shot("f-diagnostics")

# history, logs
win.goto("History"); pump(0.5)
rows = win.history_rows()
check("history has entries", len(rows) >= 8, len(rows))
win.h_search.set_text("Rotation"); pump(0.6)
check("history search filters", 0 < len(win.h_store) < len(rows), len(win.h_store))
csvp = os.path.join(OUT, "history.csv"); open(csvp, "w").write(app.history.to_csv(rows))
check("history CSV export", open(csvp).read().count("\n") == len(rows) + 1)
win.h_search.set_text("")
win.goto("Logs"); pump(0.5)
n_all = len(win.l_store); win.l_cat.set_active(services.CATEGORIES.index("ROTATION") + 1); pump(0.3)
check("log category filter", 0 < len(win.l_store) < n_all, (len(win.l_store), n_all))
win.l_cat.set_active(0)
win.l_verb.set_active(0); pump(0.3)
check("errors-only verbosity hides info", all(r["level"] == "ERROR" for r in app.log.visible()))
win.l_verb.set_active(1)
check("log file is structured JSON", all(isinstance(json.loads(l), dict) for l in open(app.log.path).read().splitlines()))
shot("g-logs")

# reports
win.goto("Reports"); pump()
for k, cb in win.rp.items(): cb.set_active(k != "include_system")
for fmt in ("HTML", "TXT", "JSON", "CSV", "ZIP"):
    win.rp_fmt.set_active(["HTML", "TXT", "JSON", "CSV", "ZIP"].index(fmt))
    p = os.path.join(OUT, "report." + fmt.lower()); win.export_report(p); wait(lambda: os.path.exists(p) and "Saved" in win.rp_msg.get_text(), 15)
    check("report %s exported" % fmt, os.path.getsize(p) > 200)
txt = open(os.path.join(OUT, "report.html")).read() + open(os.path.join(OUT, "report.json")).read()
leaks = [x for x in ("10.77.0.2", mac(), orig, "02:aa:bb:cc:dd:ee") if x in txt]
check("redacted reports leak no IP or MAC", not leaks, leaks)
check("HTML report has MAKAUT branding + credits", "MAKAUT" in txt and "Arnab Mandal" in txt)
win.rp["redact_ip_local"].set_active(False); win.rp["redact_cur_mac"].set_active(False); win.rp_fmt.set_active(1)
p = os.path.join(OUT, "raw.txt"); win.export_report(p); wait(lambda: os.path.exists(p) and "Saved" in win.rp_msg.get_text(), 15)
check("unticked redactions are kept", "10.77.0.2" in open(p).read())
shot("h-reports")

# settings / theme / first run / about
win.goto("Settings"); pump()
win.toggle_theme(); pump(0.4); shot("i-settings-dark"); win.toggle_theme()
check("theme setting persisted", app.settings.get("theme") in ("dark", "light"))
win.first_run(); pump(0.6); shot("j-first-run")
for w in Gtk.Window.list_toplevels():
    if w is not win: w.destroy()
win.goto("About"); pump(0.4)
check("about page shown", win.stack.get_visible_child_name() == "About")
win.goto("Dashboard"); pump(3); shot("k-dashboard-final")
print("SUMMARY %d/%d passed" % (sum(1 for _, ok in results if ok), len(results)))
for n, ok in results:
    if not ok: print("FAILED:", n)
