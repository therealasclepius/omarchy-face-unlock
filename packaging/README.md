# System helper packaging and trust

The 0.4.0 helper is signed with this release identity:

- Identity: `Omarchy Face Unlock release signing (therealasclepius)`
- Full fingerprint: `56F44649A6A1D7ED0C600DE7673E5021B926A4E6`
- Public key: [release.asc](keys/release.asc)
- Signing key expires September 9, 2027.

Confirm this fingerprint through the maintainer's authenticated distribution
channel before trusting it. Its appearance in this checkout alone is not a trust
anchor. Signed artifacts are prepared for the 0.4.0 release; installation requires
obtaining the package and detached signature from that release.

## User installation and updates

1. Obtain the release signing key's **full fingerprint** through a trusted channel
   independent of the writable plugin checkout. Confirm who controls it. A key or
   checksum bundled with the same checkout does not authenticate that checkout.
2. Have an administrator import and trust that exact key in pacman's system
   keyring. Do not automatically trust a key just because a download provides it.
3. Have an administrator create `/etc/pacman-face-unlock.conf`, owned by
   root:root and writable only by root, with these contents:

   ```ini
   [options]
   Architecture = auto
   SigLevel = Required TrustedOnly
   LocalFileSigLevel = Required TrustedOnly
   RemoteFileSigLevel = Required TrustedOnly
   ```

   Use `sudoedit /etc/pacman-face-unlock.conf` to enter the reviewed policy.
   This separate config does not change normal pacman behavior. Never pass a
   configuration in the writable plugin directory to elevated pacman.
4. Download the versioned `.pkg.tar.zst` and matching `.pkg.tar.zst.sig` from
   the authenticated release, placing them next to each other. Install the exact
   package with `sudo /usr/bin/pacman --config /etc/pacman-face-unlock.conf -U PACKAGE.pkg.tar.zst`. Pacman must verify
   the package itself; a separate user-side `gpg --verify` is not a substitute.
   Missing, invalid or untrusted signatures must stop installation.
5. `/usr/bin/omarchy-face-unlock-helper --protocol` must print `1`. Then run
   the plugin's `setup` from your unlocked desktop.

Updates use the same signature-enforced package path. A plugin update never
copies or runs new helper code as root. Use a reviewed current version; a valid
signature identifies the signer but does not prove a package is the latest version.
Never use `SigLevel = Never`, `TrustAll`, `makepkg -si` in the plugin checkout,
or `sudo python3 helper/...` to get around a failed install.

The helper package installs only these files (plus package metadata):

- `/usr/bin/omarchy-face-unlock-helper` (root:root, 0755)
- `/usr/lib/omarchy-face-unlock/manage.py` (root:root, 0644)
- `/usr/lib/omarchy-face-unlock/auth_manage.py` (root:root, 0644)
- `/usr/share/licenses/omarchy-face-unlock-helper/LICENSE`

There are no package install/removal hooks or PAM files in the archive.
Existing 0.3.0 root-owned journals remain compatible. Install the helper before
upgrading the plugin. `remove` restores the stock locker and undoes owned system
changes; only afterwards remove the helper package with pacman if desired.

## Release builder

Build a reviewed release commit in a clean, trusted build environment, separate
from the installed plugin and other untrusted same-user processes. The local
recipe deliberately packages that checkout and does not fetch mutable sources.

```bash
python3 -m unittest discover -s tests -v
node tests/face-flow.cjs
cd packaging/arch
makepkg --cleanbuild
```

Inspect the package manifest and payload. Sign the **finished package bytes**
with the release key in a protected signing environment, using a detached binary
GPG signature named exactly like the package plus `.sig`. Keep private signing
material outside the repository and the installed desktop plugin account.
Do not sign arbitrary artifacts supplied by a pull request or writable checkout
without verifying their provenance and contents.

Publish the package, detached signature, source commit, version, and public key.
Publish the full fingerprint through the independent trust channel agreed with
users/maintainers. Test installation on a disposable Arch system with signatures
required: the valid package must install; an unsigned package, a modified package,
and a package signed by an untrusted key must all fail. Then test actual helper
setup/removal, face authentication and covered-camera password fallback there.
The unit tests do not establish package trust or replace this release test.

Signature policy reference: [pacman.conf(5)](https://man.archlinux.org/man/pacman.conf.5.en).

## Maintainer signing-key storage

The initial key was generated in the root-only directory
`/var/lib/omarchy-face-unlock-signing` on the maintainer's machine. The private key
has filesystem protection, without a separate passphrase. Signing requires root
authorization. Its revocation certificate is in that directory's
`openpgp-revocs.d/`; keep recovery material in a protected offline backup.
Neither the private key nor its revocation certificate belongs in Git or a release.
Only `packaging/keys/release.asc` is public.
