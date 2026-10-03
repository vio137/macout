import json, os, random, shutil, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from macout_app import core, services, backend
from macout_app.core import MacError
from mock_backend import MockBackend


class CoreTests(unittest.TestCase):
    def test_parse_variants(self):
        self.assertEqual(core.normalize_mac("AA-BB-CC-DD-EE-FF"), "aa:bb:cc:dd:ee:ff")
        self.assertEqual(core.normalize_mac("aabbccddeeff"), "aa:bb:cc:dd:ee:ff")
        self.assertEqual(core.normalize_mac(" 02:11:22:33:44:55 "), "02:11:22:33:44:55")

    def test_invalid(self):
        for bad in ["", "zz:11:22:33:44:55", "02:11:22:33:44", "02:11:22:33:44:55:66", "02:11:22:33:44:5", None, "02:11:22:33:44:55; rm -rf /"]:
            self.assertFalse(core.is_valid_mac(bad), bad)

    def test_bits(self):
        self.assertTrue(core.is_multicast("01:00:5e:00:00:01"))
        self.assertFalse(core.is_multicast("02:00:00:00:00:01"))
        self.assertTrue(core.is_locally_administered("02:00:00:00:00:01"))
        self.assertFalse(core.is_locally_administered("00:1b:44:11:3a:b7"))

    def test_random_local(self):
        for _ in range(200):
            m = core.random_local_mac()
            self.assertTrue(core.is_locally_administered(m))
            self.assertFalse(core.is_multicast(m))

    def test_oui(self):
        self.assertEqual(core.oui_of("00:1B:44:11:3a:b7"), "00:1B:44")
        m = core.mac_from_oui("00:1b:44")
        self.assertTrue(m.startswith("00:1b:44:"))
        with self.assertRaises(MacError):
            core.mac_from_oui("01:00:5e")
        with self.assertRaises(MacError):
            core.mac_from_oui("zz")

    def test_pattern(self):
        m = core.mac_from_pattern("02:xx:xx:aa:xx:xx")
        self.assertTrue(m.startswith("02:") and m[9:11] == "aa")
        with self.assertRaises(MacError):
            core.mac_from_pattern("01:xx:xx:xx:xx:xx")

    def test_oui_db(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "OUI.list")
        open(p, "w").write("00 1B 44 SANDISK CORP\n00 00 0C CISCO SYSTEMS, INC.\n")
        db = core.OuiDatabase(p)
        self.assertEqual(db.lookup("00:1b:44:aa:bb:cc"), "SANDISK CORP")
        self.assertEqual(db.search("cisco")[0][0], "00:00:0C")
        self.assertEqual(core.describe_mac("00:1b:44:aa:bb:cc", db.lookup)["vendor"], "SANDISK CORP")

    def test_arch(self):
        self.assertEqual(core.normalize_arch("amd64"), "x86_64")
        self.assertEqual(core.normalize_arch("arm64"), "aarch64")
        self.assertEqual(core.normalize_arch("aarch64"), "aarch64")

    def test_os_release(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "os")
        open(p, "w").write('PRETTY_NAME="Ubuntu 22.04"\nID=ubuntu\nID_LIKE=debian\n')
        self.assertEqual(core.read_os_release(p)["ID"], "ubuntu")

    def test_dependency_detection(self):
        self.assertIsNone(core.find_tool("definitely-not-a-real-tool-xyz"))
        env = core.detect_environment()
        self.assertIn(env["arch"], (core.normalize_arch(env["arch_raw"]),))


