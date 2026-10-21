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
Both presets keep every category pill vertically aligned, including categories
created while scrolling. The shared Tahoe implementation centers pills inside
full-height ListView delegate cells; do not position the delegates themselves.

Preserve the README Credits section and existing local banner artwork.
Preserve existing copyright and component license notices. Follow `NOTICE`,
`LICENSING.md`, and `THIRD_PARTY_NOTICES.md`; keep GPL intact,
without copying, rebranding, or commercial-use bans or claims to third-party marks.
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
client fill in both modes so the upper gradient supplies the dark tint.
Only light native Qt menus use a 60% white translucent Kvantum menu fill to
keep dark system text readable. Preserve dark menus, Tahoe, and all non-menu
surfaces; apply this exception in both the installer and Nix staging.
Tahoe retains 55% white light fills and slightly clearer 48% black dark fills.
Golden Gate menus retain their black upper gradient in light and dark mode:
85% black at the top, fading to zero at 55% of the surface height;
the Dock is exempt from the gradient while retaining blur and refraction.
Launcher text uses a soft, low-opacity halo of the opposite luminance, without
a hard outline. Light-mode category pills have a translucent white backing
for readable dark labels. Keep this shared implementation in Tahoe.
In Golden Gate light mode, the Apps input uses full-opacity text and a
stronger diffuse halo. Category fills use 68% white when selected and 52%
otherwise. These changes follow the staged edition independently of the
selected launcher preset; preserve Tahoe and dark-mode styling.
There is no Reduced Transparency preference or generated opaque variant.

Published screenshots must include the first 12 hexadecimal characters of their
content SHA-256 in the filename (for example, `launcher_preset_1_light-abc123def456.png`).
Update README links and provenance together, remove replaced image files and
obsolete aliases, and preserve unrelated artwork. Apply this in both repositories
every time images are published; never overwrite a changed image at its old URL.

Main README desktop screenshots must show Files and About This Computer in
separate images in each appearance mode. Each frame must contain only its
featured application with that window focused; reject combined or unfocused
frames. Enforce this in capture and release validation. This requirement is
for the main README gallery, not distro qualification/OS screenshots.
