"""Profiles and Rotation pages."""
from gi.repository import Gtk

from . import services
from .gui_common import *  # noqa: F401,F403


class Pages2:
    # ---- Profiles
    def build_profiles(self, box):
        box.pack_start(heading("Profiles", "A profile bundles a MAC strategy, persistence and rotation. Activating one applies it to the selected interface."), False, False, 0)
        row = Gtk.Box(spacing=14)
        left = card("Profiles")
        self.pf_store = Gtk.ListStore(str, str)
        self.pf_tv = Gtk.TreeView(model=self.pf_store)
        self.pf_tv.set_headers_visible(False)
        self.pf_tv.append_column(Gtk.TreeViewColumn("Name", Gtk.CellRendererText(), text=0))
        self.pf_tv.append_column(Gtk.TreeViewColumn("Status", Gtk.CellRendererText(), text=1))
        self.pf_tv.get_selection().connect("changed", self.on_profile_select)
        sw = scrolled(self.pf_tv)
        sw.set_min_content_height(220)
        sw.set_min_content_width(260)
        left.pack_start(sw, True, True, 0)
        b1 = Gtk.Box(spacing=6)
        for t, f in (("New", self.pf_new), ("Duplicate", self.pf_dup), ("Delete", self.pf_del)):
            b1.pack_start(button(t, f), False, False, 0)
        left.pack_start(b1, False, False, 0)
        b2 = Gtk.Box(spacing=6)
        b2.pack_start(button("Import", self.pf_import), False, False, 0)
        b2.pack_start(button("Export", self.pf_export), False, False, 0)
        left.pack_start(b2, False, False, 0)
        row.pack_start(left, False, False, 0)
        ed = card("Edit profile")
        g = Gtk.Grid(column_spacing=12, row_spacing=8)
        self.pf = {}
        def add(i, name, widget):
            g.attach(label(name, "key"), 0, i, 1, 1)
            g.attach(widget, 1, i, 1, 1)
        self.pf["name"] = Gtk.Entry()
        add(0, "Name", self.pf["name"])
        self.pf["interface"] = Gtk.ComboBoxText.new_with_entry()
        add(1, "Interface", self.pf["interface"])
        self.pf["strategy"] = Gtk.ComboBoxText()
        for k, v in services.STRATEGIES.items():
            self.pf["strategy"].append(k, v)
        add(2, "MAC strategy", self.pf["strategy"])
        self.pf["mac"] = Gtk.Entry()
        self.pf["mac"].set_placeholder_text("for 'Specific MAC'")
        add(3, "MAC value", self.pf["mac"])
        self.pf["vendor_oui"] = Gtk.Entry()
        self.pf["vendor_oui"].set_placeholder_text("AA:BB:CC for 'Vendor-specific'")
        add(4, "Vendor OUI", self.pf["vendor_oui"])
        self.pf["pattern"] = Gtk.Entry()
        add(5, "Pattern", self.pf["pattern"])
        self.pf["persistent"] = Gtk.CheckButton(label="Persistent (needs root)")
        add(6, "Persistence", self.pf["persistent"])
        self.pf["rot_enabled"] = Gtk.CheckButton(label="Rotate automatically")
        add(7, "Rotation", self.pf["rot_enabled"])
        self.pf["interval"] = Gtk.SpinButton.new_with_range(1, 1440, 1)
        add(8, "Interval (min)", self.pf["interval"])
        self.pf["reconnect"] = Gtk.CheckButton(label="Renew DHCP and verify connectivity after change")
        add(9, "Reconnect", self.pf["reconnect"])
        self.pf["log_level"] = Gtk.ComboBoxText()
        for v in services.VERBOSITY:
            self.pf["log_level"].append(v, v)
        add(10, "Logging", self.pf["log_level"])
        ed.pack_start(g, False, False, 0)
        self.pf_msg = label("", "key", wrap=True)
        ed.pack_start(self.pf_msg, False, False, 0)
        b3 = Gtk.Box(spacing=8)
        b3.pack_start(button("Save", self.pf_save), False, False, 0)
        b3.pack_start(button("Activate on interface", self.pf_activate, "suggested-action"), False, False, 0)
        b3.pack_start(button("Deactivate", self.pf_deactivate), False, False, 0)
        ed.pack_start(b3, False, False, 0)
        row.pack_start(ed, True, True, 0)
        box.pack_start(row, False, False, 0)
        self.pf_current = None
        return self.refresh_profiles

    def refresh_profiles(self):
        self.pf_store.clear()
        act = self.app.profiles.active_map()
        for p in self.app.profiles.list():
            on = [i for i, n in act.items() if n == p["name"]]
            self.pf_store.append([p["name"], ("● active on " + ", ".join(on)) if on else ""])
        self.pf["interface"].remove_all()
        for n in self.app.backend.list_interfaces():
            self.pf["interface"].append_text(n)
        if self.pf_current is None and len(self.pf_store):
            self.pf_tv.get_selection().select_path(Gtk.TreePath.new_first())

    def on_profile_select(self, sel):
        m, it = sel.get_selected()
        if not it:
            return
        p = self.app.profiles.get(m[it][0])
        if not p:
            return
        self.pf_current = p["name"]
        self.pf["name"].set_text(p["name"])
        self.pf["interface"].get_child().set_text(p.get("interface") or "")
        self.pf["strategy"].set_active_id(p["strategy"])
        self.pf["mac"].set_text(p.get("mac", ""))
        self.pf["vendor_oui"].set_text(p.get("vendor_oui", ""))
        self.pf["pattern"].set_text(p.get("pattern", ""))
        self.pf["persistent"].set_active(bool(p.get("persistent")))
        r = p.get("rotation", {})
        self.pf["rot_enabled"].set_active(bool(r.get("enabled")))
        self.pf["interval"].set_value(int(r.get("interval_min", 30)))
        self.pf["reconnect"].set_active(bool(p.get("reconnect", True)))
        self.pf["log_level"].set_active_id(p.get("log_level", "Normal"))
        self.pf_msg.set_text(p.get("notes", ""))

    def pf_collect(self):
        p = dict(self.app.profiles.get(self.pf_current) or services.new_profile())
        p.update(name=self.pf["name"].get_text().strip(), interface=self.pf["interface"].get_child().get_text().strip(),
                 strategy=self.pf["strategy"].get_active_id() or "random", mac=self.pf["mac"].get_text().strip(),
                 vendor_oui=self.pf["vendor_oui"].get_text().strip(), pattern=self.pf["pattern"].get_text().strip() or "02:xx:xx:xx:xx:xx",
                 persistent=self.pf["persistent"].get_active(), reconnect=self.pf["reconnect"].get_active(),
                 log_level=self.pf["log_level"].get_active_id() or "Normal")
        rot = dict(p.get("rotation", {}))
        rot.update(enabled=self.pf["rot_enabled"].get_active(), interval_min=int(self.pf["interval"].get_value()))
        p["rotation"] = rot
        return p

    def pf_save(self):
        try:
            p = self.pf_collect()
            old = self.pf_current
            self.app.profiles.save(p)
            if old and old != p["name"]:
                self.app.profiles.delete(old)
            self.pf_current = p["name"]
            self.pf_msg.set_text("Saved.")
        except ValueError as e:
            self.pf_msg.set_text("Not saved: %s" % e)
        self.refresh_profiles()

    def pf_new(self):
        n, i = "New profile", 2
        names = {p["name"] for p in self.app.profiles.list()}
        while n in names:
            n = "New profile %d" % i
            i += 1
        self.app.profiles.save(services.new_profile(n, interface=self.iface or ""))
        self.pf_current = n
        self.refresh_profiles()

    def pf_dup(self):
        if self.pf_current:
            self.app.profiles.duplicate(self.pf_current)
            self.refresh_profiles()

    def pf_del(self):
        if self.pf_current and self.confirm("Delete profile '%s'?" % self.pf_current):
            self.app.profiles.delete(self.pf_current)
            self.pf_current = None
            self.refresh_profiles()

    def file_dialog(self, title, save, name=""):
        d = Gtk.FileChooserDialog(title=title, parent=self, action=Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save" if save else "Open", Gtk.ResponseType.OK)
        if save:
            d.set_current_name(name)
            d.set_do_overwrite_confirmation(True)
        r = d.run()
        path = d.get_filename() if r == Gtk.ResponseType.OK else None
        d.destroy()
        return path

    def pf_export(self):
        if self.pf_current:
            p = self.file_dialog("Export profile", True, services.slug(self.pf_current) + ".macout.json")
            if p:
                self.app.profiles.export(self.pf_current, p)

    def pf_import(self):
        p = self.file_dialog("Import profile", False)
        if p:
            try:
                self.app.profiles.import_file(p)
            except ValueError as e:
                self.info("Import failed", str(e), Gtk.MessageType.WARNING)
            self.refresh_profiles()

    def pf_activate(self):
        self.pf_save()
        if not self.pf_current or not self.can_change():
            return
        if not self.confirm("Activate '%s' on %s?" % (self.pf_current, self.iface), "This applies the MAC strategy now."):
            return
        name, iface = self.pf_current, self.iface
        self.run_op(lambda: self.app.activate_profile(iface, name))

    def pf_deactivate(self):
        if self.iface:
            self.app.deactivate_profile(self.iface)
            self.refresh_profiles()

    # ---- Rotation
    def build_rotation(self, box):
        box.pack_start(heading("Rotation", "Change the MAC on a schedule or when the network reconnects. Every rotation is verified and logged."), False, False, 0)
        row = Gtk.Box(spacing=14)
        cfg = card("Schedule")
        g = Gtk.Grid(column_spacing=12, row_spacing=8)
        self.rot_interval = Gtk.ComboBoxText.new_with_entry()
        for t in ("5 minutes", "10 minutes", "15 minutes", "30 minutes", "1 hour", "6 hours"):
            self.rot_interval.append_text(t)
        self.rot_interval.set_active(3)
        g.attach(label("Every", "key"), 0, 0, 1, 1)
        g.attach(self.rot_interval, 1, 0, 1, 1)
        g.attach(label("or type minutes for Custom", "key"), 2, 0, 1, 1)
        self.rot_strategy = Gtk.ComboBoxText()
        for k in ("random", "vendor", "local", "pattern"):
            self.rot_strategy.append(k, services.STRATEGIES[k])
        self.rot_strategy.set_active_id("random")
        g.attach(label("Strategy", "key"), 0, 1, 1, 1)
        g.attach(self.rot_strategy, 1, 1, 1, 1)
        self.rot_extra = Gtk.Entry()
        self.rot_extra.set_placeholder_text("OUI (AA:BB:CC) or pattern (02:xx:xx:xx:xx:xx)")
        self.rot_extra.set_width_chars(36)
        g.attach(label("OUI / pattern", "key"), 0, 2, 1, 1)
        g.attach(self.rot_extra, 1, 2, 2, 1)
        cfg.pack_start(g, False, False, 0)
        cfg.pack_start(label("Also rotate", "section"), False, False, 4)
        self.rot_trig = {}
        for k, t in (("on_wifi_reconnect", "On Wi-Fi reconnect"), ("on_nm_reconnect", "On NetworkManager reconnect"),
                     ("on_iface_restart", "On interface restart"), ("on_resume", "On system resume"), ("on_start", "On application start")):
            cb = Gtk.CheckButton(label=t)
            self.rot_trig[k] = cb
            cfg.pack_start(cb, False, False, 0)
        row.pack_start(cfg, False, False, 0)
        st = card("Status")
        st.pack_start(label("Next rotation", "key"), False, False, 0)
        self.rot_clock = label("--:--:--", "countdown")
        st.pack_start(self.rot_clock, False, False, 0)
        self.rot_state = label("Not running", "subtitle")
        st.pack_start(self.rot_state, False, False, 0)
        b = Gtk.Box(spacing=8)
        b.pack_start(button("Start", self.start_rotation, "suggested-action"), False, False, 0)
        b.pack_start(button("Pause / Resume", self.pause_rotation), False, False, 0)
        b.pack_start(button("Rotate now", self.rotate_now), False, False, 0)
        b.pack_start(button("Stop", self.stop_rotation), False, False, 0)
        st.pack_start(b, False, False, 0)
        row.pack_start(st, True, True, 0)
        box.pack_start(row, False, False, 0)
        hc = card("Rotation history")
        self.rot_hist = Gtk.ListStore(str, str, str, str, str)
        tv = Gtk.TreeView(model=self.rot_hist)
        for i, t in enumerate(("Time", "Interface", "Old MAC", "New MAC", "Result")):
            tv.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i))
        sw = scrolled(tv)
        sw.set_min_content_height(200)
        hc.pack_start(sw, True, True, 0)
        box.pack_start(hc, True, True, 0)
        return self.refresh_rotation

    def refresh_rotation(self):
        self.rot_hist.clear()
        for h in reversed(self.app.history.all()):
            if "Rotation" in str(h.get("operation")):
                self.rot_hist.append([h.get("time", ""), h.get("iface", ""), h.get("old_mac") or "", h.get("new_mac") or "", (h.get("result") or "")[:60]])
            if len(self.rot_hist) >= 50:
                break

    def parse_interval(self):
        t = (self.rot_interval.get_active_text() or "").strip().lower()
        num = "".join(ch for ch in t if ch.isdigit())
        if not num:
            raise ValueError("Enter an interval like 15 or '30 minutes'")
        n = int(num)
        return n * 60 if "hour" in t else n

    def rotation_profile(self):
        strat = self.rot_strategy.get_active_id()
        extra = self.rot_extra.get_text().strip()
        p = services.new_profile("Rotation (manual)", interface=self.iface, strategy=strat)
        if strat == "vendor":
            p["vendor_oui"] = extra
        if strat == "pattern":
            p["pattern"] = extra or "02:xx:xx:xx:xx:xx"
        p["rotation"].update({k: cb.get_active() for k, cb in self.rot_trig.items()})
        errs = services.validate_profile(p)
        if errs:
            raise ValueError("; ".join(errs))
        return p

    def start_rotation(self):
        if not self.can_change():
            return
        try:
            iv = self.parse_interval()
            p = self.rotation_profile()
            if not self.confirm("Start rotating the MAC on %s every %d minutes?" % (self.iface, iv), "Your connection will drop briefly at each rotation."):
                return
            self.app.rotation.start_rotation(self.iface, p, iv)
        except ValueError as e:
            self.info("Cannot start rotation", str(e), Gtk.MessageType.WARNING)

    def stop_rotation(self):
        if self.iface:
            self.app.rotation.stop_rotation(self.iface)

    def pause_rotation(self):
        st = self.app.rotation.status(self.iface) if self.iface else None
        if st:
            self.app.rotation.pause(self.iface, not st["paused"])

    def rotate_now(self):
        if not self.can_change():
            return
        if not self.app.rotation.status(self.iface):
            self.info("Start rotation first", "Manual rotation uses the settings of the running rotation.")
            return
        iface = self.iface
        self.run_op(lambda: self.app.rotation.rotate_now(iface) or {"ok": False, "message": "A rotation is already running"})
