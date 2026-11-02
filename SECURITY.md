# Security Policy

## Supported versions

| Platform | Supported |
|---|---|
| Windows | 1.0.4 (latest) |
| Android | 1.0.3 (latest) |

Older releases are not maintained. Please upgrade before reporting an issue that may already be fixed.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private vulnerability reporting:

<https://github.com/hutao48/genshinimpact-py.found/security/advisories/new>

Include the affected version, platform, reproduction steps, and impact. You can expect an initial response within a few days. Please give us reasonable time to publish a fix before disclosing the issue.

## Scope and design

- **Audio stays local.** The app has no telemetry, accounts or cloud processing. The only network request is the optional GitHub Releases update check.
- **Update check is read-only.** It queries `https://api.github.com/repos/hutao48/genshinimpact-py.found/releases/latest` over HTTPS, uses a 12 s timeout and a 512 KB response cap, rejects redirects, and only opens a validated `https://github.com/hutao48/genshinimpact-py.found/releases/...` page. It never downloads or executes files.
- **Settings are local.** `%LOCALAPPDATA%\GenshinInstrumentDetector\settings.ini` is written atomically; no registry keys are created.
- **Android permissions** are limited to microphone access (`RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS`). `allowBackup` and cleartext traffic are disabled.

## Known release-signing limitations

- Windows executables are currently **not Authenticode-signed**. Verify the SHA-256 values published in `SHA256SUMS.txt` from the GitHub Release before running a downloaded file.
- Android release APKs are currently signed with the build environment's debug key unless repository signing secrets are configured. Each build can have a different signature; uninstall the previous version before upgrading. Do not treat the APK signature as a stable publisher identity.

These are packaging/provenance limitations, not remote-code-execution vulnerabilities. Reports that rely on a compromised GitHub account, a compromised build runner, or a locally modified executable are generally out of scope.

## Dependency and code checks

Release builds use pinned Python packaging dependencies (`packaging/requirements-build.txt`); the repository's dependency pins were checked against OSV/pip-audit with no known advisories at the time of the 1.0.4 release. Static review covers the Python, Kotlin and GitHub Actions code; the CI workflow pins third-party actions to commit SHAs and verifies that a release tag matches `app_version.py`.
