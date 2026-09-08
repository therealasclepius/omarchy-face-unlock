# Face Unlock for Omarchy

Face unlock using an infrared camera and [Facelock](https://github.com/tyvsmith/facelock), with password authentication available while the camera scans.

- **Enter** on an empty password field starts a scan.
- **Escape** cancels it.
- Type your password at any time; a rejected scan does not unlock the screen.
- Face status appears below the password field, separate from password errors.
- Camera scanning is explicit: it does not start automatically on lock or wake.

This plugin replaces Omarchy's stock lock plugin through `clonedFrom`. It does **not** patch `/usr/share/omarchy/`. It adds a dedicated face PAM service and does not modify password, fingerprint, sudo, polkit, login, or SSH PAM services.

## Requirements and support

- Omarchy **4.0.2-1** with the Quickshell lock screen. Setup checks the stock QML against the tested copy and stops on differences. This is not a Hyprlock plugin.
- An IR camera supported by Facelock and Linux V4L2. An ordinary RGB webcam is not supported by the default security policy.
- Facelock **0.2.1** or a compatible newer version, available as AUR `facelock-bin`.
- Working password unlock, an interactive terminal, and sudo access for setup.

Physically tested on a Dell XPS 13 DX13260 with its 360×360, 15 fps IR camera. Other hardware has not been physically tested. The tested system achieved first-attempt unlocks of approximately **1–3.5 seconds** after normal-distance enrollment and optional movement tuning. These are observations, not a performance guarantee.

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

Removal first enables Omarchy's stock lock screen. It then removes the face PAM service **only if this installer created it and its contents have not subsequently changed**. A pre-existing compatible face service is reused and retained. Optional settings applied by this installer are restored only while they still match the applied values; later user changes are preserved. State and the original config backup live under root-owned `/var/lib/omarchy-face-unlock/`.

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
bash -n setup remove enroll doctor scripts/common.sh
omarchy plugin validate .
/usr/lib/qt6/bin/qmlformat Service.qml >/dev/null
/usr/lib/qt6/bin/qmlformat LockView.qml >/dev/null
```

See [SECURITY.md](SECURITY.md) for boundaries and [CHANGELOG.md](CHANGELOG.md) for releases.

## Credits and license

The lock-screen implementation is derived from [Omarchy](https://github.com/omacom/omarchy), copyright David Heinemeier Hansson, under the MIT license. Face integration, setup scripts, and tests are copyright 2026 Kosta Hantzis. See [LICENSE](LICENSE).

Facelock is an independently installed project with its own licenses. This plugin is a community project, not an official Omarchy or Facelock release.