class BackendSafety(unittest.TestCase):
    def test_iface_validation(self):
        for bad in ["", "-r", "eth0; reboot", "a" * 16, "eth 0", "$(id)"]:
            self.assertFalse(backend.valid_iface(bad), bad)
        self.assertTrue(backend.valid_iface("wlan0"))
        self.assertTrue(backend.valid_iface("enp3s0f1"))

    def test_command_construction_no_shell(self):
        calls = []
        orig = backend.run
        backend.run = lambda argv, timeout=10: (calls.append(argv), backend.Result(0, "Permanent MAC: a4:83:e7:12:34:56", ""))[1]
        try:
            b = backend.SystemBackend()
            b.macchanger = "/usr/bin/macchanger"
            b.ip = "/usr/sbin/ip"
            b._check = lambda i: None
            b.link_info = lambda i: {"up": False}
            b.macchanger_apply("eth0", "set", "AA-BB-CC-DD-EE-FF")
        finally:
            backend.run = orig
        self.assertIn(["/usr/bin/macchanger", "-m", "aa:bb:cc:dd:ee:ff", "eth0"], calls)
        self.assertTrue(all(isinstance(a, list) for a in calls))

    def test_rejects_bad_mac_before_running(self):
        b = backend.SystemBackend()
        b.macchanger = "/bin/true"
        b._check = lambda i: None
        with self.assertRaises(MacError):
            b.macchanger_apply("eth0", "set", "nonsense")

    def test_missing_macchanger(self):
        b = backend.SystemBackend()
        b.macchanger = None
        b._check = lambda i: None
        with self.assertRaises(backend.BackendError) as c:
            b.macchanger_apply("eth0", "random")
        self.assertIn("apt install macchanger", str(c.exception))


class ServiceBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mock = MockBackend()
        env = core.detect_environment()
        env["root"] = True
        self.app = services.App(backend=self.mock, base=self._mk(), env=env)
        self.app.settings.data["reconnect_timeout_sec"] = 2

    def _mk(self):
        for s in ("profiles", "sessions", "logs", "reports"):
            os.makedirs(os.path.join(self.tmp, s))
        return self.tmp

    def tearDown(self):
        self.app.rotation.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)


class ManagerTests(ServiceBase):
    def test_random_verified_and_history(self):
        r = self.app.manager.apply("wlan0", "random")
        self.assertTrue(r["ok"] and r["verified"])
        self.assertNotEqual(r["observed"], "a4:83:e7:12:34:56")
        self.assertEqual(self.app.history.all()[-1]["result"], "Success")
        self.assertEqual(self.mock.dhcp_renewals, 1)

    def test_fixed_mac(self):
        r = self.app.manager.apply("eth0", "fixed", {"mac": "02:91:AB:73:41:CC"})
        self.assertEqual(self.mock.current_mac("eth0"), "02:91:ab:73:41:cc")
        self.assertIn("verified", r["message"])

    def test_multicast_rejected(self):
        r = self.app.manager.apply("eth0", "fixed", {"mac": "01:00:5e:00:00:01"})
        self.assertFalse(r["ok"])
        self.assertEqual(self.mock.current_mac("eth0"), "00:1b:44:11:3a:b7")

    def test_command_failure_reported(self):
        self.mock.fail_next = True
        r = self.app.manager.apply("wlan0", "random")
        self.assertFalse(r["ok"])
        self.assertIn("Operation not permitted", r["message"])
        self.assertTrue(self.app.history.all()[-1]["result"].startswith("Failed"))

    def test_verification_catches_silent_failure(self):
        self.mock.lie_next = True
        r = self.app.manager.apply("wlan0", "fixed", {"mac": "02:00:00:00:00:99"})
        self.assertFalse(r["ok"])
        self.assertIn("Verification failed", r["message"])

    def test_restore(self):
        self.app.manager.apply("wlan0", "random")
        r = self.app.manager.restore("wlan0")
        self.assertTrue(r["ok"])
        self.assertEqual(self.mock.current_mac("wlan0"), "a4:83:e7:12:34:56")

    def test_bad_interface(self):
        r = self.app.manager.apply("eth0; reboot", "random")
        self.assertFalse(r["ok"])

    def test_vendor(self):
        r = self.app.manager.apply("eth0", "vendor", {"vendor_oui": "00:1b:44"})
        self.assertTrue(r["observed"].startswith("00:1b:44"))


