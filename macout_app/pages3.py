"""Observer, Diagnostics, History, Logs, Reports, Settings, About and first-run."""
from gi.repository import Gtk

from . import core, services
from .gui_common import *  # noqa: F401,F403


class Pages3:
    # ---- Network Observer
    def build_network_observer(self, box):
        box.pack_start(heading("Network Observer", "Observed network behavior on this machine. MAC-OUT cannot see what your router, ISP or a campus NAC system records about you."), False, False, 0)
        self.obs_cards = Gtk.Box(spacing=12)
        box.pack_start(self.obs_cards, False, False, 0)
        self.ba_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(self.ba_box, False, False, 0)
        sc = card("Session recording", "Record everything MAC-OUT does and observes, then get a summary.")
        r = Gtk.Box(spacing=8)
        self.rec_btn = button("Start Recording", self.toggle_recording)
        r.pack_start(self.rec_btn, False, False, 0)
        self.rec_label = label("", "mono")
        r.pack_start(self.rec_label, False, False, 6)
        sc.pack_start(r, False, False, 0)
        self.rec_summary = label("", "mono", selectable=True)
        sc.pack_start(self.rec_summary, False, False, 0)
        box.pack_start(sc, False, False, 0)
        tc = card("Event timeline")
        self.tl_store = Gtk.ListStore(str, str, str, str)
        tc.pack_start(self.timeline_view(self.tl_store, 240), True, True, 0)
        box.pack_start(tc, True, True, 0)
        return self.refresh_observer

    def yn(self, v):
        return "not tested" if v is None else ("OK" if v else "Failed")

    def refresh_observer(self):
        clear(self.obs_cards)
        s = self.snap()
        if not s:
            return
        w = s.get("wifi") or {}
        l2 = card("Layer 2")
        rows = [("Link", s["state"]), ("Association", s["association"]), ("MAC", self.display_mac(s["mac"]))]
        if s.get("wifi") is not None:
            rows += [("SSID", w.get("ssid") or "n/a"), ("BSSID", w.get("bssid") or "n/a"),
                     ("Signal", ("%s dBm" % w["signal"]) if w.get("signal") is not None else "n/a")]
        l2.pack_start(kvgrid(rows, mono=("MAC", "BSSID")), False, False, 0)
        l3 = card("Layer 3")
        l3.pack_start(kvgrid([("DHCP", s["dhcp"]), ("IPv4", ", ".join(s["ipv4"]) or "none"), ("IPv6", ", ".join(s["ipv6"]) or "none"),
                              ("Gateway", s.get("gateway") or "none"), ("Neighbors", str(len(self.app.backend.neighbors(self.iface))))]), False, False, 0)
        cn = card("Connectivity")
        h, k = self.health_of(s)
        cn.pack_start(pill("● " + h, k), False, False, 0)
        cn.pack_start(kvgrid([("Gateway ping", self.yn(s.get("gateway_reachable"))), ("DNS", self.yn(s.get("dns"))),
                              ("IPv4 Internet", self.yn(s.get("internet_v4"))), ("IPv6 Internet", self.yn(s.get("internet_v6")))]), False, False, 0)
        for c in (l2, l3, cn):
            self.obs_cards.pack_start(c, True, True, 0)
        self.obs_cards.show_all()
        self.refresh_ba()
        rec = self.app.sessions.active
        self.rec_btn.set_label("Stop Recording" if rec else "Start Recording")
        self.rec_label.set_text(("● Recording session #%d" % rec["id"]) if rec else "")

    def refresh_ba(self):
        clear(self.ba_box)
        r = self.last_result
        if not r or not r.get("before") or not r.get("after"):
            return
        c = card("Before / After the last MAC change")
        row = Gtk.Box(spacing=40)
        for title, s in (("BEFORE", r["before"]), ("AFTER", r["after"])):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            col.pack_start(label(title, "section"), False, False, 0)
            col.pack_start(kvgrid([("MAC", self.display_mac(s["mac"])), ("Association", s["association"]), ("DHCP", s["dhcp"]), ("IPv4", ", ".join(s["ipv4"]) or "none"),
                                   ("Gateway", s.get("gateway") or "none"), ("DNS", self.yn(s.get("dns"))), ("Internet", self.yn(s.get("internet_v4")))],
                                  mono=("MAC",)), False, False, 0)
            row.pack_start(col, False, False, 0)
        c.pack_start(row, False, False, 0)
        c.pack_start(label(r.get("message", ""), "banner banner-ok" if r.get("ok") and not r.get("degraded") else "banner banner-warn", wrap=True), False, False, 0)
        self.ba_box.pack_start(c, False, False, 0)
        self.ba_box.show_all()

    def toggle_recording(self):
        if self.app.sessions.active:
            s = self.app.sessions.stop()
            sm = s["summary"]
            avg = ("%.1f seconds" % sm["avg_reconnect_seconds"]) if sm["avg_reconnect_seconds"] is not None else "n/a"
            self.rec_summary.set_text("Session #%d\nMAC changes: %d\nSuccessful: %d\nFailed: %d\nAverage reconnection: %s\nConnectivity failures: %d" % (
                s["id"], sm["mac_changes"], sm["successful"], sm["failed"], avg, sm["connectivity_failures"]))
        else:
            self.rec_summary.set_text("")
            self.app.sessions.start()
        self.refresh_observer()

    # ---- Diagnostics
    def build_diagnostics(self, box):
        box.pack_start(heading("Diagnostics", "Checks the tools, permissions and network state, with a suggested fix for anything that is off."), False, False, 0)
        rb = button("Run diagnostics", self.run_diag, "suggested-action")
        rb.set_halign(Gtk.Align.START)
        box.pack_start(rb, False, False, 0)
        self.diag_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.pack_start(self.diag_box, False, False, 0)
        return None

    def run_diag(self):
        clear(self.diag_box)
        self.diag_box.pack_start(label("Running checks...", "subtitle"), False, False, 0)
        self.diag_box.show_all()
        iface = self.iface
        def done(res, err):
            clear(self.diag_box)
            if err:
                self.diag_box.pack_start(label(str(err), "banner banner-bad"), False, False, 0)
            else:
                c = card("MAC-OUT Diagnostics")
                mark = {"ok": ("✓", "ok"), "warn": ("!", "warn"), "fail": ("✗", "bad")}
                for r in res:
                    m, cls = mark[r["status"]]
                    line = Gtk.Box(spacing=10)
                    line.pack_start(label("[%s]" % m, "mono " + cls), False, False, 0)
                    line.pack_start(label(r["name"]), False, False, 0)
                    line.pack_start(label(r["detail"], "key"), False, False, 6)
                    c.pack_start(line, False, False, 0)
                    if r["advice"]:
                        c.pack_start(label("    Suggested action: " + r["advice"], "bad" if r["status"] == "fail" else "warn", wrap=True), False, False, 0)
                    if r["advanced"]:
                        ex = Gtk.Expander(label="Advanced details")
                        ex.add(label(r["advanced"], "mono", selectable=True))
                        c.pack_start(ex, False, False, 0)
                self.diag_box.pack_start(c, False, False, 0)
                self.app.log.emit("SYSTEM", "Diagnostics run: %d checks, %d need attention" % (len(res), sum(1 for r in res if r["status"] != "ok")))
            self.diag_box.show_all()
        self.bg(lambda: services.run_diagnostics(self.app.backend, self.app.observer, self.app.env, iface), done)

    # ---- History
    def build_history(self, box):
        box.pack_start(heading("History", "Every MAC operation MAC-OUT performed, with the result and how long it took."), False, False, 0)
        bar = Gtk.Box(spacing=8)
        self.h_range = Gtk.ComboBoxText()
        for k in ("Today", "Last 7 days", "Last 30 days", "All time", "Custom (days)"):
            self.h_range.append_text(k)
        self.h_range.set_active(3)
        self.h_range.connect("changed", lambda *_: self.refresh_history())
        bar.pack_start(self.h_range, False, False, 0)
        self.h_days = Gtk.SpinButton.new_with_range(1, 3650, 1)
        self.h_days.set_value(14)
        self.h_days.connect("value-changed", lambda *_: self.refresh_history())
        bar.pack_start(self.h_days, False, False, 0)
        self.h_search = Gtk.SearchEntry()
        self.h_search.set_placeholder_text("Search history")
        self.h_search.connect("search-changed", lambda *_: self.refresh_history())
        bar.pack_start(self.h_search, True, True, 0)
        bar.pack_start(button("Export CSV", self.export_history), False, False, 0)
        bar.pack_start(button("Clear history", self.clear_history, "destructive-action"), False, False, 0)
        box.pack_start(bar, False, False, 0)
        self.h_store = Gtk.ListStore(str, str, str, str, str, str, str, str)
        tv = Gtk.TreeView(model=self.h_store)
        for i, t in enumerate(("Time", "Interface", "Old MAC", "New MAC", "Profile", "Operation", "Result", "Duration")):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            tv.append_column(col)
        sw = scrolled(tv)
        sw.set_min_content_height(420)
        box.pack_start(sw, True, True, 0)
        self.h_count = label("", "key")
        box.pack_start(self.h_count, False, False, 0)
        return self.refresh_history

    def history_rows(self):
        sel = self.h_range.get_active_text()
        days = {"Today": 1, "Last 7 days": 7, "Last 30 days": 30, "Custom (days)": int(self.h_days.get_value())}.get(sel)
        return self.app.history.query(days=days, text=self.h_search.get_text())

    def refresh_history(self):
        self.h_store.clear()
        rows = self.history_rows()
        for r in reversed(rows):
            self.h_store.append([r.get("time", ""), r.get("iface", ""), self.display_mac(r.get("old_mac")), self.display_mac(r.get("new_mac")), r.get("profile", ""),
                                 r.get("operation", ""), (r.get("result") or "")[:70], "%ss" % r.get("duration", "")])
        self.h_count.set_text("%d entries. Retention: %s days (Settings > Privacy)." % (len(rows), self.app.settings.get("history_retention_days")))

    def export_history(self):
        p = self.file_dialog("Export history", True, "macout-history.csv")
        if p:
            with open(p, "w") as f:
                f.write(self.app.history.to_csv(self.history_rows()))

    def clear_history(self):
        if self.confirm("Delete all history?", "This cannot be undone."):
            self.app.history.clear()
            self.refresh_history()

    # ---- Logs
    def build_logs(self, box):
        box.pack_start(heading("Logs", "Structured log records. Verbosity is set here or in Settings > Logging."), False, False, 0)
        bar = Gtk.Box(spacing=8)
        self.l_cat = Gtk.ComboBoxText()
        self.l_cat.append_text("All categories")
        for c in services.CATEGORIES:
            self.l_cat.append_text(c)
        self.l_cat.set_active(0)
        self.l_cat.connect("changed", lambda *_: self.refresh_logs())
        bar.pack_start(self.l_cat, False, False, 0)
        bar.pack_start(label("Verbosity", "key"), False, False, 6)
        self.l_verb = Gtk.ComboBoxText()
        for v in services.VERBOSITY:
            self.l_verb.append_text(v)
        self.l_verb.set_active(list(services.VERBOSITY).index(self.app.settings.get("verbosity")))
        self.l_verb.connect("changed", self.on_verbosity)
        bar.pack_start(self.l_verb, False, False, 0)
        box.pack_start(bar, False, False, 0)
        self.l_store = Gtk.ListStore(str, str, str, str, str)
        tv = Gtk.TreeView(model=self.l_store)
        for i, t in enumerate(("Time", "Level", "Category", "Interface", "Message")):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            tv.append_column(col)
        sw = scrolled(tv)
        sw.set_min_content_height(480)
        box.pack_start(sw, True, True, 0)
        return self.refresh_logs

    def on_verbosity(self, c):
        v = c.get_active_text()
        self.app.settings.set("verbosity", v)
        self.app.log.set_verbosity(v)
        self.refresh_logs()

    def refresh_logs_if_visible(self):
        if self.stack.get_visible_child_name() == "Logs":
            self.refresh_logs()

    def refresh_logs(self):
        self.l_store.clear()
        cat = self.l_cat.get_active_text()
        for r in self.app.log.visible(None if cat in (None, "All categories") else cat)[-500:]:
            self.l_store.append([r["time"], r["level"], r["category"], r.get("iface") or "", self.display_text(r["message"])])

    # ---- Reports
    def build_reports(self, box):
        box.pack_start(heading("Reports", "Export a diagnostic report. Decide what gets removed before it leaves this machine."), False, False, 0)
        pc = card("Export Privacy", "Reports can end up with instructors, classmates or online forums. Tick what to remove.")
        self.rp = {}
        for k, t in (("redact_ip_public", "Redact public IP"), ("redact_ip_local", "Redact local IP"), ("redact_bssid", "Redact BSSID"),
                     ("redact_ssid", "Redact SSID"), ("redact_perm_mac", "Redact permanent MAC"), ("redact_cur_mac", "Redact current MAC"),
                     ("include_system", "Include system information (OS, kernel, architecture)")):
            cb = Gtk.CheckButton(label=t)
            cb.set_active(bool(self.app.settings.get(k)))
            cb.connect("toggled", lambda *_: self.update_redaction_text())
            self.rp[k] = cb
            pc.pack_start(cb, False, False, 0)
        self.rp_text = label("", "key", wrap=True)
        pc.pack_start(self.rp_text, False, False, 4)
        box.pack_start(pc, False, False, 0)
        ec = card("Export")
        r = Gtk.Box(spacing=8)
        self.rp_fmt = Gtk.ComboBoxText()
        for f in ("HTML", "TXT", "JSON", "CSV", "ZIP"):
            self.rp_fmt.append_text(f)
        self.rp_fmt.set_active(0)
        r.pack_start(self.rp_fmt, False, False, 0)
        r.pack_start(button("Export report...", self.export_report, "suggested-action"), False, False, 0)
        ec.pack_start(r, False, False, 0)
        self.rp_export_btn = r.get_children()[-1]
        self.rp_msg = label("Choose a format, then save to your Downloads folder or another location.", "key", wrap=True, selectable=True)
        self.last_export = None
        actions = Gtk.Box(spacing=8)
        self.rp_open_btn = button("Open report", lambda: self.open_report(False))
        self.rp_folder_btn = button("Show folder", lambda: self.open_report(True))
        for btn in (self.rp_open_btn, self.rp_folder_btn):
            btn.set_sensitive(False)
            actions.pack_start(btn, False, False, 0)
        ec.pack_start(actions, False, False, 0)
        ec.pack_start(self.rp_msg, False, False, 0)
        ec.pack_start(label("ZIP contains all four other formats. The report covers all interfaces.", "key"), False, False, 0)
        box.pack_start(ec, False, False, 0)
        self.update_redaction_text()
        return None

    def rp_opts(self):
        return {k: cb.get_active() for k, cb in self.rp.items()}

    def update_redaction_text(self):
        self.rp_text.set_text(services.redaction_summary(self.rp_opts()))

    def open_report(self, folder=False):
        if not self.last_export:
            return
        def done(r, err):
            if err:
                self.rp_msg.set_text("Saved: %s\nCould not open automatically: %s\nOpen the saved file from your file manager." % (self.last_export, err))
        self.bg(lambda: services.open_export(self.last_export, folder), done)

    def export_report(self, path=None):
        fmt = self.rp_fmt.get_active_text().lower()
        try:
            p = path or self.file_dialog("Export report", True, "macout-report." + fmt)
            if not p:
                return
            if not p.lower().endswith("." + fmt):
                p += "." + fmt
                import os
                if os.path.exists(p) and not self.confirm("Replace existing report?", p):
                    return
            opts = self.rp_opts()
            self.app.settings.data.update(opts)
            self.app.settings.save()
        except Exception as err:
            self.rp_msg.set_text("Export failed: %s" % err)
            return
        self.rp_export_btn.set_sensitive(False)
        self.rp_open_btn.set_sensitive(False)
        self.rp_folder_btn.set_sensitive(False)
        self.rp_msg.set_text("Generating %s report. Checking all interfaces; this can take a few seconds..." % fmt.upper())
        def done(r, err):
            self.rp_export_btn.set_sensitive(True)
            if err:
                self.rp_msg.set_text("Export failed: %s\nChoose a writable folder and try again." % err)
            else:
                self.last_export = r
                self.rp_open_btn.set_sensitive(True)
                self.rp_folder_btn.set_sensitive(True)
                self.rp_msg.set_text("Saved: %s\nOwned by your desktop user, private to that user.\n%s" % (r, services.redaction_summary(opts)))
        self.bg(lambda: self.app.reports.export(fmt, p, opts=opts), done)

    # ---- Settings
    def build_settings(self, box):
        box.pack_start(heading("Settings", "Defaults are safe. Anything risky is explained next to the setting."), False, False, 0)
        s = self.app.settings
        def combo(vals, key):
            c = Gtk.ComboBoxText()
            for v in vals:
                c.append_text(v)
            c.set_active(vals.index(s.get(key)) if s.get(key) in vals else 0)
            c.connect("changed", lambda w: s.set(key, w.get_active_text()))
            return c
        def spin(lo, hi, key):
            w = Gtk.SpinButton.new_with_range(lo, hi, 1)
            w.set_value(int(s.get(key)))
            w.connect("value-changed", lambda x: s.set(key, int(x.get_value())))
            return w
        def sw(key):
            w = Gtk.Switch()
            w.set_active(bool(s.get(key)))
            w.set_halign(Gtk.Align.START)
            w.connect("notify::active", lambda x, _: s.set(key, x.get_active()))
            return w
        def section(title, rows):
            c = card(title)
            g = Gtk.Grid(column_spacing=16, row_spacing=8)
            for i, (name, w, note) in enumerate(rows):
                g.attach(label(name), 0, i, 1, 1)
                g.attach(w, 1, i, 1, 1)
                g.attach(label(note, "key", wrap=True), 2, i, 1, 1)
            c.pack_start(g, False, False, 0)
            box.pack_start(c, False, False, 0)
        tc = combo(["system", "light", "dark"], "theme")
        tc.connect("changed", lambda w: (self.apply_theme(w.get_active_text()), self.refresh_all()))
        section("General", [("Theme", tc, "Follows the system by default."), ("Open on page", combo(PAGES, "startup_page"), ""),
                            ("Confirm before changes", sw("confirm_actions"), "Asks before anything that drops the connection.")])
        e = self.app.env
        section("Network", [("Network backend", label("NetworkManager" if e["network_manager"] else "none detected"), "Detected automatically."),
                            ("systemd", label("yes" if e["systemd"] else "no"), "Used for boot-time persistence when NetworkManager is absent."),
                            ("Refresh every (s)", spin(2, 60, "diag_interval_sec"), "How often interface state is read."),
                            ("Reconnect timeout (s)", spin(5, 120, "reconnect_timeout_sec"), "How long MAC-OUT waits for an address after a change.")])
        section("Rotation", [("Minimum interval (min)", spin(1, 60, "min_rotation_minutes"), "Safeguard. Very short intervals keep dropping your connection and can look suspicious to a network.")])
        section("Logging", [("Verbosity", combo(list(services.VERBOSITY), "verbosity"), "Also settable on the Logs page."),
                            ("Keep logs (days)", spin(1, 3650, "log_retention_days"), "Older records are deleted at startup."),
                            ("Log file", label(self.app.log.path, "mono", selectable=True), "Logs contain MAC addresses and interface names.")])
        section("Privacy", [("Keep history (days)", spin(1, 3650, "history_retention_days"), "Older history is deleted at startup."),
                            ("Data folder", label(self.app.base, "mono", selectable=True), "Everything MAC-OUT stores lives here, owner-only permissions.")])
        pe = Gtk.Entry()
        pe.set_text(s.get("macchanger_path") or "")
        pe.set_placeholder_text("auto-detect")
        pe.connect("changed", lambda w: s.set("macchanger_path", w.get_text().strip()))
        section("Advanced", [("macchanger path", pe, "Leave empty to auto-detect. Takes effect after restart."),
                             ("Backend", label("macchanger + iproute2" + (" + NetworkManager" if e["network_manager"] else "")), "Commands run as argument lists, never through a shell."),
                             ("Debug mode", sw("debug"), "Takes effect after restart.")])
        return None

    # ---- About
    def build_about(self, box):
        c = card()
        row = Gtk.Box(spacing=28)
        row.pack_start(Gtk.Image.new_from_pixbuf(logo_pixbuf(170)), False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        col.pack_start(label("MAC-OUT", "title"), False, False, 0)
        col.pack_start(label(core.TAGLINE, "subtitle"), False, False, 0)
        for head, lines in (("Designed for", ["CA-1 — MAKAUT, WB"]), ("Made by", ["Arnab Mandal", "Website: arnabmandal.com", "Email: arnab@ik.me"]),
                            ("Special Thanks", ["Dr. Nabanita Ganguly"])):
            col.pack_start(label(head, "section"), False, False, 8)
            for ln in lines:
                col.pack_start(label(ln), False, False, 0)
        row.pack_start(col, True, True, 0)
        c.pack_start(row, False, False, 0)
        box.pack_start(c, False, False, 0)
        e = self.app.env
        box.pack_start(kvgrid([("MAC-OUT version", core.VERSION), ("Architecture", "%s (%s)" % (e["arch"], e["arch_raw"])), ("Kernel", e["kernel"]),
                               ("Distribution", e["distro"]), ("macchanger", self.app.backend.macchanger_version() or "not installed"),
                               ("License", "MIT. macchanger is GPL-2.0+ and is used as an external program.")]), False, False, 0)
        box.pack_start(label("MAC-OUT reports what the local system can observe. It cannot see what an upstream network records.", "key", wrap=True), False, False, 0)
        return None

    # ---- first run
    def first_run(self):
        d = Gtk.Dialog(title="Welcome to MAC-OUT", transient_for=self, modal=True)
        d.set_default_size(520, 400)
        area = d.get_content_area()
        area.set_border_width(24)
        stack = Gtk.Stack()
        w = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        w.pack_start(Gtk.Image.new_from_pixbuf(logo_pixbuf(110)), False, False, 6)
        w.pack_start(label("Welcome to MAC-OUT", "title", xalign=0.5), False, False, 0)
        w.pack_start(label("MAC Address Management &\nNetwork Identity Observatory", "subtitle", xalign=0.5), False, False, 0)
        w.pack_start(label("Designed for CA-1 — MAKAUT, WB", "key", xalign=0.5), False, False, 8)
        stack.add_named(w, "welcome")
        e = self.app.env
        chk = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        chk.pack_start(label("Environment Check", "title"), False, False, 0)
        ifs = self.app.backend.list_interfaces()
        items = [(e["system"] == "Linux", "Linux detected (%s)" % e["distro"], ""),
                 (e["supported_arch"], "Architecture detected: %s" % e["arch_raw"], "MAC-OUT is tested on x86_64 and aarch64."),
                 (bool(self.app.backend.macchanger), "macchanger found" if self.app.backend.macchanger else "macchanger not found", "Install it with: sudo apt install macchanger"),
                 (bool(ifs), "Network interfaces found: %s" % (", ".join(ifs) or "none"), ""),
                 (e["network_manager"], "Network backend: NetworkManager" if e["network_manager"] else "NetworkManager not detected", "Optional. Persistence will use systemd instead."),
                 (e["root"], "Running as root" if e["root"] else "Not running as root", "Restart with: sudo ./macout to change MAC addresses.")]
        allok = True
        for ok, text, fix in items:
            line = Gtk.Box(spacing=8)
            line.pack_start(label("✓" if ok else "!", "ok" if ok else "warn"), False, False, 0)
            line.pack_start(label(text), False, False, 0)
            chk.pack_start(line, False, False, 0)
            if not ok and fix:
                chk.pack_start(label("   " + fix, "warn", wrap=True), False, False, 0)
            allok = allok and ok
        chk.pack_start(label("\nReady." if allok else "\nSome items need attention, but you can still look around.", "subtitle"), False, False, 0)
        stack.add_named(chk, "check")
        area.pack_start(stack, True, True, 0)
        btn = d.add_button("Continue", Gtk.ResponseType.OK)
        btn.get_style_context().add_class("suggested-action")
        state = {"n": 0}
        def on_resp(dlg, resp):
            if state["n"] == 0:
                state["n"] = 1
                stack.set_visible_child_name("check")
                btn.set_label("Open Dashboard")
            else:
                self.app.settings.set("first_run_done", True)
                dlg.destroy()
        d.connect("response", on_resp)
        d.show_all()
        return False
