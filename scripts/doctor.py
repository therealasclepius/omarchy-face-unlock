#!/usr/bin/env python3
"""Read-only readiness and compatibility checks. Never captures camera frames."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tomllib
from manage import RULES, rules

ROOT = Path(__file__).resolve().parent.parent
ID = 'io.github.therealasclepius.face-unlock'
FACE_PAM = Path('/etc/pam.d/omarchy-lock-face')


def command(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, '', 'unavailable')


def compatibility():
    stock = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    baseline = json.loads((ROOT / 'upstream-lock.json').read_text())
    differences = []
    for profile in baseline['profiles']:
        changed = []
        for name, digest in profile['sha256'].items():
            try:
                actual = hashlib.sha256((stock / name).read_bytes()).hexdigest()
            except OSError:
                actual = None
            if actual != digest:
                changed.append(name)
        if not changed:
            print('OK: lock, host loader and shared UI match reviewed Omarchy ' + profile['ref'])
            return True
        differences.append((profile['ref'], changed))
    ref, changed = min(differences, key=lambda item: len(item[1]))
    print('REVIEW: Omarchy differs from reviewed ' + ref + ': ' + ', '.join(changed))
    print('Update the plugin and review upstream changes; a mismatch does not itself disable an installed plugin.')
    return False


def face_pam_ready():
    try:
        return rules(FACE_PAM.read_text()) == RULES
    except OSError:
        return False


def runtime_issues(catalog, status):
    """Use lock IPC, not catalog.active: Omarchy 4.0.3 hides auth services."""
    issues = []
    if not isinstance(catalog, list) or not any(
            isinstance(p, dict) and p.get('id') == ID and p.get('enabled') is True
            for p in catalog):
        issues.append('Face Unlock is not enabled. Run ./repair if you want to restore it.')
        return issues
    if not isinstance(status, dict):
        return ['Lock IPC unavailable. Unlock first; restore the stock locker if necessary (see README).']
    expected = json.loads((ROOT / 'manifest.json').read_text())['version']
    if status.get('pluginId') != ID or status.get('pluginVersion') != expected:
        issues.append('The running locker differs from the installed plugin. Run ./repair while unlocked to reload it.')
    if status.get('passwordPam') is not True:
        issues.append('Password PAM is not ready; restore Omarchy password authentication before repair.')
    if status.get('face') is not True:
        issues.append('Face backend is not ready. Check the daemon, enrollment and dedicated PAM service with ./doctor.')
    return issues


def read_json_command(*args):
    result = command(*args)
    if result.returncode:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


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
    ]:
        result = command(*cmd)
        good = good and result.returncode == 0
        detail = result.stdout.strip() if label == 'Facelock version' else ''
        print(('OK: ' if result.returncode == 0 else 'CHECK: ') + label + (' — ' + detail if detail else ''))
    pam_ready = face_pam_ready()
    print(('OK: ' if pam_ready else 'CHECK: ') + 'Dedicated face PAM rules')
    good = good and pam_ready
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
    issues = runtime_issues(read_json_command('omarchy', 'plugin', 'list', '--json'),
                            read_json_command('omarchy-shell', 'lock', 'status'))
    for issue in issues:
        print('CHECK: ' + issue)
    if not issues:
        print('OK: current Face Unlock version is running with password and face readiness')
    result = command('python3', str(ROOT / 'scripts/auth_manage.py'), 'status')
    print(result.stdout.strip() if result.returncode == 0 else 'CHECK: optional authentication status unavailable')
    print('Performance/recognition require a real lock-screen test; these checks do not prove a face match.')
    return 0 if good and not issues else 1


if __name__ == '__main__':
    raise SystemExit(main())