class ProfileTests(ServiceBase):
    def test_presets_exist(self):
        self.assertEqual({p["name"] for p in self.app.profiles.list()}, {"Home", "Work", "Privacy", "Testing"})

    def test_roundtrip_and_validation(self):
        p = services.new_profile("Lab", strategy="fixed", mac="02:00:00:00:00:01", interface="wlan0")
        self.app.profiles.save(p)
        self.assertEqual(self.app.profiles.get("Lab")["mac"], "02:00:00:00:00:01")
        with self.assertRaises(ValueError):
            self.app.profiles.save(services.new_profile("Bad", strategy="fixed", mac="nope"))

    def test_duplicate_export_import_delete(self):
        q = self.app.profiles.duplicate("Privacy")
        self.assertEqual(q["name"], "Privacy copy")
        path = os.path.join(self.tmp, "x.json")
        self.app.profiles.export("Privacy", path)
        self.app.profiles.delete("Privacy copy")
        self.assertIsNone(self.app.profiles.get("Privacy copy"))
        d = json.load(open(path))
        d["profile"]["name"] = "Imported"
        json.dump(d, open(path, "w"))
        self.assertEqual(self.app.profiles.import_file(path)["name"], "Imported")
        open(path, "w").write("{}")
        with self.assertRaises(ValueError):
            self.app.profiles.import_file(path)

    def test_activate_applies(self):
        self.app.profiles.save(services.new_profile("Loc", strategy="local", rotation={"enabled": False}))
        res = self.app.activate_profile("wlan0", "Loc")
        self.assertTrue(res["ok"])
        self.assertTrue(core.is_locally_administered(self.mock.current_mac("wlan0")))
        self.assertEqual(self.app.profiles.active_for("wlan0"), "Loc")


class RotationTests(ServiceBase):
    def test_state_machine(self):
        t = [1000.0]
        st = services.RotationState(5, clock=lambda: t[0])
        self.assertIsNone(st.remaining())
        st.start()
        self.assertEqual(st.remaining(), 300)
        t[0] += 299
        self.assertFalse(st.due())
        t[0] += 2
        self.assertTrue(st.due())
        st.mark_done()
        self.assertFalse(st.due())
        self.assertEqual(st.count, 1)
        t[0] += 100
        st.pause()
        t[0] += 10000
        self.assertFalse(st.due())
        st.resume()
        self.assertAlmostEqual(st.remaining(), 200, delta=1)
        st.stop()
        self.assertIsNone(st.remaining())

    def test_safeguards(self):
        self.app.settings.data["min_rotation_minutes"] = 5
        prof = services.new_profile("R", strategy="random")
        with self.assertRaises(ValueError):
            self.app.rotation.start_rotation("wlan0", prof, interval_min=1)
        with self.assertRaises(ValueError):
            self.app.rotation.start_rotation("wlan0", services.new_profile("F", strategy="fixed", mac="02:00:00:00:00:01"), 10)

    def test_manual_rotation_logged(self):
        prof = services.new_profile("R", strategy="random")
        self.app.rotation.start_rotation("wlan0", prof, interval_min=5)
        old = self.mock.current_mac("wlan0")
        res = self.app.rotation.rotate_now("wlan0")
        self.assertTrue(res["ok"])
        self.assertNotEqual(old, self.mock.current_mac("wlan0"))
        self.assertEqual(self.app.rotation.status("wlan0")["count"], 1)
        self.assertTrue(any(e["category"] == "ROTATION" for e in self.app.log.records))
        self.app.rotation.stop_rotation("wlan0")
        self.assertIsNone(self.app.rotation.status("wlan0"))

    def test_failed_rotation_does_not_break(self):
        prof = services.new_profile("R", strategy="random")
        self.app.rotation.start_rotation("wlan0", prof, interval_min=5)
        self.mock.fail_next = True
        res = self.app.rotation.rotate_now("wlan0")
        self.assertFalse(res["ok"])
        self.assertIsNotNone(self.app.rotation.status("wlan0"))


