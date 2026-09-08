#!/usr/bin/env python3
"""Read-only readiness and compatibility checks. Never captures camera frames."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parent.parent
ID = 'io.github.therealasclepius.face-unlock'


def command(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, '', 'unavailable')


def compatibility():
    stock = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy')) / 'shell/plugins/lock'
    baseline = json.loads((ROOT / 'upstream-lock.json').read_text())
    changed = []
    for name, digest in baseline['sha256'].items():
        path = stock / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            changed.append(name)
    if changed:
        print('REVIEW: stock lock differs from tested Omarchy ' + baseline['omarchy_version'] + ': ' + ', '.join(changed))
        print('The plugin bundles a lock-screen copy. Review upstream changes before enabling it.')
        return False
    print('OK: stock lock matches tested Omarchy ' + baseline['omarchy_version'])
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compat-only', action='store_true')
    args = parser.parse_args()
    good = compatibility()
    if args.compat_only:
        return 0 if good else 1
    for label, cmd in [
        ('Facelock version', ['facelock', '--version']),
        ('Daemon running', ['systemctl', 'is-active', 'facelock-daemon']),
        ('Daemon enabled at boot', ['systemctl', 'is-enabled', 'facelock-daemon']),
        ('Current user enrolled', ['facelock', 'is-enrolled', '--quiet']),
        ('Face PAM configured', ['facelock', 'pam', 'status', '--service', 'omarchy-lock-face', '--json']),
    ]:
        result = command(*cmd)
        good = good and result.returncode == 0
        detail = result.stdout.strip() if label == 'Facelock version' else ''
        print(('OK: ' if result.returncode == 0 else 'CHECK: ') + label + (' — ' + detail if detail else ''))
    try:
        config = tomllib.loads(Path('/etc/facelock/config.toml').read_text())
        security = config.get('security', {})
        print('Camera: ' + str(config.get('device', {}).get('path', 'auto')))
        print('Local-session check: ' + ('enabled' if security.get('abort_if_ssh', True) else 'disabled (compatibility setting)'))
        print('Movement similarity limit: ' + str(security.get('frame_variance_max_similarity', 0.985)))
        if not security.get('require_ir', True) or not security.get('require_frame_variance', True):
            print('CHECK: IR or movement protection has been disabled in the backend config')
            good = False
    except (OSError, ValueError):
        print('CHECK: backend configuration unavailable or invalid')
        good = False
    result = command('omarchy', 'plugin', 'list', '--json')
    try:
        enabled = any(p['id'] == ID and p.get('enabled') for p in json.loads(result.stdout))
    except (ValueError, TypeError, KeyError):
        enabled = False
    print(('OK: ' if enabled else 'CHECK: ') + 'Face Unlock plugin enabled')
    result = command('python3', str(ROOT / 'scripts/auth_manage.py'), 'status')
    print(result.stdout.strip() if result.returncode == 0 else 'CHECK: optional authentication status unavailable')
    print('Performance/recognition require a real lock-screen test; these checks do not prove a face match.')
    return 0 if good and enabled else 1


if __name__ == '__main__':
    raise SystemExit(main())
