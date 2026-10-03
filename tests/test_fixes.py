import os, sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from macout_app import core, services
from test_macout import ServiceBase

class FixTests(ServiceBase):
    def test_batch_all_prefixes(self):
        prefixes = ['00:11:22', '00:22:33', '00:33:44']
        batch = core.vendor_candidates(prefixes)
        self.assertEqual(len(set(batch)), 12)
        self.assertEqual({core.oui_of(m) for m in batch}, set(prefixes))
        self.assertTrue(all(not core.is_multicast(m) and not core.is_locally_administered(m) for m in batch))

    def test_vendor_display(self):
        lookup = lambda m: "Cisco" if m.startswith("00:11:22") else None
        self.assertEqual(core.format_mac("00:11:22:33:44:55", lookup), "00:11:22:33:44:55 (Cisco)")
        self.assertIn("locally administered", core.format_mac("02:11:22:33:44:55", lookup))
        self.assertEqual(core.format_mac("a4:11:22:33:44:55", lookup), "a4:11:22:33:44:55")

    def test_timestamps_not_redacted(self):
        r = services.Redactor({'redact_ip_public': True}, {})
        self.assertEqual(r.text('2026-10-03 18:34:31'), '2026-10-03 18:34:31')

    def test_plain_oui_format(self):
        p = os.path.join(self.tmp, 'vendors.txt')
        with open(p, 'w') as f: f.write('001122 Cisco\n')
        db = core.OuiDatabase(p)
        self.assertEqual(db.lookup('00:11:22:33:44:55'), 'Cisco')

    def test_bad_prefixes(self):
        with self.assertRaises(core.MacError):
            core.vendor_candidates(['01:00:5e', '02:11:22', 'garbage'])

    def test_root_exports_owned_by_invoker(self):
        import pwd
        user = pwd.getpwuid(os.getuid())
        for fmt in ('html', 'txt', 'json', 'csv', 'zip'):
            p = os.path.join(self.tmp, 'owner.' + fmt)
            with patch.object(services.os, 'geteuid', return_value=0), patch.object(services, 'desktop_identity', return_value=user), patch.object(services.os, 'fchown') as chown:
                self.app.reports.export(fmt, p, opts={})
                self.assertEqual(chown.call_args.args[1:], (user.pw_uid, user.pw_gid))
            self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)

    def test_failed_export_preserves_destination(self):
        p = os.path.join(self.tmp, 'existing.html')
        with open(p, 'w') as f: f.write('previous report')
        with patch.object(self.app.reports, 'to_html', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError): self.app.reports.export('html', p)
        with open(p) as f: self.assertEqual(f.read(), 'previous report')

    def test_sudo_identity_mismatch_refused(self):
        import pwd
        user = pwd.getpwuid(os.getuid())
        with patch.object(services.os, 'geteuid', return_value=0), patch.dict(os.environ, SUDO_USER=user.pw_name, SUDO_UID='999999', SUDO_GID=str(user.pw_gid)):
            with self.assertRaises(ValueError): services.desktop_identity()

    def test_root_opener_uses_runuser(self):
        import pwd
        user = pwd.getpwuid(os.getuid())
        with patch.object(services.os, 'geteuid', return_value=0), patch.object(services, 'desktop_identity', return_value=user), patch.object(core, 'find_tool', return_value='/usr/sbin/runuser'), patch.object(services.subprocess, 'run') as run:
            run.return_value.returncode = 0
            services.open_export('/tmp/report.html')
            self.assertEqual(run.call_args.args[0][:4], ['/usr/sbin/runuser', '-u', user.pw_name, '--'])
            self.assertNotIn('preexec_fn', run.call_args.kwargs)
            self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_dark_migration_once(self):
        path = os.path.join(self.tmp, 'settings.json')
        with open(path, 'w') as f: f.write('{"theme": "system"}')
        settings = services.Settings(self.tmp)
        self.assertEqual(settings.get('theme'), 'dark')
        settings.set('theme', 'light')
        self.assertEqual(services.Settings(self.tmp).get('theme'), 'light')

    def test_open_is_not_shell(self):
        with patch.object(services.subprocess, 'run') as run:
            run.return_value.returncode = 0
            services.open_export('/tmp/a b;touch pwn.html')
            self.assertEqual(run.call_args.args[0], ['xdg-open', '/tmp/a b;touch pwn.html'])

if __name__ == '__main__': unittest.main()
