"""Shared GTK helpers, theme CSS and widgets."""
import pkgutil

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, GdkPixbuf  # noqa: E402

PAGES = ["Dashboard", "Interfaces", "MAC Control", "Profiles", "Rotation", "Network Observer",
         "Diagnostics", "History", "Logs", "Reports", "Settings", "About"]

CSS_COMMON = """
* { font-family: "Inter", "Noto Sans", "DejaVu Sans", sans-serif; }
.sidebar { padding: 10px 8px; }
.sidebar row { padding: 9px 14px; border-radius: 8px; margin: 1px 0; }
.brand { font-size: 20px; font-weight: 800; letter-spacing: 1px; }
.brandsub { font-size: 10px; }
.title { font-size: 22px; font-weight: 700; }
.subtitle { font-size: 13px; }
.section { font-size: 12px; font-weight: 700; letter-spacing: 1px; }
.card { border-radius: 12px; padding: 16px 18px; }
.cardtitle { font-size: 15px; font-weight: 700; }
.big { font-size: 28px; font-weight: 700; }
.mono { font-family: "DejaVu Sans Mono", monospace; font-size: 13px; }
.key { font-size: 12px; }
.pill { border-radius: 10px; padding: 2px 10px; font-size: 11px; font-weight: 700; }
.banner { padding: 8px 14px; border-radius: 8px; font-size: 13px; }
button { border-radius: 8px; padding: 7px 14px; }
entry { border-radius: 8px; padding: 6px 10px; }
.countdown { font-size: 34px; font-weight: 700; font-family: "DejaVu Sans Mono", monospace; }
"""

CSS_LIGHT = """
window, .page { background: #f3f5f9; color: #1b2430; }
.sidebar { background: #ffffff; border-right: 1px solid #dde3ec; }
.sidebar row:selected { background: #2a62d6; color: #ffffff; }
.sidebar row:selected label { color: #ffffff; }
.sidebar row:hover:not(:selected) { background: #eef2f9; }
.sidebar label { color: #1b2430; }
.sidebar .brandsub { color: #5b6778; }
.brandsub, .subtitle, .key { color: #5b6778; }
.card { background: #ffffff; border: 1px solid #e1e6ef; }
.section { color: #7a8597; }
.ok { color: #137a3a; } .warn { color: #a85d00; } .bad { color: #b3261e; }
.pill-ok { background: #dff3e5; color: #137a3a; } .pill-warn { background: #fdecc8; color: #8a4b00; }
.pill-bad { background: #fbdcda; color: #b3261e; } .pill-off { background: #e6eaf1; color: #4a5568; }
.banner-warn { background: #fdecc8; color: #6b3a00; } .banner-bad { background: #fbdcda; color: #8c1d18; }
.banner-ok { background: #dff3e5; color: #0e5c2b; }
button { background: #ffffff; border: 1px solid #ccd4e0; color: #1b2430; }
button:hover { background: #eef2f9; }
button.suggested-action { background: #2a62d6; border-color: #2a62d6; }
button.suggested-action label { color: #ffffff; }
button.destructive-action { background: #fff; color: #b3261e; border-color: #e3b1ad; }
entry, combobox, .view, treeview { background: #ffffff; color: #1b2430; }
entry { border: 1px solid #ccd4e0; }
treeview header button { background: #eef2f9; color: #1b2430; border-radius: 0; border: none; border-bottom: 1px solid #dde3ec; padding: 6px 8px; font-weight: 700; }
headerbar { background: #ffffff; color: #1b2430; border-bottom: 1px solid #dde3ec; }
"""

