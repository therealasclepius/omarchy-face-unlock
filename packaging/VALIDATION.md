# 0.4.0 helper validation — September 9, 2026

Package: `omarchy-face-unlock-helper-0.4.0-1-any.pkg.tar.zst`

SHA-256: `8df8fc52bb0522af0c84f8ed683a2a3d62845ea66ed26468f3b3df69cf28891f`

Signing fingerprint: `56F44649A6A1D7ED0C600DE7673E5021B926A4E6`

## Verified

- 43 Python tests passed, including PAM backup/rollback, helper import isolation,
  rejection of writable or symlinked ancestors, and missing-helper refusal.
- JavaScript lock-flow tests and local Omarchy plugin validation passed.
- The package's three executable/module payloads match the reviewed source bytes.
- Pacman with `Required TrustedOnly` rejected the package before trusting the key.
- After trusting that exact key, the signed package installed into an isolated root.
  Dependency checks were skipped only for this otherwise empty test root.
- An unsigned copy was rejected with `package missing required signature`.
- A modified copy retaining the signature was rejected with `PGP signature` failure.
- The signed package installed on the maintainer's Arch/Omarchy system with normal
  dependency checks. Package verification reported 11 files, zero altered files.
- The installed helper reports protocol 1; all helper paths are root-owned with
  0755 directory/executable permissions and 0644 module permissions.
- Its real `lock configure` operation succeeded. Before/after hashes of Facelock's
  configuration, the dedicated face PAM service, sudo, and polkit PAM files match.
- Read-only helper status recognizes both existing optional authentication blocks.

## Limits

The lock-screen behavior and biometric backend are unchanged by this release;
the QML-reported version is updated to match the manifest. These
checks exercise the new privileged-code boundary and package trust. They are not
an independent security audit or new hardware/presentation-attack certification.
Covered-camera password fallback and physical lock/unlock remain user-observed
checks; do not infer them from successful package installation or configuration.
