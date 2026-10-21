# Golden Gate

Golden Gate is a parameterized distribution of macos-tahoe-liquid-kde.
All implementation and wallpaper assets live in Tahoe. Keep this repository
limited to the downloader, its tests, `defaults.json`, the audited upstream
pin, release version, documentation, screenshots and the existing banner. Do not vendor Tahoe here.

Update `upstream.json` with both a published immutable commit and its archive
SHA-256. The selected commit must contain edition support and MacGoldenGate.
Run the wrapper tests and the shared Tahoe suite against the prepared source.
`GOLDEN_GATE_TAHOE_SOURCE` allows testing a local Tahoe checkout before publishing.

Publish matching `v<version>` releases in both repositories. Deliver completed
changes to both `dev` and `main` in both repositories, and verify both remote
branches include them before reporting completion. Release titles must
be exactly `v<version>`, with no subtitles, descriptions or other extra text.
This repository's
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

Every release must use a fresh complete bundle from Tahoe's
`./release-screenshots capture`, with the pinned VM and fixed capture profile.
Stage this edition's reviewed images with the Tahoe command's `stage
--edition golden-gate --destination <this-checkout>`. Do not reuse pictures
from an older version or fill rejected cases with old files. After pinning
the published Tahoe release and committing the images, run its tool with
`--repo <this-checkout> verify --tahoe-repo <tahoe-checkout>`.
Publish through `.github/workflows/release.yml`, which runs that gate against
the immutable Tahoe pin. Never bypass it with direct `gh release create`.
The capture implementation belongs only in Tahoe; do not vendor it here.

The shared installer must record a verified uninstall wallpaper reset as
project-applied state. Reinstallation replaces that unchanged background while
preserving a background selected afterward by the user. A Breeze/Next filename
alone is not proof of ownership; legacy misclassified states require an
explicit reset. Keep this implementation in Tahoe.

The shared Acrylic Glass KCM offers Tahoe and Golden Gate materials, both
with blur strength 10 and stable saved IDs 1 and 2. Retired Clear ID 0 falls
back to Tahoe without resetting saved optics when opening the KCM.
Installing or reinstalling Acrylic Glass selects the complete Golden Gate
material, replacing saved material selections and optical overrides while
preserving radius controls and window rules. Preset data and rendering
live only in Tahoe, including Plasma/Kvantum popup surfaces. Golden Gate stages a 1% white
client fill in both modes so the upper gradient supplies the dark tint;
Tahoe retains 55% white light fills and slightly clearer 48% black dark fills.
Golden Gate menus retain their black upper gradient in light and dark mode:
95% black at the top, fading to zero at 50% of the surface height;
the Dock is exempt from the gradient while retaining blur and refraction.
There is no Reduced Transparency preference or generated opaque variant.
