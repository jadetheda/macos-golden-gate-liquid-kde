# Golden Gate

Golden Gate is a parameterized distribution of macos-tahoe-liquid-kde.
All implementation and wallpaper assets live in Tahoe. Keep this repository
limited to the downloader, its tests, `defaults.json`, the audited upstream
pin, documentation and the existing banner. Do not vendor Tahoe here.

Update `upstream.json` with both a published immutable commit and its archive
SHA-256. The selected commit must contain edition support and MacGoldenGate.
Run the wrapper tests and the shared Tahoe suite against the prepared source.
`GOLDEN_GATE_TAHOE_SOURCE` allows testing a local Tahoe checkout before publishing.

Preserve the README Credits section and existing local banner artwork.
Never run the live installer as a test or change the user's desktop.
