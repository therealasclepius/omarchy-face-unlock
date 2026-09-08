import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('auth_manage', ROOT / 'scripts/auth_manage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SUDO = '#%PAM-1.0\nauth\tinclude\tsystem-auth\naccount include system-auth\nsession include system-auth\nsession optional pam_systemd.so class=none\n'
POLKIT = '#%PAM-1.0\n\nauth include system-auth\naccount include system-auth\npassword include system-auth\nsession include system-auth\n'


class AuthLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.etc, self.vendor = root / 'etc', root / 'vendor'
        self.etc.mkdir()
        self.vendor.mkdir()
        (self.etc / 'sudo').write_text(SUDO)
        (self.vendor / 'polkit-1').write_text(POLKIT)
        self.config = root / 'config.toml'
        self.config.write_text('[security]\n')
        for name, value in [('ETC', self.etc), ('VENDOR', self.vendor), ('STATE', root / 'state.json'), ('CONFIG', self.config)]:
            p = patch.object(m, name, value)
            p.start()
            self.addCleanup(p.stop)
        # Fixture files are owned by the test user; production trust checks are tested separately.
        p = patch.object(m, 'check_trusted')
        p.start()
        self.addCleanup(p.stop)
        self.state = {}

    def test_enable_both_and_exact_restore_vendor_untouched(self):
        m.enable(self.state, list(m.SERVICES))
        for name, before in [('sudo', SUDO), ('polkit-1', POLKIT)]:
            self.assertEqual((self.etc / name).read_text().replace(m.BLOCK, ''), before)
        self.assertEqual((self.vendor / 'polkit-1').read_text(), POLKIT)
        m.enable(self.state, list(m.SERVICES))
        m.disable(self.state, list(m.SERVICES))
        self.assertEqual((self.etc / 'sudo').read_text(), SUDO)
        self.assertFalse((self.etc / 'polkit-1').exists())
        self.assertEqual(json.loads(m.STATE.read_text()), {})

    def test_independent_selection_and_removal(self):
        m.enable(self.state, ['sudo'])
        self.assertFalse((self.etc / 'polkit-1').exists())
        m.enable(self.state, ['polkit-1'])
        m.disable(self.state, ['sudo'])
        self.assertIn(m.BLOCK, (self.etc / 'polkit-1').read_text())
        self.assertEqual(list(self.state), ['polkit-1'])

    def test_existing_polkit_override_restored_exactly(self):
        original = '# local comments\n' + POLKIT
        (self.etc / 'polkit-1').write_text(original)
        m.enable(self.state, ['polkit-1'])
        m.disable(self.state, ['polkit-1'])
        self.assertEqual((self.etc / 'polkit-1').read_text(), original)

    def test_custom_auth_or_unowned_face_refused_before_any_write(self):
        for addition in ['auth required pam_custom.so\n', 'auth sufficient pam_facelock.so\n',
                         'auth [success=1 default=ignore] pam_unix.so\n']:
            (self.vendor / 'polkit-1').write_text(addition + POLKIT)
            with self.assertRaises(RuntimeError):
                m.enable(self.state, list(m.SERVICES))
            self.assertEqual((self.etc / 'sudo').read_text(), SUDO)
            self.assertFalse(m.STATE.exists())

    def test_changed_managed_file_preserved_and_undo_is_preflighted(self):
        m.enable(self.state, list(m.SERVICES))
        edited = (self.etc / 'polkit-1').read_text() + '# later admin edit\n'
        (self.etc / 'polkit-1').write_text(edited)
        with self.assertRaises(RuntimeError):
            m.disable(self.state, list(m.SERVICES))
        self.assertIn(m.BLOCK, (self.etc / 'sudo').read_text())
        self.assertEqual((self.etc / 'polkit-1').read_text(), edited)
        with self.assertRaises(RuntimeError):
            m.enable(self.state, ['polkit-1'])

    def test_vendor_update_exposed_on_removal(self):
        m.enable(self.state, ['polkit-1'])
        new = POLKIT + '# package update\n'
        (self.vendor / 'polkit-1').write_text(new)
        m.disable(self.state, ['polkit-1'])
        self.assertEqual(m.effective('polkit-1').read_text(), new)

    def test_interrupted_install_and_undo_are_recoverable(self):
        for service in m.SERVICES:
            self.state[service] = m.prepare(service)
        m.save(self.state)  # Process death after intent, before either write.
        m.enable(self.state, list(m.SERVICES))
        (self.etc / 'sudo').write_text(SUDO)  # Death after undo write, before journal save.
        m.disable(self.state, list(m.SERVICES))
        self.assertEqual(self.state, {})

    def test_failed_second_write_rolls_back_first(self):
        write = m.atomic_write
        failed = False

        def fail_once(path, text, mode=0o600):
            nonlocal failed
            if path == self.etc / 'polkit-1' and not failed:
                failed = True
                raise OSError('disk error')
            return write(path, text, mode)

        with patch.object(m, 'atomic_write', side_effect=fail_once):
            with self.assertRaises(OSError):
                m.enable(self.state, list(m.SERVICES))
        self.assertEqual((self.etc / 'sudo').read_text(), SUDO)
        self.assertFalse((self.etc / 'polkit-1').exists())
        self.assertEqual(self.state, {})

    def test_disable_without_state_does_not_touch_external_face(self):
        external = 'auth sufficient pam_facelock.so\n' + SUDO
        (self.etc / 'sudo').write_text(external)
        m.disable(self.state, list(m.SERVICES))
        self.assertEqual((self.etc / 'sudo').read_text(), external)

    def test_session_bypass_requires_explicit_opt_in_without_config_edit(self):
        original = '[security]\nabort_if_ssh = false\n'
        self.config.write_text(original)
        with self.assertRaises(RuntimeError):
            m.preflight(list(m.SERVICES))
        m.preflight(list(m.SERVICES), allow_session_bypass=True)
        self.assertEqual(self.config.read_text(), original)

    def test_backend_policy_and_protections_are_not_weakened(self):
        for config in ['[security]\ndisabled=true\n', '[security]\nrequire_ir=false\n',
                       '[security]\nrequire_frame_variance=false\n', '[encryption]\nmethod="none"\n',
                       '[security.pam_policy]\nallowed_services=["omarchy-lock-face"]\n',
                       '[security.pam_policy]\ndenied_services=["polkit-1"]\n']:
            self.config.write_text(config)
            with self.assertRaises(RuntimeError):
                m.preflight(list(m.SERVICES))
            self.assertEqual(self.config.read_text(), config)

    def test_whitelist_never_contains_global_login_or_ssh_services(self):
        self.assertEqual(set(m.SERVICES), {'sudo', 'polkit-1'})
        self.assertEqual(set(m.BASES), set(m.SERVICES))
        self.assertEqual(m.rules(m.BLOCK), ['auth sufficient pam_facelock.so'])


if __name__ == '__main__':
    unittest.main()
