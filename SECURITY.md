# Security boundaries

## Privileged code and package trust

The plugin never passes a plugin-directory script to sudo. Setup, repair, auth,
and removal call the fixed `/usr/bin/omarchy-face-unlock-helper` executable.
That separately installed package starts `/usr/bin/python3 -I`, excluding
the current directory, caller `PYTHONPATH`/`PYTHONHOME`, and user site packages.
Before adding its fixed module directory, the entry point checks ownership,
writability, and symlinks for itself, `/usr/lib/omarchy-face-unlock`, both Python
modules, and every ancestor. All must be root-owned and not group/world-writable.
It clears the inherited environment before invoking the backend and uses fixed
system paths. Its interface accepts only enumerated actions and options, never
code, arbitrary module names, target paths, or configuration snippets.

Installation and updates require pacman signature verification against an
administrator-trusted signing key, as described in [packaging/README.md](packaging/README.md).
The signing fingerprint must be authenticated separately from the plugin checkout.
There is no `sudo cp`, checkout installer, unsigned-package fallback, automatic
key trust, sudoers exception, or helper self-update. The package has no install
hooks and changes no authentication settings until explicitly invoked.
Missing or incompatible helpers stop setup/repair before privileged changes.
Removing the helper package itself does not restore PAM; run plugin removal first.

This boundary protects the helper's elevated imports from writable plugin files.
It does not sandbox the plugin or make a compromised desktop user trustworthy:
a replaced wrapper could still ask a user to approve a different sudo command,
and existing general-purpose sudo authorization is outside this helper's control.

## Authentication behavior

Only a successful PAM result from an active face scan unlocks the session. Cancellation, timeout, errors, unavailable backends, and failed recognition retain the lock. Password authentication uses a separate, unchanged PAM service. Escape aborts the face conversation, and password typing remains available during scans.

Screen-lock scans start automatically after the lock becomes secure and when mouse or keyboard activity wakes a display blanked by this locker. A visible enrolled face can therefore unlock a newly locked session without an Enter confirmation. Escape cancels both pending and active scans; ordinary mouse movement while the display remains awake does not restart a cancelled scan. Each wake permits one automatic attempt, with the existing timeout, recognition requirements, and password fallback retained.

This plugin runs unsandboxed in Omarchy's shell, like other lock plugins. Review it before installing. Setup/removal require sudo to manage the dedicated lock PAM service, optional Facelock settings, and root-owned installer state. The separate `auth` command can also opt into sudo and/or polkit PAM integration. The installers refuse unexpected existing PAM contents, symlinks, and untrusted system paths. They do not install passwordless sudoers rules or a background privileged installer.

Optional admin authentication inserts `auth sufficient pam_facelock.so` ahead of the reviewed stock service authentication include. Success can satisfy authentication; failure/absence falls through to the original password flow, and existing account/session rules remain. This is sequential fallback, unlike the screen lock's separate password lane. It covers every request through the selected PAM service, including sudo commands and high-privilege polkit actions. Facelock's separate polkit-agent action allowlist does not scope this PAM integration. We continue to use Omarchy's existing polkit agent.

Scans begin automatically for sudo/polkit requests. A face match is not a confirmation of the command or application's intent, and an application can raise an authentication request while the user is looking at the screen. Enabling these integrations grants the biometric authority over admin access and, with 1Password system authentication enabled, the password vault. No Windows Hello/Face ID security equivalence is claimed.

With an existing `abort_if_ssh=false` configuration, optional admin setup requires `--allow-session-bypass`. This retains the already disabled remote/local gate: remote callers can request scans and may satisfy sudo/polkit authentication while the enrolled user is visible. Not editing `sshd` does not prevent sudo from being invoked over SSH. Setup never silently changes the shared backend's policy or IR/movement requirements.

The optional manager restricts writes to `/etc/pam.d/sudo`, `/etc/pam.d/polkit-1`, and its root-owned journal. It records originals before atomic replacement and serializes with lock setup/removal using the same lock file. Repeated installation and interrupted installation/undo are recoverable. It refuses to overwrite or remove subsequently edited files. Vendor-only PAM services are overridden under `/etc`, then exposed again on removal; vendor updates need review while an override is active. Custom PAM stacks are deliberately unsupported by this installer.

`--uwsm-compat` disables the daemon's local-session gate. `--natural-motion` reduces the strictness of the movement check. Both are explicit choices with shared-backend effects, described in the README. The latter is not an equivalent-security optimization. The project has not undergone an independent security audit or broad hardware/presentation-attack evaluation.

Keep your password working. Disk decryption and boot authentication are outside the scope of this plugin. The plugin never ships or uploads face templates, keys, or recordings. Do not attach biometric databases, keyfiles, passwords, or camera captures to public issues.

For problems, open a GitHub issue with Omarchy/Facelock versions, camera model, and redacted error messages. For a suspected vulnerability, use GitHub's private vulnerability reporting if available; otherwise open a minimal issue asking for a private contact without publishing exploitation details.

## Update resilience

Read-only user hooks inspect health after Omarchy updates and login. They do not grant authorization, capture camera data, repair PAM, or automatically re-enable a disabled plugin. They are installed under the user's Omarchy hook directories; modified hooks and symlink paths are preserved/refused. Removing the plugin through `./remove` removes unchanged hooks. Deleting plugin files alone leaves harmless wrappers which exit if their target is missing.

`./repair` is an explicit terminal action gated on an unlocked password-capable desktop and reviewed host code. It refuses another enabled custom locker and uses the existing conservative PAM manager. It retains enrollment and backend security policy, enables the daemon for boot, and does not alter optional admin-auth integrations. Setup now also enables the daemon when reusing an existing backend. Startup availability probes have a timeout and a finite retry budget; readiness never substitutes for successful PAM authentication. The doctor uses lock IPC identity/version rather than the public service map, preserving Omarchy 4.0.3's authentication isolation.
