"""Drives the real GUI against a real (dummy) interface and takes screenshots.
Run through tests/run_gui_demo.sh, which sets up a private network namespace."""
import os, subprocess, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from macout_app import services, gui
from macout_app.gui_common import PAGES

OUT = os.environ.get("SHOTS", "/tmp/shots")
os.makedirs(OUT, exist_ok=True)
app = services.App()
app.settings.data.update(confirm_actions=False, first_run_done=True, reconnect_timeout_sec=6, theme=os.environ.get("THEME", "light"))
app.settings.save()
win = gui.MacOutWindow(app)
win.resize(1200, 800)
steps = []

def shot(name):
    import cairo
    w = win.get_window()
    W, H = w.get_width(), w.get_height()
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    win.draw(cr)
    surf.write_to_png("%s/%s.png" % (OUT, name))
    r = win.last_result
    print("SHOT", name, "last:", r and (r.get("ok"), r.get("observed"), (r.get("message") or "")[:100]), flush=True)

def at(delay_ms, fn):
    steps.append((delay_ms, fn))

def goto(p):
    win.goto(p)

def wait_idle():
    return not win.busy

t = [1500]
def add(fn, gap=1200):
    t[0] += gap
    steps.append((t[0], fn))

add(lambda: shot("01-dashboard"))
add(lambda: goto("MAC Control"))
add(lambda: shot("02-mac-control"))
add(lambda: win.do_apply("random", {}), 800)
add(lambda: shot("03-after-random"), 9000)
add(lambda: goto("Network Observer"))
add(lambda: shot("04-observer"))
add(lambda: win.do_restore(), 500)
add(lambda: (goto("MAC Control"), shot("05-restored")), 9000)
add(lambda: (goto("Rotation"), setattr(win.rot_interval, "x", 0), win.rot_interval.get_child().set_text("1"), win.start_rotation()), 800)
add(lambda: (setattr(app.rotation.jobs["wlan0"]["state"], "interval", 4), setattr(app.rotation.jobs["wlan0"]["state"], "next_at", __import__("time").time() + 4)), 500)
add(lambda: shot("06-rotation"), 14000)
add(lambda: (goto("Profiles"),), 800)
add(lambda: shot("07-profiles"))
add(lambda: (goto("Diagnostics"), win.run_diag()))
add(lambda: shot("08-diagnostics"), 5000)
add(lambda: (goto("History")))
add(lambda: shot("09-history"))
add(lambda: (goto("Logs")))
add(lambda: shot("10-logs"))
add(lambda: (goto("Reports"), win.rp_fmt.set_active(0), win.export_report(os.path.join(OUT, "report.html"))))
add(lambda: shot("11-reports"), 3000)
add(lambda: (goto("Settings")))
add(lambda: shot("12-settings"))
add(lambda: (goto("About")))
add(lambda: shot("13-about"))
add(lambda: (win.stop_rotation(), print("RESULT", json.dumps(win.last_result and {k: win.last_result.get(k) for k in ("ok", "requested", "observed", "verified", "message")}))), 500)
add(lambda: Gtk.main_quit(), 800)
for d, fn in steps:
    GLib.timeout_add(d, lambda f=fn: (f(), False)[1])
Gtk.main()
print("DONE")
