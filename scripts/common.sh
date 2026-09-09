#!/bin/bash
PLUGIN_ID=io.github.therealasclepius.face-unlock
PLUGIN_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

fail() { printf 'Face Unlock: %s\n' "$*" >&2; exit 1; }
require_desktop() {
  (( EUID != 0 )) || fail 'Run this as your desktop user, not with sudo.'
  command -v omarchy >/dev/null || fail 'Omarchy 4 with Quickshell is required.'
  local status
  status=$(omarchy-shell lock status) || fail 'The Omarchy lock service is unavailable.'
  jq -e '.locked == false and .passwordPam == true' <<<"$status" >/dev/null ||
    fail 'Unlock the desktop and configure password authentication first.'
}
require_installed() {
  local catalog
  catalog=$(omarchy-plugin-catalog) || fail 'Cannot read the plugin catalog.'
  jq -e --arg id "$PLUGIN_ID" --arg dir "$PLUGIN_DIR" \
    'any(.[]; .id == $id and .sourceDir == $dir)' <<<"$catalog" >/dev/null ||
    fail 'Install with omarchy plugin add first, then run setup from the installed directory.'
}
require_facelock() {
  command -v facelock >/dev/null || fail 'Install facelock-bin first.'
  local caps capability
  caps=$(facelock capabilities) || fail 'Facelock 0.2.1 or a compatible newer build is required.'
  for capability in is-enrolled pam-status pam-if-present setup-no-pam setup-systemd; do
    grep -Fxq "$capability" <<<"$caps" || fail "Facelock lacks $capability. Update the backend."
  done
}

require_helper() {
  [[ -x /usr/bin/omarchy-face-unlock-helper ]] ||
    fail 'Install the signed omarchy-face-unlock-helper package first; see packaging/README.md. Setup cannot install privileged code from this plugin.'
  [[ $(/usr/bin/omarchy-face-unlock-helper --protocol) == 1 ]] ||
    fail 'The system helper is incompatible or untrusted; reinstall it from your trusted signed package source.'
}
