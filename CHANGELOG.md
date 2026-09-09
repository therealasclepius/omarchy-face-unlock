# Changelog

## 0.4.0

- Replace sudo execution of plugin-directory Python with a separately packaged,
  root-owned helper for setup, repair, optional authentication, and removal.
- Isolate privileged Python imports, check installed paths, clear the inherited
  environment, and restrict the helper to fixed operations and destinations.
- Require the signed helper package before setup/repair; document authenticated
  installation, independent updates, and signing-key trust requirements.
- Retain existing installer journals and conservative undo behavior.
- Add privilege-boundary regression tests and an Arch package recipe.

## 0.3.0

- Retry temporary backend-readiness failures at startup, lock and wake without consuming a pending scan or overriding Escape.
- Enable the Facelock daemon at boot when reusing an existing installation.
- Add conservative `repair` and read-only post-update/login health hooks, also installed when existing users first load this version.
- Detect stale running plugin versions and respect Omarchy 4.0.3's private authentication-service store.
- Check reviewed 4.0.2/4.0.3 lock, loader and shared UI fingerprints; add daily latest-release compatibility CI.
- Add regression coverage for startup recovery, stale services, hidden authentication services, host changes, and hook lifecycle.


- Start a face scan automatically once the lock is secure and the backend is ready.
- Start a fresh scan on mouse or keyboard wake after the locker blanks the display.
- Preserve Escape cancellation, manual Enter retry, password fallback, and bounded attempts.
- Add automatic-trigger checks for readiness, password entry, cancellation, and wake.
- Validate loading in the live Omarchy shell; physical automatic lock/wake testing remains pending.

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
  on the Dell XPS 13 with Facelock 0.2.1. Also confirm an actual 1Password face unlock
  with system authentication enabled.

## 0.1.0

- Add explicit Enter-to-scan face unlock with parallel password fallback.
- Add Escape cancellation and separate face-status messages.
- Add portable camera/enrollment setup, optional UWSM and movement settings,
  conservative removal, and read-only diagnostics.
- Test on Omarchy 4.0.2-1 and a Dell XPS 13 DX13260 IR camera with Facelock 0.2.1.
