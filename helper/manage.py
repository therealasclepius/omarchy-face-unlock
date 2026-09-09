#!/usr/bin/env python3
"""Privileged, bounded management of one PAM service and two opt-in settings."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import tomllib

CONFIG = Path('/etc/facelock/config.toml')
PAM = Path('/etc/pam.d/omarchy-lock-face')
STATE_DIR = Path('/var/lib/omarchy-face-unlock')
STATE = STATE_DIR / 'state.json'
FACELOCK = '/usr/bin/facelock'
HEADER = '# Managed by omarchy-face-unlock\n'
SKELETON = '#%PAM-1.0\n' + HEADER + 'auth required pam_deny.so\naccount include system-local-login\n'
RULES = ['auth sufficient pam_facelock.so', 'auth required pam_deny.so',
         'account include system-local-login']
OPTIONS = {'abort_if_ssh': False, 'frame_variance_max_similarity': 0.995}


def rules(text):
    return [' '.join(line.split()) for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def check_trusted(path, missing=False):
    """Never follow a symlink or read state controlled by an unprivileged user."""
    for part in [*reversed(path.parents), path]:
        try:
            st = part.lstat()
        except FileNotFoundError:
            if part == path and missing:
                return
            raise
        if stat.S_ISLNK(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise RuntimeError(f'Unsafe ownership, permissions, or symlink: {part}')


def atomic_write(path, text, mode=0o600):
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def set_security(text, key, value):
    """Edit a scalar in a normal [security] section, preserving unrelated text."""
    if key not in OPTIONS:
        raise ValueError('Unsupported setting')
    before = tomllib.loads(text)
    section = re.search(r'^\[security\][ \t]*(?:#.*)?$', text, re.M)
    if not section:
        raise ValueError('Expected a standalone [security] section; edit the unusual TOML layout manually.')
    end = re.search(r'^\s*\[', text[section.end():], re.M)
    stop = section.end() + end.start() if end else len(text)
    body = text[section.end():stop]
    line = re.compile(r'^[ \t]*' + re.escape(key) + r'[ \t]*=.*(?:\n|$)', re.M)
    present = key in before.get('security', {})
    if present and len(line.findall(body)) != 1:
        raise ValueError('Unsupported setting layout; refusing to rewrite it.')
    replacement = '' if value is None else f'{key} = {json.dumps(value)}\n'
    if present:
        body = line.sub(replacement, body, count=1)
    elif value is not None:
        body = '\n' + replacement + body
    new = text[:section.end()] + body + text[stop:]
    expected = dict(before.get('security', {}))
    if value is None:
        expected.pop(key, None)
    else:
        expected[key] = value
    after = tomllib.loads(new)
    if after != dict(before, security=expected):
        raise ValueError('TOML edit would affect unrelated settings')
    return new


def restore_options(text, changes):
    for key, change in changes.items():
        current = tomllib.loads(text).get('security', {}).get(key)
        if current == change['applied']:
            text = set_security(text, key, change['previous'])
        else:
            print(f'Preserving subsequently changed setting: security.{key}')
    return text


def save_state(state):
    atomic_write(STATE, json.dumps(state, indent=2) + '\n')


def run(*args):
    subprocess.run(args, check=True)


def configure(state, keys):
    original = CONFIG.read_text()
    updated = original
    changes = dict(state.get('settings', {}))
    for key in keys:
        previous = tomllib.loads(updated).get('security', {}).get(key)
        if previous == OPTIONS[key]:
            continue  # An existing choice is not owned by this installer.
        changes.setdefault(key, {'previous': previous, 'applied': OPTIONS[key]})
        updated = set_security(updated, key, OPTIONS[key])
    # Validate all existing state before changing any authentication file.
    if PAM.exists():
        content = PAM.read_text()
        expected = rules(SKELETON) if state.get('pam_owned') else None
        if rules(content) != RULES and rules(content) != expected:
            raise RuntimeError('Existing omarchy-lock-face uses another configuration; refusing to overwrite it.')
        owned = state.get('pam_owned', False)
    else:
        owned = True
    state.update(settings=changes, pam_owned=owned)
    save_state(state)  # Crash recovery: record intent before system edits.
    if not PAM.exists():
        atomic_write(PAM, SKELETON, 0o644)
    if owned:
        run(FACELOCK, 'pam', 'add', '--service', 'omarchy-lock-face', '--no-confirm')
        if rules(PAM.read_text()) != RULES:
            raise RuntimeError('Unexpected PAM result; stock password lane is unchanged.')
        state['pam_sha256'] = hashlib.sha256(PAM.read_bytes()).hexdigest()
        save_state(state)
    if updated != original:
        if not (STATE_DIR / 'config.before.toml').exists():
            atomic_write(STATE_DIR / 'config.before.toml', original)
        atomic_write(CONFIG, updated, 0o644)
    run('/usr/bin/systemctl', 'restart', 'facelock-daemon')
    print('Dedicated face PAM service ready. Other PAM services were not changed.')


def remove(state):
    if state.get('pam_owned') and PAM.exists():
        content = PAM.read_text()
        digest = hashlib.sha256(PAM.read_bytes()).hexdigest()
        if digest != state.get('pam_sha256') and content != SKELETON:
            raise RuntimeError('Managed PAM service changed since setup; preserving it for manual review.')
        run(FACELOCK, 'pam', 'remove', '--service', 'omarchy-lock-face', '--if-present', '--no-confirm')
        if rules(PAM.read_text()) != rules(SKELETON):
            raise RuntimeError('Unexpected PAM removal result; preserving the service.')
        PAM.unlink()
    original = CONFIG.read_text()
    updated = restore_options(original, state.get('settings', {}))
    if updated != original:
        atomic_write(CONFIG, updated, 0o644)
    save_state({'settings': {}, 'pam_owned': False})
    run('/usr/bin/systemctl', 'restart', 'facelock-daemon')
    print('Installer-owned changes removed; pre-existing settings and biometric data retained.')


def ensure_key():
    encryption = tomllib.loads(CONFIG.read_text()).get('encryption', {})
    method = encryption.get('method', 'keyfile')
    if method == 'none':
        raise RuntimeError('Enable encryption in Facelock before setting up this plugin.')
    if method == 'keyfile':
        path = Path(encryption.get('key_path', '/etc/facelock/encryption.key'))
        check_trusted(path, missing=True)
        if not path.exists():
            # Handles Facelock 0.2.1's missing-key noninteractive setup case.
            # Backend refuses generation if encrypted templates already exist.
            run(FACELOCK, 'tpm', 'encrypt', '--generate-key')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['configure', 'remove', 'ensure-key'])
    parser.add_argument('--uwsm-compat', action='store_true')
    parser.add_argument('--natural-motion', action='store_true')
    args = parser.parse_args()
    if args.action != 'configure' and (args.uwsm_compat or args.natural_motion):
        parser.error('security options are only supported with configure')
    if os.geteuid() != 0:
        parser.error('Run the packaged helper via sudo; paths are fixed.')
    check_trusted(CONFIG)
    check_trusted(PAM, missing=True)
    check_trusted(STATE_DIR, missing=True)
    STATE_DIR.mkdir(mode=0o700, exist_ok=True)
    check_trusted(STATE, missing=True)
    lock = STATE_DIR / '.lock'
    check_trusted(lock, missing=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        state = json.loads(STATE.read_text()) if STATE.exists() else {'settings': {}, 'pam_owned': False}
        if args.action == 'configure':
            keys = [key for flag, key in [(args.uwsm_compat, 'abort_if_ssh'),
                    (args.natural_motion, 'frame_variance_max_similarity')] if flag]
            configure(state, keys)
        elif args.action == 'remove':
            remove(state)
        else:
            ensure_key()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Face Unlock: {error}')
