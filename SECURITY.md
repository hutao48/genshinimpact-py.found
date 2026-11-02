# Security Policy

## Supported versions

| Platform | Supported |
|---|---|
| Windows | 1.1.0 (latest) |
| Android | 1.1.0 (latest) |

Older releases are not maintained. Please upgrade before reporting an issue that may already be fixed.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private vulnerability reporting:

<https://github.com/hutao48/genshinimpact-py.found/security/advisories/new>

Include the affected version, platform, reproduction steps, and impact. You can expect an initial response within a few days. Please give us reasonable time to publish a fix before disclosing the issue.

## Scope and design

- **Audio stays local.** The app has no telemetry, accounts or cloud processing. The only network requests are the optional GitHub Releases update check and the update download when the user enables automatic updates or asks to install one.
- **Update check.** It queries `https://api.github.com/repos/hutao48/genshinimpact-py.found/releases/latest` over HTTPS, uses a 12 s timeout and a 512 KB response cap, and validates release URLs. With automatic updates off, it only opens a validated GitHub release page and never downloads or executes files.
- **Automatic updates (opt-in).** When enabled, the Windows app downloads the matching `win64-setup.exe` from that release over HTTPS, enforces a 200 MB limit, verifies the SHA-256 published in the GitHub asset metadata, checks the PE header, then starts the installer with fixed silent arguments. The Android app does the same for the APK and hands it to the system package installer; Android still asks the user to confirm installation.
- **Settings are local.** `%LOCALAPPDATA%\GenshinInstrumentDetector\settings.ini` is written atomically; no registry keys are created.
- **Android permissions** are microphone access (`RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS`), network access for update checks (`INTERNET`), and package installation (`REQUEST_INSTALL_PACKAGES`). APK downloads are shared through a non-exported `FileProvider`. `allowBackup` and cleartext traffic are disabled.

## Android signing

Starting with 1.1.0, release APKs are signed with a fixed release key supplied to CI through the `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD` repository Secrets. The workflow fails instead of producing a debug-signed release if the key is missing. Future 1.1.x/1.x releases use the same certificate and can be installed over the previous version. Versions 1.0.3 and earlier used per-build debug keys; upgrading from them to 1.1.0 requires uninstalling the old app once.

## Known release-signing limitations

- Windows executables are currently **not Authenticode-signed**. Verify the SHA-256 values published in `SHA256SUMS.txt` from the GitHub Release before running a downloaded file. The copy hosted directly on the project site has its own checksum file at `docs/downloads/SHA256SUMS.txt`.
- Android release APKs are signed with the fixed release key described above. Keep the signing key and its passwords backed up: losing them prevents future versions from upgrading over an installed copy.

These are packaging/provenance limitations, not remote-code-execution vulnerabilities. Reports that rely on a compromised GitHub account, a compromised build runner, or a locally modified executable are generally out of scope.

## Dependency and code checks

Release builds use pinned Python packaging dependencies (`packaging/requirements-build.txt`); the repository's dependency pins were checked against OSV/pip-audit with no known advisories at the time of the 1.1.0 release. Static review covers the Python, Kotlin and GitHub Actions code; the CI workflow pins third-party actions to commit SHAs and verifies that a release tag matches `app_version.py`.