class LogHistoryReportTests(ServiceBase):
    def test_log_serialization(self):
        self.app.log.emit("MAC", "hello", iface="eth0", x=1)
        line = open(self.app.log.path).read().strip().splitlines()[-1]
        rec = json.loads(line)
        self.assertEqual((rec["category"], rec["message"], rec["data"]["x"]), ("MAC", "hello", 1))

    def test_verbosity(self):
        self.app.log.set_verbosity("Errors only")
        self.app.log.emit("MAC", "quiet", "INFO")
        self.app.log.emit("ERROR", "loud", "ERROR")
        msgs = [r["message"] for r in self.app.log.visible()]
        self.assertIn("loud", msgs)
        self.assertNotIn("quiet", msgs)

    def test_history_filter_csv_prune(self):
        self.app.history.add(iface="eth0", old_mac="a", new_mac="b", operation="x", result="Success", duration=1)
        with open(self.app.history.path, "a") as f:
            f.write(json.dumps({"time": "2000-01-01 00:00:00", "epoch": 0, "iface": "eth0"}) + "\n")
        rows = self.app.history.all()
        self.assertEqual(len(rows), 2)
        self.assertIn("time,iface", self.app.history.to_csv(rows))
        self.app.history.prune(1)
        self.assertEqual(len(self.app.history.all()), 1)  # the year-2000 record is pruned
        self.assertEqual(len(self.app.history.query(days=7, text="eth0")), 1)

    def test_session_summary(self):
        self.app.sessions.start()
        self.app.manager.apply("wlan0", "random")
        self.mock.fail_next = True
        self.app.manager.apply("wlan0", "random")
        s = self.app.sessions.stop()
        self.assertEqual(s["summary"]["successful"], 1)
        self.assertEqual(s["summary"]["failed"], 1)
        self.assertEqual(len(self.app.sessions.list()), 1)

    def test_reports_and_redaction(self):
        self.app.manager.apply("wlan0", "fixed", {"mac": "02:91:ab:73:41:cc"})
        opts = {k: True for k in ("redact_ip_local", "redact_ip_public", "redact_bssid", "redact_ssid", "redact_perm_mac", "redact_cur_mac")}
        out = {}
        for fmt in ("txt", "json", "csv", "html", "zip"):
            p = os.path.join(self.tmp, "r." + fmt)
            self.app.reports.export(fmt, p, opts=opts)
            self.assertTrue(os.path.getsize(p) > 100)
            out[fmt] = p
        for fmt in ("txt", "json", "html"):
            text = open(out[fmt]).read()
            for secret in ("192.168.1.42", "192.168.1.1", "aa:bb:cc:dd:ee:ff", "HomeNet", "a4:83:e7:12:34:56", "02:91:ab:73:41:cc"):
                self.assertNotIn(secret, text, "%s leaked in %s" % (secret, fmt))
        self.assertIn("MAKAUT", open(out["html"]).read())
        self.assertIn("macout-report.html", zipfile.ZipFile(out["zip"]).namelist())
        json.load(open(out["json"]))
        # unredacted export keeps data
        p = os.path.join(self.tmp, "raw.txt")
        self.app.reports.export("txt", p, opts={})
        self.assertIn("192.168.1.42", open(p).read())

    def test_diagnostics(self):
        res = services.run_diagnostics(self.mock, self.app.observer, self.app.env, "wlan0")
        names = {r["name"]: r for r in res}
        self.assertEqual(names["macchanger available"]["status"], "ok")
        self.assertEqual(names["DNS resolution"]["status"], "ok")


class PersistenceTests(ServiceBase):
    def test_networkmanager_path(self):
        self.app.persistence.env["network_manager"] = True
        mech = self.app.persistence.enable("wlan0", "02:00:00:00:00:42")
        self.assertEqual(mech, "NetworkManager")
        self.assertIn(("nm", "wlan0", "02:00:00:00:00:42"), self.mock.calls)
        self.app.persistence.disable("wlan0")
        self.assertEqual(self.app.persistence.entries(), {})

    def test_needs_root(self):
        self.app.persistence.env["root"] = False
        with self.assertRaises(backend.BackendError):
            self.app.persistence.enable("wlan0", "02:00:00:00:00:42")

    def test_rejects_multicast(self):
        with self.assertRaises(MacError):
            self.app.persistence.enable("wlan0", "01:00:00:00:00:42")


if __name__ == "__main__":
    unittest.main(verbosity=1)
