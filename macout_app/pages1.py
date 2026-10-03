"""Dashboard, Interfaces and MAC Control pages (mixin for MacOutWindow)."""
import time

from gi.repository import Gtk

from . import core
from .core import MacError, normalize_mac
from .backend import BackendError
from .gui_common import *  # noqa: F401,F403


class Pages1:
    # ---- Dashboard
    def build_dashboard(self, box):
        hh = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hour = time.localtime().tm_hour
        greet = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
        hh.pack_start(label(greet, "subtitle"), False, False, 0)
        hh.pack_start(label("Network Overview", "title"), False, False, 0)
        box.pack_start(hh, False, False, 0)
        self.dash_banner = Gtk.Box()
        box.pack_start(self.dash_banner, False, False, 0)
        self.dash_cards = Gtk.FlowBox()
        self.dash_cards.set_selection_mode(Gtk.SelectionMode.NONE)
        self.dash_cards.set_max_children_per_line(3)
        self.dash_cards.set_homogeneous(True)
        self.dash_cards.set_column_spacing(12)
        self.dash_cards.set_row_spacing(12)
        box.pack_start(self.dash_cards, False, False, 0)
        q = card("Quick actions")
        row = Gtk.Box(spacing=8)
        row.pack_start(button("Randomize", lambda: self.do_apply("random", {}), "suggested-action"), False, False, 0)
        row.pack_start(button("Restore", self.do_restore), False, False, 0)
        row.pack_start(button("Start Rotation", lambda: self.goto("Rotation")), False, False, 0)
        row.pack_start(button("Stop Rotation", self.stop_rotation), False, False, 0)
        row.pack_start(button("Run Diagnostics", lambda: (self.goto("Diagnostics"), self.run_diag())), False, False, 0)
        q.pack_start(row, False, False, 0)
        box.pack_start(q, False, False, 0)
        rc = card("Rotation")
        self.dash_rot = label("Not running", "mono")
        rc.pack_start(self.dash_rot, False, False, 0)
        box.pack_start(rc, False, False, 0)
        tc = card("Recent events")
        self.tl_dash = Gtk.ListStore(str, str, str, str)
        tc.pack_start(self.timeline_view(self.tl_dash, 170), True, True, 0)
        box.pack_start(tc, True, True, 0)
        return self.refresh_dashboard

    def goto(self, page):
        self.nav.select_row(self.nav.get_row_at_index(PAGES.index(page)))

    def refresh_dashboard(self):
        clear(self.dash_cards)
        clear(self.dash_banner)
        if not self.app.backend.macchanger:
            self.dash_banner.pack_start(label("macchanger is not installed. MAC-OUT needs it for changes. Install: sudo apt install macchanger", "banner banner-bad", wrap=True), True, True, 0)
        elif not self.app.env["root"]:
            self.dash_banner.pack_start(label("Read-only mode: you are not root. Restart with sudo ./macout to change MAC addresses.", "banner banner-warn", wrap=True), True, True, 0)
        if not self.snaps:
            self.dash_cards.add(card("Reading interfaces...", "This takes a second."))
        for n, s in self.snaps.items():
            c = card()
            c.pack_start(label(s["type"], "key"), False, False, 0)
            c.pack_start(label(n, "big"), False, False, 0)
            h, k = self.health_of(s)
            c.pack_start(pill("● " + s["association"].upper(), "ok" if s["association"] == "Connected" else ("warn" if s["up"] else "off")), False, False, 0)
            c.pack_start(pill("● NETWORK " + h, k), False, False, 0)
            st = self.app.rotation.status(n)
            c.pack_start(kvgrid([("Current MAC", s["mac"]), ("Permanent MAC", s.get("permanent") or "not exposed by driver"),
                                 ("IPv4", ", ".join(s["ipv4"]) or "none"), ("Gateway", s.get("gateway") or "none"),
                                 ("Profile", self.app.profiles.active_for(n) or "none"),
                                 ("Rotation", ("every %d min, ACTIVE" % st["interval_min"]) if st else "off")],
                                mono=("Current MAC", "Permanent MAC")), False, False, 4)
            self.dash_cards.add(c)
        self.dash_cards.show_all()
        self.dash_banner.show_all()

    # ---- Interfaces
    def build_interfaces(self, box):
        box.pack_start(heading("Interfaces", "Everything the system reports for each network interface. Values come from the kernel, iproute2 and NetworkManager."), False, False, 0)
        self.if_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.pack_start(self.if_list, False, False, 0)
        return self.refresh_interfaces

    def refresh_interfaces(self):
        clear(self.if_list)
        for n, s in self.snaps.items():
            c = card("%s  (%s)" % (n, s["type"]))
            rows = [("State", "%s, %s" % (s["state"], s["association"])), ("Current MAC", s["mac"]),
                    ("Permanent MAC", s.get("permanent") or "not exposed by driver"),
                    ("IPv4", ", ".join(s["ipv4"]) or "none"), ("IPv6", ", ".join(s["ipv6"]) or "none"),
                    ("Gateway", s.get("gateway") or "none"), ("NetworkManager", s["nm"]),
                    ("Active profile", self.app.profiles.active_for(n) or "none")]
            w = s.get("wifi")
            if w is not None:
                rows += [("SSID", w.get("ssid") or "not available"), ("BSSID", w.get("bssid") or "not available"),
                         ("Signal", ("%s dBm" % w["signal"]) if w.get("signal") is not None else "not available")]
            c.pack_start(kvgrid(rows, mono=("Current MAC", "Permanent MAC", "BSSID")), False, False, 0)
            ex = Gtk.Expander(label="Advanced details")
            ex.add(label("MTU %s\nRoutes:\n%s" % (s.get("mtu"), "\n".join(self.app.backend.routes(n)) or "none"), "mono", selectable=True))
            c.pack_start(ex, False, False, 0)
            self.if_list.pack_start(c, False, False, 0)
        if not self.snaps:
            self.if_list.pack_start(card("No interfaces found", "Nothing under /sys/class/net except loopback."), False, False, 0)
        self.if_list.show_all()

    # ---- MAC Control
    def build_mac_control(self, box):
        box.pack_start(heading("MAC Control", "Change, verify and restore the MAC of the selected interface. Every change is verified by reading the address back."), False, False, 0)
        self.mc_info = card("Current identity")
        box.pack_start(self.mc_info, False, False, 0)
        ops = card("Operations")
        r1 = Gtk.Box(spacing=8)
        r1.pack_start(button("Randomize", lambda: self.do_apply("random", {}), "suggested-action", "macchanger -r"), False, False, 0)
        r1.pack_start(button("Locally administered", lambda: self.do_apply("local", {}), tip="Random unicast address with the local bit set"), False, False, 0)
        r1.pack_start(button("Restore permanent MAC", self.do_restore, "destructive-action"), False, False, 0)
        ops.pack_start(r1, False, False, 0)
        ops.pack_start(label("Specific MAC", "section"), False, False, 4)
        r2 = Gtk.Box(spacing=8)
        self.mac_entry = Gtk.Entry()
        self.mac_entry.set_placeholder_text("02:11:22:33:44:55")
        self.mac_entry.set_width_chars(22)
        self.mac_entry.connect("changed", self.on_mac_entry)
        r2.pack_start(self.mac_entry, False, False, 0)
        r2.pack_start(button("Apply", self.apply_manual), False, False, 0)
        self.mac_hint = label("", "key")
        r2.pack_start(self.mac_hint, False, False, 6)
        ops.pack_start(r2, False, False, 0)
        ops.pack_start(label("Vendor-specific MAC", "section"), False, False, 4)
        r3 = Gtk.Box(spacing=8)
        self.vendor_search = Gtk.SearchEntry()
        self.vendor_search.set_placeholder_text("Search vendor: Intel, Apple, Cisco, Raspberry...")
        self.vendor_search.set_width_chars(34)
        self.vendor_search.connect("search-changed", self.on_vendor_search)
        r3.pack_start(self.vendor_search, False, False, 0)
        self.vendor_preview = label("", "mono")
        r3.pack_start(self.vendor_preview, False, False, 6)
        ops.pack_start(r3, False, False, 0)
        self.vendor_store = Gtk.ListStore(str, str, int)
        tv = Gtk.TreeView(model=self.vendor_store)
        for i, t in enumerate(("OUI", "Vendor", "Known prefixes")):
            tv.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i))
        tv.get_selection().connect("changed", self.on_vendor_select)
        self.vendor_tv = tv
        sw = scrolled(tv)
        sw.set_min_content_height(150)
        ops.pack_start(sw, False, False, 0)
        r4 = Gtk.Box(spacing=8)
        r4.pack_start(button("Generate preview", self.vendor_generate), False, False, 0)
        r4.pack_start(button("Apply vendor MAC", self.vendor_apply, "suggested-action"), False, False, 0)
        ops.pack_start(r4, False, False, 0)
        ops.pack_start(label("Persistence", "section"), False, False, 4)
        self.persist_label = label("", "subtitle", wrap=True)
        ops.pack_start(self.persist_label, False, False, 0)
        r5 = Gtk.Box(spacing=8)
        r5.pack_start(button("Make current MAC persistent", self.persist_on), False, False, 0)
        r5.pack_start(button("Remove persistence", self.persist_off), False, False, 0)
        ops.pack_start(r5, False, False, 0)
        box.pack_start(ops, False, False, 0)
        self.mc_result = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(self.mc_result, False, False, 0)
        self.vendor_pick = None
        self.vendor_candidate = None
        self.on_vendor_search(self.vendor_search)
        return self.refresh_mac_control

    def refresh_mac_control(self):
        clear(self.mc_info)
        self.mc_info.pack_start(label("Current identity", "cardtitle"), False, False, 0)
        s = self.snap()
        if not s:
            self.mc_info.pack_start(label("Reading interface...", "subtitle"), False, False, 0)
        else:
            d = core.describe_mac(s["mac"], self.app.manager.oui.lookup)
            orig = self.app.manager.original_mac(self.iface)
            rows = [("Interface", "%s (%s)" % (self.iface, s["type"])), ("Current MAC", d["mac"]),
                    ("Permanent MAC", s.get("permanent") or "not exposed by driver (MAC-OUT remembers the first MAC it saw: %s)" % (orig or "none yet")),
                    ("Type", d["cast"]), ("Administration", d["administration"]), ("OUI", d["oui"]), ("Vendor", d["vendor"])]
            self.mc_info.pack_start(kvgrid(rows, mono=("Current MAC", "OUI")), False, False, 0)
            if s["type"] not in ("Wi-Fi", "Ethernet", "Dummy"):
                self.mc_info.pack_start(label("This is a %s interface. It may refuse MAC changes." % s["type"], "banner banner-warn"), False, False, 0)
        self.mc_info.show_all()
        if self.iface:
            ent = self.app.persistence.entries().get(self.iface)
            state = ("Currently persistent: %s (%s)" % (ent["mac"], ent["mechanism"])) if ent else "Current state: Temporary (lost on reboot)."
            self.persist_label.set_text(self.app.persistence.explain(self.iface) + "\n" + state)

    def on_mac_entry(self, e):
        t = e.get_text()
        if not t:
            self.mac_hint.set_text("")
            return
        try:
            m = normalize_mac(t)
            if core.is_multicast(m):
                self.mac_hint.set_text("✗ multicast address, cannot be used")
            else:
                self.mac_hint.set_text("✓ unicast, %s" % ("locally administered" if core.is_locally_administered(m) else "globally unique"))
        except MacError:
            self.mac_hint.set_text("✗ not a valid MAC")

    def apply_manual(self):
        try:
            m = normalize_mac(self.mac_entry.get_text())
            if core.is_multicast(m):
                raise MacError("A multicast address cannot be used on an interface")
        except MacError as e:
            self.info("Invalid MAC", str(e), Gtk.MessageType.WARNING)
            return
        self.do_apply("fixed", {"mac": m})

    def on_vendor_search(self, entry):
        self.vendor_store.clear()
        db = self.app.manager.oui
        if not len(db):
            self.vendor_preview.set_text("No vendor database found (install macchanger or ieee-data).")
            return
        seen = {}
        for oui, name in db.search(entry.get_text(), 800):
            seen.setdefault(name, []).append(oui)
        for name, ouis in list(seen.items())[:80]:
            self.vendor_store.append([ouis[0], name, len(ouis)])

    def on_vendor_select(self, sel):
        m, it = sel.get_selected()
        self.vendor_pick = (m[it][0], m[it][1]) if it else None

    def vendor_generate(self):
        if not self.vendor_pick:
            self.vendor_preview.set_text("Select a vendor first")
            return
        self.vendor_candidate = core.mac_from_oui(self.vendor_pick[0])
        self.vendor_preview.set_text("Preview: " + self.vendor_candidate)

    def vendor_apply(self):
        if not self.vendor_candidate:
            self.vendor_generate()
        if self.vendor_candidate:
            self.do_apply("fixed", {"mac": self.vendor_candidate}, "Vendor-specific (%s)" % self.vendor_pick[1])

    def persist_on(self):
        if not self.can_change() or not self.confirm("Make the current MAC persistent?", self.app.persistence.explain(self.iface)):
            return
        mac = self.app.backend.current_mac(self.iface)
        iface = self.iface
        def done(r, err):
            if err:
                self.info("Persistence not set", str(err), Gtk.MessageType.WARNING)
            else:
                self.info("Persistent MAC set", "Mechanism: %s" % r)
            self.refresh_mac_control()
        self.bg(lambda: self.app.persistence.enable(iface, mac), done)

    def persist_off(self):
        iface = self.iface
        def done(r, err):
            if err:
                self.info("Could not remove persistence", str(err), Gtk.MessageType.WARNING)
            self.refresh_mac_control()
        self.bg(lambda: self.app.persistence.disable(iface), done)

    def do_restore(self):
        if not self.can_change():
            return
        if not self.confirm("Restore the original MAC on %s?" % self.iface, "The interface goes down briefly and reconnects."):
            return
        iface = self.iface
        self.run_op(lambda: self.app.manager.restore(iface))

    def do_apply(self, strategy, p, op=None):
        if not self.can_change():
            return
        if not self.confirm("Change the MAC on %s?" % self.iface, "The interface goes down briefly. Your connection will drop for a few seconds and DHCP will be renewed."):
            return
        iface = self.iface
        self.run_op(lambda: self.app.manager.apply(iface, strategy, p, profile=self.app.profiles.active_for(iface), operation=op))

    def show_result(self, res):
        clear(self.mc_result)
        ok = res.get("ok")
        c = card("Result" if ok else "Operation failed")
        kind = "banner-ok" if ok and not res.get("degraded") else ("banner-warn" if ok else "banner-bad")
        c.pack_start(label(res.get("message") or "Done", "banner " + kind, wrap=True), False, False, 0)
        if ok:
            c.pack_start(label("Requested: %s    Observed: %s    %s" % (res.get("requested") or "(chosen by macchanger)", res.get("observed"), "✓ Verified" if res.get("verified") else ""), "mono"), False, False, 0)
        self.mc_result.pack_start(c, False, False, 0)
        self.mc_result.show_all()
        self.refresh_ba()
