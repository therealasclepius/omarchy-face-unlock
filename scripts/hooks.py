#!/usr/bin/env python3
"""Install/remove only our named, unchanged read-only Omarchy hooks."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
HOOK_ROOT = Path.home() / '.config/omarchy/hooks'
NAME = 'face-unlock-health'


def manage(action):
    source = ROOT / 'scripts/update-health-hook'
    expected = source.read_bytes()
    destinations = [HOOK_ROOT / (event + '.d') / NAME for event in ('post-update', 'post-boot')]
    # Preflight both destinations before making any changes.
    for dest in destinations:
        if any(p.is_symlink() for p in (dest, *dest.parents)):
            raise RuntimeError(f'Refusing symlink hook path: {dest}')
        if dest.exists() and dest.read_bytes() != expected:
            raise RuntimeError(f'Preserving modified hook: {dest}')
    for dest in destinations:
        if action == 'remove':
            dest.unlink(missing_ok=True)
        elif not dest.exists():
            # Use the supported Omarchy installer and a stable basename.
            with tempfile.TemporaryDirectory() as temp:
                staged = Path(temp) / NAME
                staged.write_bytes(expected)
                subprocess.run(['omarchy', 'hook', 'install', dest.parent.name[:-2], str(staged)], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'remove'])
    try:
        manage(parser.parse_args().action)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
