import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import doctor
import hooks
import update_health

VERSION = json.loads((ROOT / 'manifest.json').read_text())['version']
CATALOG = [{'id': doctor.ID, 'enabled': True, 'active': False}]
STATUS = {'pluginId': doctor.ID, 'pluginVersion': VERSION, 'passwordPam': True, 'face': True, 'locked': False}


class HealthTests(unittest.TestCase):
    def test_authentication_hidden_from_public_services_is_healthy(self):
        self.assertEqual(doctor.runtime_issues(CATALOG, STATUS), [])

    def test_stale_shell_disabled_plugin_missing_password_and_backend(self):
        for catalog, status, message in [
            ([], STATUS, 'not enabled'),
            (CATALOG, None, 'unavailable'),
            (CATALOG, dict(STATUS, pluginVersion='old'), 'running locker differs'),
            (CATALOG, dict(STATUS, pluginId='another.lock'), 'running locker differs'),
            (CATALOG, dict(STATUS, passwordPam=False), 'Password PAM'),
            (CATALOG, dict(STATUS, face=False), 'backend is not ready'),
        ]:
            with self.subTest(message=message):
                self.assertTrue(any(message in issue for issue in doctor.runtime_issues(catalog, status)))

    def test_missing_commands_and_invalid_json_fail_closed(self):
        for result in [subprocess.CompletedProcess([], 1, '{}', ''),
                       subprocess.CompletedProcess([], 0, 'not ready', '')]:
            with patch.object(doctor, 'command', return_value=result):
                self.assertIsNone(doctor.read_json_command('omarchy-shell'))

    def test_startup_retries_are_read_only_and_recover(self):
        def query(*args):
            return CATALOG if args[0] == 'omarchy' else next(states)
        states = iter([None, dict(STATUS, face=False), STATUS])
        with patch.object(update_health, 'compatibility', return_value=True), \
             patch.object(update_health, 'face_pam_ready', return_value=True), \
             patch.object(update_health, 'read_json_command', side_effect=query), \
             patch.object(update_health, 'command', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.object(update_health.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(update_health.check(), [])
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual({call.args for call in run.call_args_list}, {
                ('systemctl', 'is-active', 'facelock-daemon'),
                ('systemctl', 'is-enabled', 'facelock-daemon')})

    def test_unknown_host_and_disabled_daemon_are_reported(self):
        with patch.object(update_health, 'compatibility', return_value=False), \
             patch.object(update_health, 'read_json_command', side_effect=[CATALOG, STATUS]), \
             patch.object(update_health, 'command', return_value=subprocess.CompletedProcess([], 1)), \
             contextlib.redirect_stdout(io.StringIO()):
            issues = update_health.check(attempts=1)
        self.assertTrue(any('compatibility' in issue for issue in issues))
        self.assertTrue(any('not running' in issue for issue in issues))
        self.assertTrue(any('not enabled' in issue for issue in issues))

    def test_missing_or_changed_pam_is_detected_without_backend_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            pam = Path(temp) / 'pam'
            with patch.object(doctor, 'FACE_PAM', pam):
                self.assertFalse(doctor.face_pam_ready())
                pam.write_text('\n'.join(doctor.RULES) + '\n')
                self.assertTrue(doctor.face_pam_ready())
                pam.write_text('auth sufficient pam_permit.so\n')
                self.assertFalse(doctor.face_pam_ready())

    def test_host_change_detected_even_when_lock_files_match(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stock = root / 'stock'
            stock.mkdir()
            (stock / 'lock.qml').write_text('unchanged lock')
            (stock / 'loader.qml').write_text('reviewed loader')
            profile = {'ref': 'test', 'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stock.iterdir()}}
            (root / 'upstream-lock.json').write_text(json.dumps({'profiles': [profile]}))
            with patch.object(doctor, 'ROOT', root), patch.dict(os.environ, {'OMARCHY_PATH': str(stock)}), contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(doctor.compatibility())
                (stock / 'loader.qml').write_text('changed loader')
                self.assertFalse(doctor.compatibility())
                (stock / 'loader.qml').unlink()
                self.assertFalse(doctor.compatibility())


class HookTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dest = Path(temp.name) / 'hooks'
        patcher = patch.object(hooks, 'HOOK_ROOT', self.dest)
        patcher.start(); self.addCleanup(patcher.stop)
        self.calls = []
        def install(args, **kwargs):
            self.calls.append(args)
            target = self.dest / (args[3] + '.d') / hooks.NAME
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args[4], target)
        patcher = patch.object(hooks.subprocess, 'run', side_effect=install)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_install_is_idempotent_and_remove_preserves_unrelated_hook(self):
        hooks.manage('install'); hooks.manage('install')
        self.assertEqual(len(self.calls), 2)
        unrelated = self.dest / 'post-update.d' / 'unrelated'
        unrelated.write_text('keep')
        hooks.manage('remove'); hooks.manage('remove')
        self.assertEqual(unrelated.read_text(), 'keep')
        self.assertFalse((self.dest / 'post-boot.d' / hooks.NAME).exists())

    def test_modified_hook_is_preserved_before_any_other_changes(self):
        hooks.manage('install')
        modified = self.dest / 'post-boot.d' / hooks.NAME
        modified.write_text('my edit')
        for action in ('install', 'remove'):
            with self.assertRaises(RuntimeError): hooks.manage(action)
        self.assertEqual(modified.read_text(), 'my edit')
        self.assertTrue((self.dest / 'post-update.d' / hooks.NAME).exists())

    def test_symlink_is_not_followed(self):
        self.dest.mkdir()
        (self.dest / 'post-boot.d').symlink_to(self.dest, target_is_directory=True)
        with self.assertRaises(RuntimeError): hooks.manage('install')
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
