"""Exercise the privilege entry point without sudo or authentication changes."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'helper/omarchy-face-unlock-helper'
loader = importlib.machinery.SourceFileLoader('entry', str(ENTRY))
spec = importlib.util.spec_from_loader(loader.name, loader)
entry = importlib.util.module_from_spec(spec)
loader.exec_module(entry)


class BoundaryTests(unittest.TestCase):
    def test_installed_module_selection_ignores_caller_code_and_cleans_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / 'installed'
            caller = root / 'plugin'
            library.mkdir()
            caller.mkdir()
            for name in ('manage.py', 'auth_manage.py', 'sitecustomize.py'):
                (caller / name).write_text('raise RuntimeError("caller code executed")\n')
            (library / 'manage.py').write_text(
                'import os, sys\n'
                'def main():\n'
                '    assert os.getcwd() == "/"\n'
                '    assert "PYTHONPATH" not in os.environ\n'
                '    assert "FACELOCK_CONFIG" not in os.environ\n'
                '    assert os.environ["PATH"] == "/usr/bin"\n'
                '    assert sys.argv[1:] == ["configure"]\n'
                '    print("packaged module selected")\n')
            (library / 'auth_manage.py').write_text('def main(): raise AssertionError("wrong action")\n')
            # Simulate the installed paths only. The ownership checker is tested
            # independently; no root files or real authentication are accessed.
            driver = (
                'from pathlib import Path\nimport sys\n'
                f'p = Path({str(ENTRY)!r})\n'
                'ns = {"__name__": "fixture", "__file__": str(p)}\n'
                'exec(compile(p.read_text(), str(p), "exec"), ns)\n'
                f'ns.update(ENTRY=p, LIB=Path({str(library)!r}), trusted=lambda p: None)\n'
                'sys.argv = [str(p), "lock", "configure"]\nns["main"]()\n')
            result = subprocess.run(['/usr/bin/python3', '-I', '-c', driver], cwd=caller,
                                    env=dict(os.environ, PYTHONPATH=str(caller),
                                             PYTHONHOME=str(caller), FACELOCK_CONFIG='/tmp/evil'),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'packaged module selected')

    def test_checkout_refused_before_import_even_with_poisoned_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'executed'
            payload = f'open({str(marker)!r}, "w").write("executed")\nraise RuntimeError("poison")\n'
            for name in ('manage.py', 'auth_manage.py', 'sitecustomize.py', 'pathlib.py'):
                (root / name).write_text(payload)
            result = subprocess.run(
                ['/usr/bin/python3', '-I', str(ENTRY), '--protocol'], cwd=root,
                env=dict(os.environ, PYTHONPATH=tmp, PYTHONHOME=tmp),
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Install the signed system package', result.stderr)
            self.assertFalse(marker.exists())

    def test_nonisolated_invocation_refused(self):
        result = subprocess.run([sys.executable, str(ENTRY), '--protocol'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('isolated Python', result.stderr)

    def test_trust_checks_reject_writable_owned_or_symlinked_ancestors(self):
        target = Path('/usr/lib/omarchy-face-unlock/manage.py')
        good = SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o755)
        for bad in (SimpleNamespace(st_uid=1000, st_mode=stat.S_IFDIR | 0o755),
                    SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o775),
                    SimpleNamespace(st_uid=0, st_mode=stat.S_IFLNK | 0o777)):
            for unsafe in [*target.parents, target]:
                def info(path):
                    return bad if path == unsafe else good
                with self.subTest(unsafe=unsafe, bad=bad), patch.object(Path, 'lstat', info):
                    with self.assertRaises(RuntimeError):
                        entry.trusted(target)
        with patch.object(Path, 'lstat', return_value=good):
            entry.trusted(target)

    def test_wrappers_do_not_elevate_plugin_code(self):
        for name in ('setup', 'repair', 'auth', 'remove', 'enroll'):
            for line in (ROOT / name).read_text().splitlines():
                if line.startswith('sudo '):
                    self.assertNotIn('PLUGIN_DIR', line)
                    self.assertNotIn('python', line)
                    self.assertNotIn('bash', line)

    def test_helper_rejects_arbitrary_paths_and_unknown_actions(self):
        # Test the actual argument parsers: invalid arguments must fail before
        # checking root or accessing configuration, and cannot choose a script.
        for module in ('manage.py', 'auth_manage.py'):
            for args in (['/tmp/evil.py'], ['configure', '--config', '/tmp/evil']):
                result = subprocess.run([sys.executable, str(ROOT / 'helper' / module), *args],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn('error:', result.stderr)


if __name__ == '__main__':
    unittest.main()
