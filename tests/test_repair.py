"""Run the real repair wrapper with fake desktop/backend commands; no system writes."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ID = 'io.github.therealasclepius.face-unlock'


@unittest.skipIf(os.geteuid() == 0 or not shutil.which('jq') or not shutil.which('script'),
                 'requires a non-root user, jq and util-linux script')
class RepairTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        plugin = self.root / 'plugin'
        (plugin / 'scripts').mkdir(parents=True)
        shutil.copy(ROOT / 'repair', plugin / 'repair')
        shutil.copy(ROOT / 'scripts/common.sh', plugin / 'scripts/common.sh')
        # Fixture-only helper: production always uses the absolute packaged path.
        common = plugin / 'scripts/common.sh'
        common.write_text(common.read_text().replace('/usr/bin/omarchy-face-unlock-helper', str(self.root / 'bin/omarchy-face-unlock-helper')))
        mock = self.root / 'bin'
        mock.mkdir()
        self.log = self.root / 'calls'
        commands = {
            'omarchy-shell': 'printf "%s\\n" "$TEST_STATUS"',
            'omarchy-plugin-catalog': 'printf "%s\\n" "$TEST_INSTALLED"',
            'omarchy': 'if [[ "$*" == "plugin list --json" ]]; then printf "%s\\n" "$TEST_CATALOG"; fi',
            'facelock': '''if [[ "$1" == capabilities ]]; then
  printf '%s\\n' is-enrolled pam-status pam-if-present setup-no-pam setup-systemd
elif [[ "$1" == is-enrolled ]]; then exit "${TEST_ENROLLED_RC:-0}"; fi''',
            'omarchy-face-unlock-helper': 'printf "%s\\n" "${TEST_HELPER_PROTOCOL:-1}"',
            'sudo': 'if [[ "$*" == *"omarchy-face-unlock-helper lock configure" ]]; then exit "${TEST_CONFIGURE_RC:-0}"; fi',
            'python3': 'if [[ "$1" == *doctor.py ]]; then exit "${TEST_COMPAT_RC:-0}"; fi',
        }
        for name, body in commands.items():
            path = mock / name
            path.write_text('#!/bin/bash\nprintf "%s\\n" "' + name + ' $*" >> "$TEST_LOG"\n' + body + '\n')
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=str(mock) + ':' + os.environ['PATH'],
                        TEST_LOG=str(self.log), TEST_STATUS=json.dumps({'locked': False, 'passwordPam': True}),
                        TEST_INSTALLED=json.dumps([{'id': ID, 'sourceDir': str(plugin)}]),
                        TEST_CATALOG=json.dumps([{'id': ID, 'enabled': True, 'clonedFrom': 'omarchy.lock'}]))
        self.plugin = plugin

    def run_repair(self, **env):
        result = subprocess.run(['script', '-q', '-e', '-c', 'bash ' + shlex.quote(str(self.plugin / 'repair')), '/dev/null'],
                                env=dict(self.env, **env), capture_output=True, text=True, timeout=10)
        return result, self.log.read_text()

    def test_repair_reuses_backend_without_security_or_admin_flags(self):
        result, calls = self.run_repair()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('sudo /usr/bin/systemctl enable --now facelock-daemon', calls)
        self.assertIn('omarchy-face-unlock-helper lock configure\n', calls)
        self.assertIn('omarchy plugin enable ' + ID, calls)
        self.assertIn('omarchy restart shell', calls)
        for forbidden in ['--uwsm-compat', '--natural-motion', 'auth_manage.py', 'enroll --', 'ensure-key']:
            self.assertNotIn(forbidden, calls)

    def test_locked_unreviewed_and_conflicting_locker_stop_before_sudo(self):
        for env in [
            {'TEST_STATUS': json.dumps({'locked': True, 'passwordPam': True})},
            {'TEST_COMPAT_RC': '1'},
            {'TEST_CATALOG': json.dumps([{'id': 'someone.lock', 'enabled': True, 'clonedFrom': 'omarchy.lock'}])},
        ]:
            with self.subTest(env=env):
                self.log.write_text('')
                result, calls = self.run_repair(**env)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('sudo ', calls)
                self.assertNotIn('omarchy restart shell', calls)

    def test_missing_enrollment_and_pam_failure_stop_before_enabling_plugin(self):
        for env in [{'TEST_ENROLLED_RC': '1'}, {'TEST_CONFIGURE_RC': '1'}]:
            with self.subTest(env=env):
                self.log.write_text('')
                result, calls = self.run_repair(**env)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('omarchy plugin enable', calls)
                self.assertNotIn('omarchy restart shell', calls)

    def test_incompatible_or_missing_helper_stops_before_sudo(self):
        result, calls = self.run_repair(TEST_HELPER_PROTOCOL='2')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('sudo ', calls)
        self.log.write_text('')
        (self.root / 'bin/omarchy-face-unlock-helper').unlink()
        result, calls = self.run_repair()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('sudo ', calls)


if __name__ == '__main__':
    unittest.main()