CSS_DARK = """
window, .page { background: #11151c; color: #e6eaf2; }
.sidebar { background: #161b24; border-right: 1px solid #262e3b; }
.sidebar row:selected { background: #3b78f0; color: #ffffff; }
.sidebar row:selected label { color: #ffffff; }
.sidebar row:hover:not(:selected) { background: #1e2530; }
.sidebar label { color: #e6eaf2; }
.sidebar .brandsub { color: #98a3b5; }
.brandsub, .subtitle, .key { color: #98a3b5; }
.card { background: #1a2029; border: 1px solid #28303d; }
.section { color: #8592a6; }
.ok { color: #5fd38a; } .warn { color: #f2b04c; } .bad { color: #ff8a80; }
.pill-ok { background: #17382a; color: #5fd38a; } .pill-warn { background: #43320f; color: #f2b04c; }
.pill-bad { background: #4a1f1c; color: #ff8a80; } .pill-off { background: #262e3b; color: #a8b3c5; }
.banner-warn { background: #43320f; color: #f6cf8a; } .banner-bad { background: #4a1f1c; color: #ffb4ab; }
.banner-ok { background: #17382a; color: #8ee6ae; }
button { background: #222a36; border: 1px solid #343e4e; color: #e6eaf2; }
button:hover { background: #2b3544; }
button.suggested-action { background: #3b78f0; border-color: #3b78f0; }
button.suggested-action label { color: #ffffff; }
button.destructive-action { background: #222a36; color: #ff8a80; border-color: #6a3a37; }
entry, combobox, .view, treeview { background: #1f2630; color: #e6eaf2; }
entry { border: 1px solid #343e4e; }
treeview header button { background: #222a36; color: #e6eaf2; border-radius: 0; border: none; border-bottom: 1px solid #343e4e; padding: 6px 8px; font-weight: 700; }
headerbar { background: #161b24; color: #e6eaf2; border-bottom: 1px solid #262e3b; }
"""

CAT_COLORS = {"MAC": "#2a62d6", "NETWORK": "#0f8b8d", "DHCP": "#2f8f46", "DNS": "#7b5ea7", "ROUTING": "#8a6d1d",
              "SYSTEM": "#667085", "PROFILE": "#b35c9d", "ROTATION": "#c2410c", "ERROR": "#d92d20"}


def label(text="", css=None, xalign=0.0, wrap=False, selectable=False):
    l = Gtk.Label(label=text)
    l.set_xalign(xalign)
    for c in (css or "").split():
        l.get_style_context().add_class(c)
    if wrap:
        l.set_line_wrap(True)
        l.set_max_width_chars(80)
    l.set_selectable(selectable)
    return l


def card(title=None, subtitle=None):
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    b.get_style_context().add_class("card")
    if title:
        b.pack_start(label(title, "cardtitle"), False, False, 0)
    if subtitle:
        b.pack_start(label(subtitle, "subtitle", wrap=True), False, False, 0)
    return b


def kvgrid(rows, mono=()):
    g = Gtk.Grid(column_spacing=18, row_spacing=5)
    for i, (k, v) in enumerate(rows):
        g.attach(label(k, "key"), 0, i, 1, 1)
        g.attach(label(str(v), "mono" if k in mono else "", selectable=True), 1, i, 1, 1)
    return g


def pill(text, kind="off"):
    l = Gtk.Label(label=text)
    l.get_style_context().add_class("pill")
    l.get_style_context().add_class("pill-" + kind)
    l.set_halign(Gtk.Align.START)
    return l


def clear(box):
    for c in box.get_children():
        box.remove(c)


def button(text, cb, kind=None, tip=None):
    b = Gtk.Button(label=text)
    if kind:
        b.get_style_context().add_class(kind)
    b.connect("clicked", lambda *_: cb())
    if tip:
        b.set_tooltip_text(tip)
    return b


def scrolled(child):
    s = Gtk.ScrolledWindow()
    s.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    s.add(child)
    return s


def page_box():
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    b.set_border_width(24)
    b.get_style_context().add_class("page")
    return b


def heading(title, sub):
    h = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    h.pack_start(label(title, "title"), False, False, 0)
    h.pack_start(label(sub, "subtitle", wrap=True), False, False, 0)
    return h


def fmt_remaining(sec):
    if sec is None:
        return "--:--:--"
    sec = int(sec)
    return "%02d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def logo_pixbuf(height):
    """Load the supplied MAKAUT logo untouched; scale by height and keep the aspect ratio."""
    data = pkgutil.get_data("macout_app", "assets/makaut_logo.jpg")
    ld = GdkPixbuf.PixbufLoader()
    ld.write(data)
    ld.close()
    pb = ld.get_pixbuf()
    w = int(round(pb.get_width() * height / pb.get_height()))
    return pb.scale_simple(w, height, GdkPixbuf.InterpType.HYPER)
