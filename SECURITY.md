# Security boundaries

Only a successful PAM result from an active face scan unlocks the session. Cancellation, timeout, errors, unavailable backends, and failed recognition retain the lock. Password authentication uses a separate, unchanged PAM service. Escape aborts the face conversation, and password typing remains available during scans.

This plugin runs unsandboxed in Omarchy's shell, like other lock plugins. Review it before installing. Setup/removal require sudo to manage a single dedicated PAM service, optional Facelock settings, and root-owned installer state. The installer refuses unexpected existing PAM contents, symlinks, and untrusted system paths. It does not install a passwordless sudo rule or background privileged installer.

`--uwsm-compat` disables the daemon's local-session gate. `--natural-motion` reduces the strictness of the movement check. Both are explicit choices with shared-backend effects, described in the README. The latter is not an equivalent-security optimization. The project has not undergone an independent security audit or broad hardware/presentation-attack evaluation.

Keep your password working. Disk decryption and boot authentication are outside the scope of this plugin. The plugin never ships or uploads face templates, keys, or recordings. Do not attach biometric databases, keyfiles, passwords, or camera captures to public issues.

For problems, open a GitHub issue with Omarchy/Facelock versions, camera model, and redacted error messages. For a suspected vulnerability, use GitHub's private vulnerability reporting if available; otherwise open a minimal issue asking for a private contact without publishing exploitation details.
