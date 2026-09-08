# Changelog

## 0.2.0

- Add independently selectable sudo and polkit face authentication with `auth enable`.
- Support 1Password through its native Linux system-authentication setting.
- Preserve password fallback, original PAM account/session rules, and package-owned files.
- Add exact backups, conservative independent removal, recovery from interrupted writes,
  and explicit acknowledgement of an existing shared-backend session bypass.
- Extend doctor and full removal to cover optional authentication integrations.
- Add 12 installer tests covering rollback, custom-stack refusal, vendor overrides,
  service selection, and backend policy preservation.
- Physically verify sudo and polkit face success plus covered-camera password fallback
  on the Dell XPS 13 with Facelock 0.2.1. App-specific 1Password verification is separate.

## 0.1.0

- Add explicit Enter-to-scan face unlock with parallel password fallback.
- Add Escape cancellation and separate face-status messages.
- Add portable camera/enrollment setup, optional UWSM and movement settings,
  conservative removal, and read-only diagnostics.
- Test on Omarchy 4.0.2-1 and a Dell XPS 13 DX13260 IR camera with Facelock 0.2.1.
