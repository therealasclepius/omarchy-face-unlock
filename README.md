# Face Unlock for Omarchy

Face unlock using an infrared camera and [Facelock](https://github.com/tyvsmith/facelock), with password authentication available while the camera scans.

- A face scan starts automatically once the lock screen is secure and face authentication is ready.
- Waking a display blanked by the lock screen with the mouse or keyboard starts a fresh scan.
- **Enter** on an empty password field retries a scan.
- **Escape** cancels a queued or active scan.
- Type your password at any time; a rejected scan does not unlock the screen.
- Face status appears below the password field, separate from password errors.
- Each automatic attempt is bounded; failed scans do not retry continuously. Automatic scans wait 600 ms and do not start while you are typing or checking a password.

This plugin replaces Omarchy's stock lock plugin through `clonedFrom`. It does **not** patch `/usr/share/omarchy/`. Default setup adds only a dedicated face PAM service. Separately opt into `sudo` and graphical authentication with `./auth` below.

Automatic scanning can unlock immediately after locking if your enrolled face remains visible. After a failed or cancelled scan, press Enter to retry, or let the display blank and wake it again. Opening a laptop lid without mouse or keyboard activity is not a verified automatic-scan trigger.

## Requirements and support

- Omarchy **4.0.2-1** with the Quickshell lock screen. Setup checks the stock QML against the tested copy and stops on differences. This is not a Hyprlock plugin.
- An IR camera supported by Facelock and Linux V4L2. An ordinary RGB webcam is not supported by the default security policy.
- Facelock **0.2.1** or a compatible newer version, available as AUR `facelock-bin`.
- Working password unlock, an interactive terminal, and sudo access for setup.

Physically tested on a Dell XPS 13 DX13260 with its 360×360, 15 fps IR camera. Other hardware has not been physically tested. The tested system achieved first-attempt unlocks of approximately **1–3.5 seconds** after normal-distance enrollment and optional movement tuning. These are observations, not a performance guarantee. They describe the earlier Enter-to-scan flow; automatic triggering has passed automated checks and loaded in the live shell, but still needs a physical lock/wake test.

## Install

Review the code, then run:

```bash
omarchy plugin add https://github.com/therealasclepius/omarchy-face-unlock --yes
~/.config/omarchy/plugins/io.github.therealasclepius.face-unlock/setup
```

`plugin add --yes` installs the files without enabling the plugin. Setup installs Facelock if missing, runs its camera/model/encryption wizard without changing PAM, enrolls your face, configures the dedicated face service, and enables this lock plugin. The shell restarts while you are unlocked. Existing lock plugins are replaced through Omarchy's plugin mechanism.

Sit at your **normal typing distance** during enrollment. Slowly turn left and right, keeping your face in view. Enrolling only while leaning close to the camera makes everyday positioning harder. The fast standard models and CPU inference worked well on the tested hardware.

Already have a configured Facelock backend? Reuse its camera, models, encryption, and enrollments:

```bash
~/.config/omarchy/plugins/io.github.therealasclepius.face-unlock/setup --existing
```

A new setup can pass `--camera /dev/video2` (use **your** actual IR device), or `--camera auto`. Camera selection is otherwise interactive. No enrollment data, keys, camera recordings, or machine-specific configuration is shipped in this repository.

## Optional: installs, admin prompts, and 1Password

After setting up and testing face screen unlock, run in a visible terminal:

```bash
cd ~/.config/omarchy/plugins/io.github.therealasclepius.face-unlock
./auth enable --sudo --polkit
```

Select either flag alone to enable just that integration:

| Option | What it authorizes |
| --- | --- |
| `--sudo` | Terminal commands using `sudo`, including package installation and updates. It applies to all sudo authentication, not just installs. Sudo's command permissions and authentication caching still apply. |
| `--polkit` | All graphical prompts using polkit, including admin actions and 1Password's system authentication. It is not restricted to a list of apps or actions. |

Unlike the screen lock, these PAM integrations **scan automatically when authentication is requested**, then fall back to the existing password flow if recognition fails or is unavailable. The password prompt may take a few seconds to appear. The Omarchy graphical dialog may still say “Enter password” while the face scan runs. Escape cancels a graphical request; Ctrl+C cancels a terminal request. Opening an authentication prompt while your face is visible can authorize its action: enable this only if that behavior is appropriate for your computer.

The installer accepts only the reviewed default Arch `sudo` and `polkit-1` PAM stacks. It refuses custom authentication stacks, including existing fingerprint/face rules, rather than inserting a shortcut ahead of unknown policies. It keeps the original account/session rules and password fallback. It writes overrides to `/etc/pam.d/` and leaves package files in `/usr/lib/pam.d/` intact. Global `system-auth`, login, SSH, disk decryption, and sudoers permissions are not changed.

If the shared backend already uses `abort_if_ssh = false` (the UWSM workaround below), the command requires an explicit acknowledgement:

```bash
./auth enable --sudo --polkit --allow-session-bypass
```

This retains the existing configuration; it does not turn the workaround on. **Remote callers may request scans and satisfy sudo/polkit authentication while your enrolled face is visible at the camera.** Leaving SSH's own PAM stack unchanged does not prevent a remote shell from invoking sudo. Face authentication is a convenience option, not proof that you intended a particular privileged action. Review [SECURITY.md](SECURITY.md) before enabling it for admin access or a password vault.

### 1Password

In the native 1Password Linux app, open **Settings → Security → Unlock using system authentication**. Lock the app and unlock it once with your account password to initialize this feature; subsequent unlocks can use face authentication through polkit. Your account password remains necessary after restarting the app/computer and whenever 1Password's password-confirmation policy requires it. The Snap/Flatpak versions do not support system authentication.

This uses [1Password's documented PAM/polkit integration](https://support.1password.com/system-authentication-linux-security/); the plugin never receives your vault password or vault contents. See [1Password setup instructions](https://support.1password.com/system-authentication-linux/) and [supported installation methods](https://support.1password.com/install-linux/). Website passwords and applications with their own authentication mechanisms are not automatically replaced.

An actual 1Password face unlock was manually confirmed on the tested Dell XPS 13, with a corresponding successful polkit face-authentication log entry. This is a test on that setup, not a guarantee for every installation.

### Verify and disable

Keep a terminal open while testing. Use harmless commands:

```bash
./auth status
sudo -k
sudo /usr/bin/true
pkexec /usr/bin/true
```

Confirm a face match in the Facelock journal; successful command execution alone could also mean a password or cached authorization was used. Then **cover the camera**, repeat with `sudo -k`, and verify password fallback for both commands. Finally test an actual 1Password lock/unlock. Configuration checks and automated installer tests do not prove those live interactions work on another machine.

Disable one or both without changing screen unlock:

```bash
./auth disable --sudo
./auth disable --polkit
# Or both:
./auth disable --all
```

The root-owned journal at `/var/lib/omarchy-face-unlock/auth-state.json` records each original override and its installed replacement. Disable restores an original override byte-for-byte, or removes a newly created override to expose the current vendor file. Later administrator edits are preserved and require manual review. After package updates, compare any enabled PAM overrides against the new vendor configuration. Removing the plugin files alone does not undo these integrations.

## Optional compatibility and movement settings

The default setup preserves Facelock's security settings. These flags are opt-in and affect the shared Facelock daemon, not just the QML UI:

| Flag | Change | Tradeoff |
| --- | --- | --- |
| `--uwsm-compat` | Sets `security.abort_if_ssh = false` | Disables the daemon's PID/logind local-session check. Same-account processes, including remote sessions, can request a scan. Face identity and liveness are still required. Does not enable SSH PAM. |
| `--natural-motion` | Sets `security.frame_variance_max_similarity = 0.995` instead of the default `0.985` | Allows subtler head movement and reduces false rejections, but is a less strict static-photo check. IR, identity matching, and the three-frame movement check remain enabled unless independently changed in the backend. |

On the tested UWSM desktop, the stock local-session check rejected requests with `NoSessionForPID` before opening the camera. After confirming that exact issue, use:

```bash
~/.config/omarchy/plugins/io.github.therealasclepius.face-unlock/setup --existing --uwsm-compat
```

If identity matching is good but movement checks repeatedly reject you, add `--natural-motion`. Neither workaround is silently enabled for everyone. Facelock's IR and movement checks are not a claim of certified Windows Hello/Face ID security or protection against every presentation attack.

## Improve enrollment and diagnose

```bash
cd ~/.config/omarchy/plugins/io.github.therealasclepius.face-unlock
./enroll 'Normal distance, different screen angle'
./doctor
journalctl -u facelock-daemon --since '5 minutes ago'
```

`enroll` adds a model and offers a recognition test; it retains existing faces. Reusing a label replaces that label according to Facelock's enrollment behavior. Recognition tests returning exit status zero may still report a non-match: read the result.

- **No scan starts / instant rejection:** inspect the daemon log for `NoSessionForPID`, missing models, or unavailable encryption. Do not assume another enrollment will fix an integration failure.
- **High similarity with `variance_blocked=true`:** recognition found your face but movement was insufficient. Try a slight head turn, then consider the documented motion option.
- **Works only close up:** add an enrollment at normal distance and another common screen angle. Keep the face in view of the low-resolution IR camera.
- **Changed stock QML after an Omarchy update:** this plugin contains a copy of the tested lock implementation. Review upstream fixes before using `setup --allow-unverified-omarchy`. This flag does not make an incompatible version safe.
- **Missing key after initial Facelock 0.2.1 setup:** setup invokes Facelock's own key-generation command only if the configured keyfile is absent. It never disables encryption to make enrollment work.

`doctor` is read-only and does not activate the camera or read your biometric database. Face data and key management belong to Facelock and remain local on your machine. Facelock downloads recognition models during setup.

## Remove / restore

While unlocked:

```bash
~/.config/omarchy/plugins/io.github.therealasclepius.face-unlock/remove
omarchy plugin remove io.github.therealasclepius.face-unlock
```

Removal first enables Omarchy's stock lock screen. It disables installer-owned optional sudo/polkit integrations, then removes the face PAM service **only if this installer created it and its contents have not subsequently changed**. A pre-existing compatible face service is reused and retained. Optional settings applied by this installer are restored only while they still match the applied values; later user changes are preserved. State and the original config backup live under root-owned `/var/lib/omarchy-face-unlock/`.

Facelock, camera/model configuration, its enabled daemon, encryption keys, and enrolled faces are retained because another application or user may use them. To remove the backend too, follow Facelock's package removal and data-purge documentation. Removing plugin files alone does not undo system configuration; run `remove` first.

Emergency return to the stock plugin, while unlocked:

```bash
omarchy plugin enable omarchy.lock
omarchy restart shell
```

## Development

```bash
python3 -m unittest discover -s tests -v
node tests/face-flow.cjs
bash -n setup remove enroll doctor auth scripts/common.sh
omarchy plugin validate .
/usr/lib/qt6/bin/qmlformat Service.qml >/dev/null
/usr/lib/qt6/bin/qmlformat LockView.qml >/dev/null
```

See [SECURITY.md](SECURITY.md) for boundaries and [CHANGELOG.md](CHANGELOG.md) for releases.

## Credits and license

The lock-screen implementation is derived from [Omarchy](https://github.com/omacom/omarchy), copyright David Heinemeier Hansson, under the MIT license. Face integration, setup scripts, and tests are copyright 2026 Kosta Hantzis. See [LICENSE](LICENSE).

Facelock is an independently installed project with its own licenses. This plugin is a community project, not an official Omarchy or Facelock release.
