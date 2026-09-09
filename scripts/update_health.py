#!/usr/bin/env python3
"""Bounded, read-only post-update/login health check. Never captures a face."""
import argparse
import time
from doctor import compatibility, command, read_json_command, runtime_issues, face_pam_ready


def check(attempts=6, delay=2):
    compatible = compatibility()
    issues = []
    for attempt in range(attempts):
        catalog = read_json_command('omarchy', 'plugin', 'list', '--json')
        status = read_json_command('omarchy-shell', 'lock', 'status')
        issues = runtime_issues(catalog, status)
        daemon = command('systemctl', 'is-active', 'facelock-daemon').returncode == 0
        enabled = command('systemctl', 'is-enabled', 'facelock-daemon').returncode == 0
        if not face_pam_ready():
            issues.append('Dedicated face PAM is missing or changed. Run ./doctor; repair refuses custom PAM rules.')
        if not daemon:
            issues.append('Facelock daemon is not running. Run ./repair while unlocked.')
        if not enabled:
            issues.append('Facelock daemon is not enabled for boot. Run ./repair while unlocked.')
        if not issues:
            break
        if attempt + 1 < attempts:
            time.sleep(delay)
    if not compatible:
        issues.insert(0, 'Omarchy compatibility needs review. Update the Face Unlock plugin, then run ./doctor.')
    for issue in issues:
        print('Face Unlock: ' + issue)
    if not issues:
        print('Face Unlock: installed version is running; password, face readiness and boot service are ready.')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notify', action='store_true')
    args = parser.parse_args()
    issues = check()
    if issues and args.notify:
        command('notify-send', '--app-name=Face Unlock', 'Face Unlock needs attention',
                'After updating Omarchy, run the plugin’s ./doctor. Use ./repair while unlocked for a stale shell or missing integration.')
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
