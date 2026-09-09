import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manage', ROOT / 'helper/manage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CONFIG = '''# Retain camera choice and comments.
[device]
path = "/dev/video9"
[security]
# abort_if_ssh = true
require_ir = true
[recognition]
threshold = 0.85
'''


class ConfigTests(unittest.TestCase):
    def test_insert_update_restore_preserves_other_settings(self):
        changed = m.set_security(CONFIG, 'abort_if_ssh', False)
        changed = m.set_security(changed, 'frame_variance_max_similarity', 0.995)
        parsed = tomllib.loads(changed)
        self.assertEqual(parsed['device']['path'], '/dev/video9')
        self.assertEqual(parsed['recognition']['threshold'], 0.85)
        self.assertFalse(parsed['security']['abort_if_ssh'])
        restored = m.restore_options(changed, {
            'abort_if_ssh': {'previous': None, 'applied': False},
            'frame_variance_max_similarity': {'previous': None, 'applied': 0.995},
        })
        self.assertEqual(tomllib.loads(restored), tomllib.loads(CONFIG))
        self.assertIn('# Retain camera choice', restored)

    def test_existing_explicit_value_and_later_edit(self):
        original = m.set_security(CONFIG, 'frame_variance_max_similarity', 0.98)
        changed = m.set_security(original, 'frame_variance_max_similarity', 0.995)
        state = {'frame_variance_max_similarity': {'previous': 0.98, 'applied': 0.995}}
        self.assertEqual(tomllib.loads(m.restore_options(changed, state)), tomllib.loads(original))
        manual = m.set_security(changed, 'frame_variance_max_similarity', 0.99)
        self.assertEqual(m.restore_options(manual, state), manual)

    def test_unusual_layout_and_unapproved_key_refused(self):
        for text in ['security = {abort_if_ssh = true}\n', '[security]\n"abort_if_ssh"=true\n']:
            with self.assertRaises(ValueError):
                m.set_security(text, 'abort_if_ssh', False)
        with self.assertRaises(ValueError):
            m.set_security(CONFIG, 'require_ir', False)

    def test_keys_in_other_sections_unchanged(self):
        original = CONFIG + 'abort_if_ssh = "unrelated"\n'
        modified = m.set_security(original, 'abort_if_ssh', False)
        self.assertEqual(tomllib.loads(modified)['recognition']['abort_if_ssh'], 'unrelated')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = root / 'config.toml'
        self.config.write_text(CONFIG)
        self.pam = root / 'omarchy-lock-face'
        self.state_dir = root / 'state'
        self.state_dir.mkdir()
        for key, value in [('CONFIG', self.config), ('PAM', self.pam),
                           ('STATE_DIR', self.state_dir), ('STATE', self.state_dir / 'state.json')]:
            p = patch.object(m, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.calls = []
        p = patch.object(m, 'run', self.backend)
        p.start()
        self.addCleanup(p.stop)
        self.state = {'settings': {}, 'pam_owned': False}

    def backend(self, *args):
        self.calls.append(args)
        if args[1:3] == ('pam', 'add'):
            text = self.pam.read_text()
            if 'pam_facelock.so' not in text:
                self.pam.write_text(text.replace('auth required pam_deny.so',
                    'auth sufficient pam_facelock.so\nauth required pam_deny.so'))
        elif args[1:3] == ('pam', 'remove'):
            self.pam.write_text(self.pam.read_text().replace('auth sufficient pam_facelock.so\n', ''))

    def test_fresh_setup_and_remove_restore_original(self):
        m.configure(self.state, ['abort_if_ssh', 'frame_variance_max_similarity'])
        self.assertEqual(m.rules(self.pam.read_text()), m.RULES)
        self.assertTrue(self.state['pam_owned'])
        self.assertEqual(self.pam.stat().st_mode & 0o777, 0o644)
        m.configure(self.state, [])  # Repeated setup retains original undo point.
        m.remove(self.state)
        self.assertFalse(self.pam.exists())
        self.assertEqual(tomllib.loads(self.config.read_text()), tomllib.loads(CONFIG))
        self.assertTrue(all('sudo' not in call and 'system-auth' not in call for call in self.calls))

    def test_existing_compatible_service_and_tuning_are_not_owned(self):
        content = '# Existing integration\n' + '\n'.join(m.RULES) + '\n'
        self.pam.write_text(content)
        self.config.write_text(m.set_security(CONFIG, 'abort_if_ssh', False))
        m.configure(self.state, ['abort_if_ssh'])
        self.assertFalse(self.state['pam_owned'])
        self.assertEqual(self.state['settings'], {})
        m.remove(self.state)
        self.assertEqual(self.pam.read_text(), content)
        self.assertFalse(tomllib.loads(self.config.read_text())['security']['abort_if_ssh'])

    def test_unknown_service_is_never_overwritten(self):
        self.pam.write_text('auth required pam_other.so\n')
        with self.assertRaises(RuntimeError):
            m.configure(self.state, ['abort_if_ssh'])
        self.assertEqual(self.pam.read_text(), 'auth required pam_other.so\n')
        self.assertEqual(self.config.read_text(), CONFIG)
        self.assertEqual(self.calls, [])
        self.assertFalse(m.STATE.exists())

    def test_changed_managed_service_is_preserved(self):
        m.configure(self.state, [])
        self.pam.write_text(self.pam.read_text() + '# changed later\n')
        with self.assertRaises(RuntimeError):
            m.remove(self.state)
        self.assertIn('# changed later', self.pam.read_text())

    def test_backend_failure_leaves_deny_only_service_recoverable(self):
        with patch.object(m, 'run', side_effect=subprocess.CalledProcessError(1, 'facelock')):
            with self.assertRaises(subprocess.CalledProcessError):
                m.configure(self.state, ['abort_if_ssh'])
        self.assertEqual(self.pam.read_text(), m.SKELETON)
        self.assertEqual(self.config.read_text(), CONFIG)
        recovered = json.loads(m.STATE.read_text())
        m.remove(recovered)
        self.assertFalse(self.pam.exists())

    def test_symlink_trust_check_refuses(self):
        link = Path(self.temp.name) / 'link'
        link.symlink_to(self.config)
        with self.assertRaises(RuntimeError):
            m.check_trusted(link)


class PackagingTests(unittest.TestCase):
    def test_manifest_and_portability(self):
        manifest = json.loads((ROOT / 'manifest.json').read_text())
        self.assertEqual(manifest['omarchy']['clonedFrom'], 'omarchy.lock')
        self.assertIn('readonly property string pluginVersion: ' + json.dumps(manifest['version']),
                      (ROOT / 'Service.qml').read_text())
        for file in ['Service.qml', 'LockView.qml', 'setup', 'remove', 'enroll', 'doctor']:
            text = (ROOT / file).read_text()
            self.assertNotIn('/home/', text)
        self.assertIn('auth required pam_deny.so', m.SKELETON)


if __name__ == '__main__':
    unittest.main()
