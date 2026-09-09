#!/usr/bin/env python3
"""Opt-in sudo/polkit PAM management with exact backups and conservative undo."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tomllib

from manage import atomic_write, check_trusted, rules, CONFIG, STATE_DIR

ETC = Path('/etc/pam.d')
VENDOR = Path('/usr/lib/pam.d')
STATE = STATE_DIR / 'auth-state.json'
SERVICES = ('sudo', 'polkit-1')
BLOCK = ('# BEGIN omarchy-face-unlock optional authentication\n'
         'auth sufficient pam_facelock.so\n'
         '# END omarchy-face-unlock optional authentication\n')
BASES = {
    'sudo': [
        ['auth include system-auth', 'account include system-auth', 'session include system-auth'],
        ['auth include system-auth', 'account include system-auth', 'session include system-auth',
         'session optional pam_systemd.so class=none'],
    ],
    'polkit-1': [
        ['auth include system-auth', 'account include system-auth',
         'password include system-auth', 'session include system-auth'],
    ],
}


def effective(service):
    path = ETC / service
    check_trusted(path, missing=True)
    if not path.exists():
        path = VENDOR / service
        check_trusted(path)
    return path


def save(state):
    atomic_write(STATE, json.dumps(state, indent=2) + '\n')


def preflight(services, allow_session_bypass=False):
    check_trusted(CONFIG)
    config = tomllib.loads(CONFIG.read_text())
    security = config.get('security', {})
    if security.get('disabled', False):
        raise RuntimeError('Facelock is disabled in its configuration.')
    if not security.get('require_ir', True) or not security.get('require_frame_variance', True):
        raise RuntimeError('IR and frame-variance protection must be enabled first.')
    if config.get('encryption', {}).get('method', 'keyfile') == 'none':
        raise RuntimeError('Enable Facelock encryption first.')
    if not security.get('abort_if_ssh', True):
        if not allow_session_bypass:
            raise RuntimeError('The shared backend has abort_if_ssh=false. Remote callers may '
                               'trigger admin/vault scans. Review README and explicitly pass '
                               '--allow-session-bypass to retain this existing choice.')
        print('Existing session bypass accepted: remote callers may trigger authentication scans.')
    policy = security.get('pam_policy', {})
    for service in services:
        if service in policy.get('denied_services', []) or (
                policy.get('allowed_services') and service not in policy['allowed_services']):
            raise RuntimeError(f'Facelock policy excludes {service}; review the shared policy manually.')
    check_trusted(Path('/usr/lib/security/pam_facelock.so'))


def prepare(service):
    source = effective(service)
    text = source.read_text()
    if rules(text) not in BASES[service] or 'omarchy-face-unlock' in text:
        raise RuntimeError(f'{service}: unsupported/custom PAM stack; refusing to bypass or '
                           'overwrite existing authentication. Only reviewed Arch defaults are supported.')
    # Place immediately before the sole stock auth include; preserve all original bytes.
    lines = text.splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if line.lstrip().startswith('auth'))
    applied = ''.join(lines[:index]) + BLOCK + ''.join(lines[index:])
    return {'before': text if source.parent == ETC else None,
            'baseline': text, 'applied': applied,
            'mode': source.stat().st_mode & 0o777}


def current(service):
    path = ETC / service
    check_trusted(path, missing=True)
    return path.read_text() if path.exists() else None


def enable(state, services):
    plans = {}
    for service in services:
        if service in state:
            content = current(service)
            if content == state[service]['applied']:
                continue
            if content == state[service]['before']:
                plans[service] = prepare(service)  # Recover an interrupted install/undo.
                continue
            raise RuntimeError(f'{service}: managed file changed; preserve it for manual review.')
        plans[service] = prepare(service)
    # Validate every service before recording intent or changing either file.
    state.update(plans)
    save(state)
    try:
        for service, entry in plans.items():
            atomic_write(ETC / service, entry['applied'], entry['mode'])
    except OSError:
        # Restore any completed writes. Journal also supports recovery after process death.
        disable(state, list(plans))
        raise
    for service in services:
        print(f'Enabled: {service} — face first, existing password fallback retained.')


def disable(state, services):
    for service in services:
        if service in state and current(service) not in (state[service]['applied'], state[service]['before']):
            raise RuntimeError(f'{service}: managed file changed; preserving it and its backup for manual review.')
        if service in state and state[service]['before'] is None and current(service) is not None:
            check_trusted(VENDOR / service)
    for service in services:
        if service not in state:
            print(f'Unmanaged: {service}; no changes made.')
            continue
        entry = state[service]
        if current(service) != entry['before']:
            if entry['before'] is None:
                # Removing our override exposes the current package-provided PAM service.
                (ETC / service).unlink()
            else:
                atomic_write(ETC / service, entry['before'], entry['mode'])
        del state[service]
        save(state)
        print(f'Restored: {service}.')


def status():
    for service in SERVICES:
        text = effective(service).read_text()
        ours = BLOCK in text
        face = any('pam_facelock.so' in line for line in rules(text))
        label = 'enabled (plugin block)' if ours else 'external face configuration' if face else 'disabled'
        print(f'{service}: {label}')
    print('Status checks configuration only; a live test is needed to verify authentication.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'disable', 'status'])
    parser.add_argument('--sudo', action='store_true')
    parser.add_argument('--polkit', action='store_true')
    parser.add_argument('--all', action='store_true', help='Disable both integrations')
    parser.add_argument('--allow-session-bypass', action='store_true')
    args = parser.parse_args()
    if args.allow_session_bypass and args.action != 'enable':
        parser.error('--allow-session-bypass is only supported with enable')
    services = [s for s, flag in [('sudo', args.sudo), ('polkit-1', args.polkit)] if flag]
    if args.action == 'status':
        if services or args.all or args.allow_session_bypass:
            parser.error('status takes no options')
        status()
        return
    if args.all:
        if args.action != 'disable':
            parser.error('--all is only supported for disable; select each integration explicitly')
        services = list(SERVICES)
    if not services:
        parser.error('select --sudo and/or --polkit')
    if os.geteuid() != 0:
        parser.error('run via ./auth in a terminal')
    check_trusted(STATE_DIR, missing=True)
    STATE_DIR.mkdir(mode=0o700, exist_ok=True)
    check_trusted(STATE, missing=True)
    lock = STATE_DIR / '.lock'
    check_trusted(lock, missing=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        if not isinstance(state, dict) or any(s not in SERVICES for s in state):
            raise RuntimeError('Unrecognized authentication state; preserving it.')
        if args.action == 'enable':
            preflight(services, args.allow_session_bypass)
            enable(state, services)
        else:
            disable(state, services)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Face Unlock: {error}')
