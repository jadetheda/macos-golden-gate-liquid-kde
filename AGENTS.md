# Golden Gate

Golden Gate is a parameterized distribution of macos-tahoe-liquid-kde.
All implementation and wallpaper assets live in Tahoe. Keep this repository
limited to the downloader, its tests, `defaults.json`, the audited upstream
pin, release version, documentation, screenshots and the existing banner. Do not vendor Tahoe here.

Update `upstream.json` with both a published immutable commit and its archive
SHA-256. The selected commit must contain edition support and MacGoldenGate.
Run the wrapper tests and the shared Tahoe suite against the prepared source.
`GOLDEN_GATE_TAHOE_SOURCE` allows testing a local Tahoe checkout before publishing.

Publish matching `v<version>` releases in both repositories. This repository's
`VERSION` must equal the pinned Tahoe source's `VERSION`; `upstream.json` must
reference the commit tagged for that Tahoe release. Publish Tahoe first,
verify the archive checksum, then publish Golden Gate. Each README must show
the preset and wallpaper its edition installs by default.

`defaults.json` selects `launcher_preset: 2` alongside the Golden Gate wallpaper.
The pinned Tahoe source must include `launcher_defaults.py`. Both launcher
presets stay selectable from the options menu and General settings; do not
force the edition default over an explicit saved choice.

Preserve the README Credits section and existing local banner artwork.
Never run the live installer as a test or change the user's desktop.

Capture documentation screenshots only inside a disposable VM. Never switch
the host theme, move its windows, or inject host input for screenshots. Run
captures sequentially, verify labels and window identity, and review each image
before publishing it.

The shared Acrylic Glass KCM offers Clear, Tahoe and Golden Gate materials.
The edition initially selects Golden Gate; explicit saved material selections
and individual overrides must survive reinstalls. Preset data and rendering
live only in Tahoe, including transparent shared Plasma/Kvantum popup surfaces.
Golden Gate menus retain their black upper gradient in light and dark mode;
the Dock is exempt from the gradient while retaining blur and refraction.
There is no Reduced Transparency preference or generated opaque variant.
