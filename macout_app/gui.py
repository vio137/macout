"""GTK3 front end. Talks only to services.App and never runs commands itself."""
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from . import core  # noqa: E402
from .backend import BackendError  # noqa: E402
from .gui_common import *  # noqa: E402,F401,F403
from .pages1 import Pages1  # noqa: E402
from .pages2 import Pages2  # noqa: E402
from .pages3 import Pages3  # noqa: E402


class MacOutWindow(Pages1, Pages2, Pages3, Gtk.Window):
    def __init__(self, app):
        Gtk.Window.__init__(self, title="MAC-OUT")
        self.app = app
        self.set_default_size(1200, 780)
        self.iface = None
        self.busy = False
        self.last_result = None
        self.snaps = {}
        self.tick_n = 0
        self.dark = False
        self.css_provider = Gtk.CssProvider()
        common = Gtk.CssProvider()
        common.load_from_data(CSS_COMMON.encode())
        scr = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(scr, common, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.StyleContext.add_provider_for_screen(scr, self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.apply_theme(app.settings.get("theme"))

        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title("MAC-OUT")
        hb.set_subtitle(core.TAGLINE)
        self.set_titlebar(hb)
        self.iface_combo = Gtk.ComboBoxText()
        self.iface_combo.set_tooltip_text("Interface that MAC Control, Rotation and Observer act on")
        self.iface_combo.connect("changed", self.on_iface_changed)
        hb.pack_start(label("Interface ", "key"))
        hb.pack_start(self.iface_combo)
        root_ok = app.env["root"]
        p = pill("ROOT" if root_ok else "READ-ONLY (not root)", "ok" if root_ok else "warn")
        p.set_tooltip_text("Changing a MAC address needs root. Start with: sudo ./macout")
        hb.pack_end(p)
        hb.pack_end(button("Dark / Light", self.toggle_theme, tip="Switch theme"))

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(outer)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        side.get_style_context().add_class("sidebar")
        side.set_size_request(210, -1)
        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top.set_border_width(8)
        top.pack_start(label("MAC-OUT", "brand"), False, False, 0)
        top.pack_start(label("Network Identity Observatory", "brandsub"), False, False, 0)
        side.pack_start(top, False, False, 6)
        self.nav = Gtk.ListBox()
        self.nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for name in PAGES:
            row = Gtk.ListBoxRow()
            row.add(label(name))
            row.page = name
            self.nav.add(row)
        self.nav.connect("row-selected", self.on_nav)
        side.pack_start(self.nav, True, True, 0)
        lg = Gtk.Image.new_from_pixbuf(logo_pixbuf(96))
        lg.set_halign(Gtk.Align.CENTER)
        lg.set_tooltip_text("Maulana Abul Kalam Azad University of Technology, West Bengal")
        side.pack_end(lg, False, False, 10)
        outer.pack_start(side, False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(160)
        outer.pack_start(self.stack, True, True, 0)

        self.builders = {}
        for name in PAGES:
            box = page_box()
            self.stack.add_named(scrolled(box), name)
            self.builders[name] = getattr(self, "build_" + name.lower().replace(" ", "_"))(box)
        self.load_interfaces()
        for rec in app.log.visible()[-50:]:
            self.on_event(rec)
        self.bg(self.collect_snaps, self.on_snaps)
        app.log.listeners.append(lambda rec: GLib.idle_add(self.on_event, rec))
        GLib.timeout_add_seconds(1, self.tick)
        start = app.settings.get("startup_page")
        self.nav.select_row(self.nav.get_row_at_index(PAGES.index(start) if start in PAGES else 0))
        self.connect("destroy", self.on_quit)
        self.show_all()
        if not app.settings.get("first_run_done"):
            GLib.idle_add(self.first_run)

    # ---- infrastructure
    def apply_theme(self, mode):
        if mode == "system":
            mode = "dark" if Gtk.Settings.get_default().get_property("gtk-application-prefer-dark-theme") else "light"
        self.dark = mode == "dark"
        self.css_provider.load_from_data((CSS_DARK if self.dark else CSS_LIGHT).encode())

    def toggle_theme(self):
        mode = "light" if self.dark else "dark"
        self.app.settings.set("theme", mode)
        self.apply_theme(mode)

    def on_quit(self, *_):
        self.app.rotation.shutdown()
        self.app.sessions.stop()
        Gtk.main_quit()

    def bg(self, fn, done=None):
        def run():
            try:
                r, err = fn(), None
            except Exception as e:  # show errors instead of dying silently in a thread
                r, err = None, e
            if done:
                GLib.idle_add(done, r, err)
        threading.Thread(target=run, daemon=True).start()

    def confirm(self, text, detail=""):
        if not self.app.settings.get("confirm_actions"):
            return True
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.NONE, text=text)
        d.format_secondary_text(detail)
        d.add_button("Cancel", Gtk.ResponseType.CANCEL)
        d.add_button("Continue", Gtk.ResponseType.OK)
        r = d.run()
        d.destroy()
        return r == Gtk.ResponseType.OK

    def info(self, text, detail="", kind=Gtk.MessageType.INFO):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=kind, buttons=Gtk.ButtonsType.OK, text=text)
        d.format_secondary_text(detail)
        d.run()
        d.destroy()

    def can_change(self):
        if not self.app.env["root"]:
            self.info("Root is required", "Changing a MAC address needs root. Close MAC-OUT and start it with:\n\nsudo ./macout", Gtk.MessageType.WARNING)
            return False
        if not self.app.backend.macchanger:
            self.info("macchanger is missing", "Install it with:\n\nsudo apt install macchanger", Gtk.MessageType.WARNING)
            return False
        if not self.iface:
            self.info("No interface selected")
            return False
        return True

    def load_interfaces(self):
        cur = self.iface
        self.iface_combo.remove_all()
        names = self.app.backend.list_interfaces()
        for n in names:
            self.iface_combo.append_text(n)
        pick = cur if cur in names else self.pick_default(names)
        if pick:
            self.iface_combo.set_active(names.index(pick))

    def pick_default(self, names):
        for n in names:
            if self.app.backend.iface_type(n) == "Wi-Fi":
                return n
        for n in names:
            try:
                if self.app.backend.link_info(n)["up"]:
                    return n
            except BackendError:
                pass
        return names[0] if names else None

    def on_iface_changed(self, combo):
        self.iface = combo.get_active_text()
        self.refresh_all()

    def on_nav(self, lb, row):
        if row:
            self.stack.set_visible_child_name(row.page)
            self.refresh_page(row.page)

    def refresh_all(self):
        for name in PAGES:
            self.refresh_page(name)

    def refresh_page(self, name):
        fn = self.builders.get(name)
        if callable(fn):
            fn()

    def snap(self, iface=None):
        return self.snaps.get(iface or self.iface)

    def health_of(self, s):
        h = self.app.observer.health(s)
        return h, {"HEALTHY": "ok", "DEGRADED": "warn", "DOWN": "bad", "UNKNOWN": "off"}[h]

    def set_status(self, text):
        self.get_titlebar().set_subtitle(text or core.TAGLINE)

    def run_op(self, fn):
        if self.busy:
            return
        self.busy = True
        self.set_status("Working...")
        def done(res, err):
            self.busy = False
            self.set_status("")
            if err:
                self.info("Unexpected error", str(err), Gtk.MessageType.ERROR)
                return
            if res is None:
                return
            self.last_result = res
            self.show_result(res)
            def after(s, e):
                self.on_snaps(s, e)
                self.refresh_all()
            self.bg(self.collect_snaps, after)
        self.bg(fn, done)

    # ---- live events and polling
    def on_event(self, rec):
        for ls in (self.tl_store, self.tl_dash):
            ls.append([rec["time"][11:], rec["category"], rec["message"], CAT_COLORS.get(rec["category"], "#667085")])
            if len(ls) > 400:
                ls.remove(ls.get_iter_first())
        self.refresh_logs_if_visible()
        if rec["category"] in ("ROTATION", "MAC") and self.stack.get_visible_child_name() in ("Rotation", "History"):
            GLib.timeout_add(600, lambda: (self.refresh_page(self.stack.get_visible_child_name()), False)[1])
        return False

    def timeline_view(self, store, height=260):
        tv = Gtk.TreeView(model=store)
        tv.set_headers_visible(False)
        tv.set_can_focus(False)
        r = Gtk.CellRendererText()
        r.set_property("family", "DejaVu Sans Mono")
        tv.append_column(Gtk.TreeViewColumn("Time", r, text=0))
        r2 = Gtk.CellRendererText()
        r2.set_property("weight", 700)
        r2.set_property("size-points", 9)
        tv.append_column(Gtk.TreeViewColumn("Cat", r2, text=1, foreground=3))
        tv.append_column(Gtk.TreeViewColumn("Event", Gtk.CellRendererText(), text=2))
        sw = scrolled(tv)
        sw.set_min_content_height(height)
        store.connect("row-inserted", lambda s, p, i: GLib.idle_add(lambda: tv.scroll_to_cell(p) or False))
        return sw

    def tick(self):
        self.tick_n += 1
        self.update_countdown()
        if self.tick_n % max(2, int(self.app.settings.get("diag_interval_sec"))) == 0 and not self.busy:
            self.bg(self.collect_snaps, self.on_snaps)
        return True

    def collect_snaps(self):
        out = {}
        full = self.tick_n % 30 == 0 or not self.snaps
        for n in self.app.backend.list_interfaces():
            try:
                s = self.app.observer.snapshot(n, connectivity=(full and n == self.iface))
                if not (full and n == self.iface) and n in self.snaps:
                    for k in ("dns", "internet_v4", "internet_v6", "gateway_reachable"):
                        if k in self.snaps[n]:
                            s[k] = self.snaps[n][k]
                out[n] = s
            except BackendError:
                pass
        return out

    def on_snaps(self, snaps, err):
        if snaps:
            self.snaps = snaps
            cur = self.stack.get_visible_child_name()
            if cur in ("Dashboard", "Interfaces", "Network Observer", "MAC Control"):
                self.refresh_page(cur)

    def update_countdown(self):
        if not self.iface:
            return
        st = self.app.rotation.status(self.iface)
        txt = fmt_remaining(st["remaining"]) if st else "--:--:--"
        self.rot_clock.set_text(txt + ("  (paused)" if st and st["paused"] else ""))
        self.rot_state.set_text(("ACTIVE, %d rotations done" % st["count"]) if st else "Not running")
        self.dash_rot.set_text(("ACTIVE, next rotation in " + txt) if st else "Not running")


def main(app):
    MacOutWindow(app)
    Gtk.main()
