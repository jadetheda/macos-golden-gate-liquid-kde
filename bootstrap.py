"""Use local Tahoe sources when available, otherwise fetch a published release."""

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import pwd
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
ENTRY_POINTS = {"install", "uninstall", "installer", "test", "vm"}
# Entry points that fast-forward this checkout before running.
UPDATE_ENTRY_POINTS = {"install", "installer"}
TAHOE_REPOSITORY = "lestercorderomurillo/macos-tahoe-liquid-kde"
GOLDEN_GATE_REPOSITORY = "lestercorderomurillo/macos-golden-gate-liquid-kde"
RELEASES_URL = f"https://github.com/{GOLDEN_GATE_REPOSITORY}/releases/latest"


def active_prepared(cache: Path) -> set[Path] | None:
    """Older wrappers have no lease; their entry points still run in the source."""
    active = set()
    try:
        processes = list(Path("/proc").iterdir())
    except OSError:
        return None  # Cannot establish whether legacy snapshots are in use.
    for process in processes:
        if not process.name.isdecimal():
            continue
        try:
            relative = Path(os.readlink(process / "cwd")).relative_to(cache)
        except (OSError, ValueError):
            continue
        if relative.parts:
            active.add(cache / relative.parts[0])
    return active


def prune_prepared(cache: Path, current: Path) -> None:
    """Retire only wrapper snapshots, after their replacement is ready.

    A running entry point holds a shared lock on its ready marker. Never
    unlink a locked snapshot: the wizard and its backend still import it.
    """
    active = active_prepared(cache)
    for previous in cache.iterdir():
        # The caller owns .prepare.lock; no extraction can still be using
        # these TemporaryDirectory names left behind by an interrupted run.
        if (not previous.is_symlink() and previous.is_dir()
                and re.fullmatch(r"\.prepare-[a-z0-9_]{8}", previous.name)):
            try:
                shutil.rmtree(previous)
            except OSError as exc:
                print(f"Golden Gate: could not remove interrupted download {previous}: {exc}", file=sys.stderr)
            continue
        if (active is None or previous in active
                or previous == current or previous.is_symlink()
                or not previous.is_dir()
                or not re.fullmatch(r"[0-9a-f]{20}", previous.name)):
            continue
        marker = previous / ".golden-gate-ready"
        try:
            fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as lease:
                if not re.fullmatch(r"(?:local-development|[0-9a-f]{40})\n", lease.read()):
                    continue
                try:
                    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                shutil.rmtree(previous)
        except FileNotFoundError:
            continue
        except OSError as exc:
            print(f"Golden Gate: could not remove old cache {previous}: {exc}", file=sys.stderr)


def lease_prepared(target: Path) -> int:
    """Keep the snapshot alive across exec until the entry point exits."""
    fd = os.open(target / ".golden-gate-ready", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        os.set_inheritable(fd, True)
    except BaseException:
        os.close(fd)
        raise
    return fd


def extract_archive(archive: Path, destination: Path) -> Path:
    """Extract regular files first, then contained relative symbolic links."""
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        roots = set()
        seen = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("Unsafe archive path")
            if path in seen:
                raise ValueError("Duplicate archive path")
            seen.add(path)
            roots.add(path.parts[0])
            if member.issym():
                target = PurePosixPath(posixpath.normpath(str(path.parent / member.linkname)))
                if (PurePosixPath(member.linkname).is_absolute()
                        or not target.parts or target.parts[0] != path.parts[0]
                        or ".." in target.parts):
                    raise ValueError("Archive link escapes the source tree")
            elif not (member.isfile() or member.isdir()):
                raise ValueError("Unsupported archive member")
        if len(roots) != 1:
            raise ValueError("Expected one archive root")
        for member in members:
            path = destination / member.name
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, path.open("xb") as output:
                    shutil.copyfileobj(source, output)
                path.chmod(0o755 if member.mode & 0o111 else 0o644)
        for member in members:
            if member.issym():
                path = destination / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(member.linkname)
    return destination / roots.pop()


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def _github(path: str, accept: str = "application/vnd.github+json") -> bytes | None:
    request = urllib.request.Request(f"https://api.github.com/repos/{path}",
                                     headers={"Accept": accept, "User-Agent": "GoldenGate-KDE"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.read()
    except (OSError, ValueError):
        return None


def latest_release(repository: str) -> str | None:
    """The newest published release tag, or None when GitHub can't answer."""
    data = _github(f"{repository}/releases/latest")
    try:
        tag = json.loads(data)["tag_name"] if data else None
    except (ValueError, KeyError, TypeError):
        return None
    return tag if isinstance(tag, str) and re.fullmatch(r"v\d+\.\d+\.\d+", tag) else None


def latest_tahoe() -> dict | None:
    """The newest published Tahoe release and its commit."""
    tag = latest_release(TAHOE_REPOSITORY)
    sha = _github(f"{TAHOE_REPOSITORY}/commits/{tag}", "application/vnd.github.sha") if tag else None
    commit = sha.decode(errors="replace").strip() if sha else ""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        return None
    return {"repository": TAHOE_REPOSITORY, "commit": commit, "version": tag[1:]}


def download(pin: dict, destination: Path) -> None:
    commit = pin["commit"]
    if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Publish and pin Tahoe's edition support first, or set "
                         "GOLDEN_GATE_TAHOE_SOURCE to a local Tahoe checkout")
    url = ("https://codeload.github.com/lestercorderomurillo/"
           f"macos-tahoe-liquid-kde/tar.gz/{commit}")
    print("Downloading shared Tahoe implementation…", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "GoldenGate-KDE"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    # A release is checked against its VERSION after extraction; the
    # offline fallback pin carries its own archive digest.
    if "version" not in pin and digest.hexdigest() != pin.get("sha256"):
        raise ValueError("Tahoe archive checksum mismatch; refusing to run it")


def local_files(source: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(source), "ls-files", "--cached", "--others",
         "--exclude-standard", "-z"], check=True, capture_output=True)
    # ls-files includes tracked deletions in an in-progress rewrite.
    return sorted(name for name in set(result.stdout.decode().split("\0"))
                  if name and ((source / name).is_file() or (source / name).is_symlink()))


def local_source() -> Path | None:
    """An explicit checkout wins, then the sibling repository; never modify it."""
    explicit = os.environ.get("GOLDEN_GATE_TAHOE_SOURCE")
    source = (Path(explicit).expanduser() if explicit else
              ROOT.parent / "macos-tahoe-liquid-kde").resolve()
    required = ("VERSION", "installer", "src/installer/installer_ui.py",
                "src/scripts/defaults.json", "src/scripts/launcher_defaults.py",
                "src/offline/wallpapers/MacGoldenGate/metadata.json")
    if all((source / name).is_file() for name in required):
        return source
    if explicit:
        raise ValueError(f"Incomplete local Tahoe source: {source}")
    if (source / ".git").exists():
        status = _git("status", "--porcelain", "--untracked-files=all", root=source)
        if status is not None and status.returncode == 0 and status.stdout.strip():
            raise ValueError(f"Local Tahoe source has unfinished changes and missing required files: "
                             f"{source}. Restore the missing files to test this checkout.")
    return None


def _single_state_svg(sheet_svg: str, state: str) -> str:
    match = re.search(
        rf'(<g id="{re.escape(state)}-center">\s*'
        r'<rect x="0" y=")\d+(" width="16" height="16"[^/>]*/>\s*'
        r'<g transform="translate\(8,)\d+(\)">.*?</g>\s*</g>)',
        sheet_svg,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"Missing state {state} in SVG sheet")
    group = f"{match.group(1)}0{match.group(2)}8{match.group(3)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">\n'
        f"{group}\n</svg>\n"
    )


def _patch_gtk_group_hover(gtk_root: Path) -> None:
    if not gtk_root.is_dir():
        return
    for css in gtk_root.rglob("*.css"):
        if css.is_symlink():
            continue
        text = css.read_text(encoding="utf-8")
        orig = text
        if "headerbar windowcontrols:hover button.close" not in text:
            for btn in ("close", "maximize", "minimize"):
                text = text.replace(
                    f"headerbar windowcontrols button.{btn}:backdrop:hover {{",
                    f"headerbar windowcontrols:hover button.{btn}:backdrop, headerbar windowcontrols button.{btn}:backdrop:hover {{",
                )
                text = text.replace(
                    f"headerbar windowcontrols button.{btn}:hover {{",
                    f"headerbar windowcontrols:hover button.{btn}, headerbar windowcontrols button.{btn}:hover {{",
                )
            text = text.replace(
                ".fullscreen headerbar windowcontrols button.maximize:backdrop:hover, .maximized headerbar windowcontrols button.maximize:backdrop:hover {",
                ".fullscreen headerbar windowcontrols:hover button.maximize:backdrop, .maximized headerbar windowcontrols:hover button.maximize:backdrop, .fullscreen headerbar windowcontrols button.maximize:backdrop:hover, .maximized headerbar windowcontrols button.maximize:backdrop:hover {",
            )
            text = text.replace(
                ".fullscreen headerbar windowcontrols button.maximize:hover, .maximized headerbar windowcontrols button.maximize:hover {",
                ".fullscreen headerbar windowcontrols:hover button.maximize, .maximized headerbar windowcontrols:hover button.maximize, .fullscreen headerbar windowcontrols button.maximize:hover, .maximized headerbar windowcontrols button.maximize:hover {",
            )
        if "headerbar box:hover > button.titlebutton.close" not in text:
            for btn in ("close", "maximize", "minimize"):
                text = text.replace(
                    f"headerbar button.titlebutton.{btn}:backdrop:hover {{",
                    f"headerbar box:hover > button.titlebutton.{btn}:backdrop, headerbar button.titlebutton.{btn}:backdrop:hover {{",
                )
                text = text.replace(
                    f"headerbar button.titlebutton.{btn}:hover {{",
                    f"headerbar box:hover > button.titlebutton.{btn}, headerbar button.titlebutton.{btn}:hover {{",
                )
            text = text.replace(
                ".fullscreen headerbar button.titlebutton.maximize:backdrop:hover, .maximized headerbar button.titlebutton.maximize:backdrop:hover {",
                ".fullscreen headerbar box:hover > button.titlebutton.maximize:backdrop, .maximized headerbar box:hover > button.titlebutton.maximize:backdrop, .fullscreen headerbar button.titlebutton.maximize:backdrop:hover, .maximized headerbar button.titlebutton.maximize:backdrop:hover {",
            )
            text = text.replace(
                ".fullscreen headerbar button.titlebutton.maximize:hover, .maximized headerbar button.titlebutton.maximize:hover {",
                ".fullscreen headerbar box:hover > button.titlebutton.maximize, .maximized headerbar box:hover > button.titlebutton.maximize, .fullscreen headerbar button.titlebutton.maximize:hover, .maximized headerbar button.titlebutton.maximize:hover {",
            )
        if text != orig:
            css.write_text(text, encoding="utf-8")


def _patch_firefox_controls(firefox_root: Path, aurorae_root: Path) -> None:
    mac_root = firefox_root / "MacTahoeLiquidKde/MacTahoe"
    if not mac_root.is_dir():
        return
    parts_dir = mac_root / "parts"
    if parts_dir.is_dir():
        for css in parts_dir.glob("titlebutton-*.css"):
            text = css.read_text(encoding="utf-8")
            if ".titlebar-buttonbox:hover" in text:
                continue
            for btn in ("close", "max", "min", "restore"):
                text = text.replace(
                    f"#nav-bar .titlebar-{btn}:hover,\n#titlebar .titlebar-{btn}:hover,",
                    f"#nav-bar .titlebar-buttonbox:hover .titlebar-{btn},\n#titlebar .titlebar-buttonbox:hover .titlebar-{btn},\n#nav-bar .titlebar-{btn}:hover,\n#titlebar .titlebar-{btn}:hover,",
                )
                text = text.replace(
                    f"#nav-bar:-moz-window-inactive .titlebar-{btn}:hover,\n#titlebar:-moz-window-inactive .titlebar-{btn}:hover,",
                    f"#nav-bar:-moz-window-inactive .titlebar-buttonbox:hover .titlebar-{btn},\n#titlebar:-moz-window-inactive .titlebar-buttonbox:hover .titlebar-{btn},\n#nav-bar:-moz-window-inactive .titlebar-{btn}:hover,\n#titlebar:-moz-window-inactive .titlebar-{btn}:hover,",
                )
            text = text.replace(
                ':root[sizemode="maximized"] #nav-bar .titlebar-max:hover,\n:root[sizemode="maximized"] #titlebar .titlebar-max:hover,',
                ':root[sizemode="maximized"] #nav-bar .titlebar-buttonbox:hover .titlebar-max,\n:root[sizemode="maximized"] #titlebar .titlebar-buttonbox:hover .titlebar-max,\n:root[sizemode="maximized"] #nav-bar .titlebar-max:hover,\n:root[sizemode="maximized"] #titlebar .titlebar-max:hover,',
            )
            text = text.replace(
                ':root[sizemode="maximized"] #nav-bar:-moz-window-inactive .titlebar-max:hover,\n:root[sizemode="maximized"] #titlebar:-moz-window-inactive .titlebar-max:hover,',
                ':root[sizemode="maximized"] #nav-bar:-moz-window-inactive .titlebar-buttonbox:hover .titlebar-max,\n:root[sizemode="maximized"] #titlebar:-moz-window-inactive .titlebar-buttonbox:hover .titlebar-max,\n:root[sizemode="maximized"] #nav-bar:-moz-window-inactive .titlebar-max:hover,\n:root[sizemode="maximized"] #titlebar:-moz-window-inactive .titlebar-max:hover,',
            )
            css.write_text(text, encoding="utf-8")

    tb_dir = mac_root / "titlebuttons"
    if not tb_dir.is_dir():
        return
    for mode, dark_sfx in (("Light", ""), ("Dark", "-dark")):
        gg_dir = aurorae_root / f"MacGoldenGateLiquidKde-{mode}"
        if not gg_dir.is_dir():
            continue
        sheets = {
            btn: (gg_dir / f"{btn}.svg").read_text(encoding="utf-8")
            for btn in ("close", "minimize", "maximize", "restore")
            if (gg_dir / f"{btn}.svg").is_file()
        }
        if len(sheets) < 4:
            continue
        (tb_dir / f"titlebutton-backdrop{dark_sfx}.svg").write_text(
            _single_state_svg(sheets["close"], "inactive"), encoding="utf-8"
        )
        for btn in ("close", "minimize", "maximize"):
            (tb_dir / f"titlebutton-{btn}{dark_sfx}.svg").write_text(
                _single_state_svg(sheets[btn], "active"), encoding="utf-8"
            )
            for alt in ("", "-alt"):
                for sfx, st in (("-hover", "hover"), ("-active", "pressed"), ("-backdrop", "hover-inactive")):
                    target = tb_dir / f"titlebutton-{btn}{sfx}{dark_sfx}{alt}.svg"
                    if target.is_file() or not alt:
                        target.write_text(_single_state_svg(sheets[btn], st), encoding="utf-8")
        for alt in ("", "-alt"):
            for sfx, st in (("-hover", "hover"), ("-active", "pressed"), ("-backdrop", "hover-inactive")):
                target = tb_dir / f"titlebutton-unmaximize{sfx}{dark_sfx}{alt}.svg"
                if target.is_file() or not alt:
                    target.write_text(_single_state_svg(sheets["restore"], st), encoding="utf-8")


def apply_aurorae(source: Path) -> None:
    aurorae_root = ROOT / "src/offline/aurorae"
    if not aurorae_root.is_dir():
        return
    dest_aurorae = source / "src/offline/aurorae"
    dest_aurorae.mkdir(parents=True, exist_ok=True)
    has_window_controls = (source / "src/scripts/window_controls.py").is_file()
    for variant in ("Light", "Dark"):
        gg_dir = aurorae_root / f"MacGoldenGateLiquidKde-{variant}"
        if not gg_dir.is_dir():
            continue
        # 1. Copy complete standalone MacGoldenGateLiquidKde-{variant} theme
        target_gg = dest_aurorae / f"MacGoldenGateLiquidKde-{variant}"
        if target_gg.exists():
            shutil.rmtree(target_gg)
        shutil.copytree(gg_dir, target_gg)
        if (gg_dir / f"MacGoldenGateLiquidKde-{variant}rc").is_file():
            shutil.copy2(gg_dir / f"MacGoldenGateLiquidKde-{variant}rc", dest_aurorae / f"MacGoldenGateLiquidKde-{variant}rc")

        if has_window_controls:
            tahoe_rc = dest_aurorae / f"MacTahoeLiquidKde-{variant}rc"
            if tahoe_rc.is_file():
                rc_text = tahoe_rc.read_text(encoding="utf-8")
                if "ButtonGroupHover=" not in rc_text:
                    rc_text = rc_text.replace("[General]\n", "[General]\nButtonGroupHover=true\n", 1)
                    tahoe_rc.write_text(rc_text, encoding="utf-8")
        else:
            # 2. Legacy Tahoe (< 0.61.6): update built-in decoration and icons with Golden Gate SVGs & RC
            tahoe_dir = dest_aurorae / f"MacTahoeLiquidKde-{variant}"
            tahoe_dir.mkdir(parents=True, exist_ok=True)
            if (gg_dir / "decoration.svg").is_file():
                shutil.copy2(gg_dir / "decoration.svg", tahoe_dir / "decoration.svg")
            if (gg_dir / f"MacGoldenGateLiquidKde-{variant}rc").is_file():
                shutil.copy2(gg_dir / f"MacGoldenGateLiquidKde-{variant}rc", dest_aurorae / f"MacTahoeLiquidKde-{variant}rc")

            icons_dir = dest_aurorae / f"icons-{variant}"
            icons_dir.mkdir(parents=True, exist_ok=True)
            for icon in gg_dir.glob("*.svg"):
                if icon.name != "decoration.svg":
                    shutil.copy2(icon, icons_dir / icon.name)

    # 3. Enable MacGoldenGateLiquidKde and aurorae.v2 in window_decorations step
    step_file = source / "src/scripts/steps/window_decorations.py"
    if step_file.is_file():
        code = step_file.read_text()
        target_pat = '    for mode in VARIANTS:\n        name = f"MacTahoeLiquidKde-{mode}"'
        repl = '    for mode in VARIANTS:\n      for theme_prefix in ("MacGoldenGateLiquidKde", "MacTahoeLiquidKde"):\n        name = f"{theme_prefix}-{mode}"'
        if target_pat in code:
            code = code.replace(target_pat, repl)
            code = code.replace(
                'chosen = "MacTahoeLiquidKde-Light" if theme_mode() == "light" else "MacTahoeLiquidKde-Dark"',
                'chosen = "MacGoldenGateLiquidKde-Light" if theme_mode() == "light" else "MacGoldenGateLiquidKde-Dark"'
            )
        if '("library", "org.kde.kwin.aurorae")' in code:
            code = code.replace('("library", "org.kde.kwin.aurorae")', '("library", "org.kde.kwin.aurorae.v2")')
        step_file.write_text(code)

    # 4. Enable MacGoldenGateLiquidKde and aurorae.v2 in theme_switch
    theme_switch_file = source / "src/scripts/theme_switch.py"
    if theme_switch_file.is_file():
        ts_code = theme_switch_file.read_text()
        if "def decoration_theme" not in ts_code:
            ts_code = ts_code.replace(
                "__aurorae__svg__MacTahoeLiquidKde-Dark",
                "__aurorae__svg__MacGoldenGateLiquidKde-Dark"
            ).replace(
                "__aurorae__svg__MacTahoeLiquidKde-Light",
                "__aurorae__svg__MacGoldenGateLiquidKde-Light"
            )
        if '("library", "org.kde.kwin.aurorae")' in ts_code:
            ts_code = ts_code.replace('("library", "org.kde.kwin.aurorae")', '("library", "org.kde.kwin.aurorae.v2")')
        theme_switch_file.write_text(ts_code)

    # 5. Ensure window_controls.py (Tahoe >= 0.61.6) serves calibrated Golden Gate SVGs, calibrated RC margins, and ButtonGroupHover=true
    wc_file = source / "src/scripts/window_controls.py"
    if wc_file.is_file():
        wc_code = wc_file.read_text(encoding="utf-8")
        target_rc_write = '(destination / f"{name}rc").write_text(text)'
        repl_rc_write = '''gg_rc_src = source / name / f"{name}rc"
        if not gg_rc_src.is_file():
            gg_rc_src = source / f"{name}rc"
        if edition == "MacGoldenGate" and gg_rc_src.is_file():
            text = gg_rc_src.read_text(encoding="utf-8")
        if "ButtonGroupHover=" not in text:
            text = text.replace("[General]\\n", "[General]\\nButtonGroupHover=true\\n", 1)
        (destination / f"{name}rc").write_text(text, encoding="utf-8")'''
        if target_rc_write in wc_code:
            wc_code = wc_code.replace(target_rc_write, repl_rc_write)
        elif "ButtonGroupHover=true" not in wc_code:
            wc_code = wc_code.replace(
                '(destination / f"{name}rc").write_text(text)',
                'if "ButtonGroupHover=" not in text:\n            text = text.replace("[General]\\n", "[General]\\nButtonGroupHover=true\\n", 1)\n        (destination / f"{name}rc").write_text(text)',
            )
        override = '''

_GG_AURORAE_ROOT = Path(__file__).resolve().parents[1] / "offline/aurorae"


def button_svg(button: str, mode: str, state: str | None = None) -> str:
    """Serve calibrated Golden Gate SVG state sheet or single-state GTK asset."""
    if button not in BUTTONS or mode not in ("Light", "Dark") or (state is not None and state not in STATES):
        raise ValueError("Unknown window control variant")
    svg_path = _GG_AURORAE_ROOT / f"MacGoldenGateLiquidKde-{mode}" / f"{button}.svg"
    sheet = svg_path.read_text(encoding="utf-8")
    if state is None:
        return sheet
    match = re.search(
        rf'(<g id="{re.escape(state)}-center">\\s*'
        r'<rect x="0" y=")\\d+(" width="16" height="16"[^/>]*/>\\s*'
        r'<g transform="translate\\(8,)\\d+(\\)">.*?</g>\\s*</g>)',
        sheet,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"Missing state {state} in {svg_path}")
    group = f"{match.group(1)}0{match.group(2)}8{match.group(3)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">\\n'
        f"{group}\\n</svg>\\n"
    )
'''
        if "_GG_AURORAE_ROOT" not in wc_code:
            wc_code = wc_code + override
        wc_file.write_text(wc_code, encoding="utf-8")

    # 6. Enable group hover in GTK 3/4 and Firefox titlebuttons
    _patch_gtk_group_hover(source / "src/offline/gtk")
    _patch_firefox_controls(source / "src/offline/firefox", aurorae_root)



def apply_defaults(source: Path, defaults: dict) -> None:
    package = defaults.get("wallpaper")
    if package not in ("MacTahoe", "MacGoldenGate"):
        raise ValueError("Unsupported wallpaper default")
    config = source / "src/scripts/defaults.json"
    wallpaper = source / "src/offline/wallpapers" / package
    if not config.is_file() or not (wallpaper / "metadata.json").is_file():
        raise ValueError("Pinned Tahoe source lacks edition support or wallpapers")
    preset = defaults.get("launcher_preset", 1)
    if type(preset) is not int or preset not in (1, 2):
        raise ValueError("Unsupported launcher preset default")
    if "launcher_preset" in defaults and not (source / "src/scripts/launcher_defaults.py").is_file():
        raise ValueError("Pinned Tahoe source lacks launcher presets; publish and pin "
                         "the shared update, or set GOLDEN_GATE_TAHOE_SOURCE to "
                         "the updated local Tahoe checkout")
    config.write_text(json.dumps(defaults, indent=2) + "\n")
    apply_aurorae(source)


def prepare(*, lease: bool = False) -> Path:
    # Resolve local development sources before making any network request.
    pin = json.loads((ROOT / "upstream.json").read_text())
    defaults = json.loads((ROOT / "defaults.json").read_text())
    source = local_source()
    if source is None and os.environ.get("MAC_TAHOE_NO_UPDATE_CHECK", "").lower() != "true":
        pin = latest_tahoe() or pin
    digest = hashlib.sha256((ROOT / "bootstrap.py").read_bytes())
    digest.update(json.dumps([pin, defaults], sort_keys=True).encode())
    aurorae_dir = ROOT / "src/offline/aurorae"
    if aurorae_dir.is_dir():
        for path in sorted(aurorae_dir.rglob("*")):
            if path.is_file():
                digest.update(str(path.relative_to(ROOT)).encode())
                digest.update(path.read_bytes())
    files = local_files(source) if source else []
    for name in files:
        path = source / name
        digest.update(name.encode())
        digest.update(str(path.lstat().st_mode).encode())
        digest.update(os.readlink(path).encode() if path.is_symlink() else path.read_bytes())
    cache = ROOT / "build"
    cache.mkdir(exist_ok=True)
    target = cache / digest.hexdigest()[:20]
    with (cache / ".prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.is_symlink():
            raise ValueError("Prepared source must not be a symbolic link")
        if (target / ".golden-gate-ready").is_symlink():
            raise ValueError("Prepared source marker must not be a symbolic link")
        if (target / ".golden-gate-ready").is_file():
            if lease:
                lease_prepared(target)
            prune_prepared(cache, target)
            return target
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=cache) as temporary:
            staging = Path(temporary)
            if source:
                checkout = staging / "source"
                for name in files:
                    destination = checkout / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / name, destination, follow_symlinks=False)
            else:
                archive = staging / "tahoe.tar.gz"
                download(pin, archive)
                checkout = extract_archive(archive, staging / "unpacked")
                if "version" in pin and (checkout / "VERSION").read_text().strip() != pin["version"]:
                    raise ValueError("Tahoe release archive does not match its version")
            apply_defaults(checkout, defaults)
            (checkout / ".golden-gate-ready").write_text(
                ("local-development" if source else pin["commit"]) + "\n")
            checkout.rename(target)
        if lease:
            lease_prepared(target)
        prune_prepared(cache, target)
    return target


def _git(*args: str, root: Path | None = None) -> subprocess.CompletedProcess | None:
    """Run git in this checkout as the invoking user; pulling as root would
    leave root-owned objects."""
    env = dict(os.environ)
    drop = None
    if os.geteuid() == 0 and os.environ.get("SUDO_UID") and os.environ.get("SUDO_GID"):
        uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
        user = pwd.getpwuid(uid)
        env["HOME"] = user.pw_dir

        def drop():
            os.initgroups(user.pw_name, gid)
            os.setresgid(gid, gid, gid)
            os.setresuid(uid, uid, uid)
    try:
        return subprocess.run(["git", "-c", "maintenance.auto=false", "-c", "gc.auto=0",
                               "-C", str(root or ROOT), *args], capture_output=True, text=True,
                              timeout=120, env=env, preexec_fn=drop, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _clean_checkout(root: Path | None = None) -> bool:
    root = root or ROOT
    if not (root / ".git").exists():
        return False
    git = _git if root == ROOT else lambda *args: _git(*args, root=root)
    top = git("rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
        return False
    status = git("status", "--porcelain", "--untracked-files=all")
    return status is not None and status.returncode == 0 and not status.stdout.strip()


def _update_checkout(root: Path, repository: str, label: str) -> bool:
    """Only a newer published VERSION and a clean fast-forward may change files."""
    try:
        current = (root / "VERSION").read_text().strip()
    except OSError:
        return False
    if not re.fullmatch(r"\d+\.\d+\.\d+", current):
        return False
    latest = latest_release(repository)
    try:
        hints = json.loads(os.environ.get('MAC_TAHOE_RELEASE_HINTS', '{}'))
    except ValueError:
        hints = {}
    hints[repository] = latest.removeprefix('v') if latest else None
    os.environ['MAC_TAHOE_RELEASE_HINTS'] = json.dumps(hints)
    if not latest or _version(latest) <= _version(current):
        return False
    available = f"{label} {latest} is available (local v{current})."
    release_url = f"https://github.com/{repository}/releases/tag/{latest}"
    if not _clean_checkout(root):
        print(f"{available} Keeping local source: changes present or not a clean git checkout. "
              f"{release_url}", flush=True)
        return False

    git = _git if root == ROOT else lambda *args: _git(*args, root=root)

    def git_ok(*args):
        result = git(*args)
        return result if result is not None and result.returncode == 0 else None

    partial = git_ok('config', '--get', 'remote.origin.partialclonefilter')
    filtering = ['--filter=blob:none'] if partial is not None and partial.stdout.strip() == 'blob:none' else []
    fetched = git_ok("fetch", "--no-tags", *filtering, f"https://github.com/{repository}.git",
                     "refs/tags/" + latest)
    target = git_ok("rev-parse", "FETCH_HEAD^{commit}") if fetched is not None else None
    commit = target.stdout.strip() if target is not None else ""
    version = git_ok("show", commit + ":VERSION") if re.fullmatch(r"[0-9a-f]{40}", commit) else None
    if version is None or version.stdout.strip() != latest.removeprefix("v"):
        print(f"{available} Could not verify the published update; keeping local source. "
              f"{release_url}", flush=True)
        return False
    if git_ok("merge-base", "--is-ancestor", "HEAD", commit) is None:
        print(f"{available} Keeping local commits: the release is not a fast-forward. "
              f"{release_url}", flush=True)
        return False
    if not _clean_checkout(root) or git_ok("merge", "--ff-only", "--no-overwrite-ignore", commit) is None:
        print(f"{available} Could not safely update; keeping local source. "
              f"{release_url}", flush=True)
        return False
    print(f"Updated {label}: v{current} → {latest}", flush=True)
    return True


def _updates_enabled(entry: str, args: list[str]) -> bool:
    return (entry in UPDATE_ENTRY_POINTS
            and not any(arg in args for arg in
                        ("--prepare", "--check-update", "--free-space", "--help", "-h", "--uninstall", "--supervise"))
            and not os.environ.get("GOLDEN_GATE_TAHOE_SOURCE")
            and os.environ.get("MAC_TAHOE_NO_UPDATE_CHECK", "").lower() != "true")


def update_wrapper(entry: str, args: list[str]) -> None:
    """Update the wrapper independently of an automatically discovered sibling."""
    if not _updates_enabled(entry, args) or os.environ.get("GOLDEN_GATE_UPDATED") == "1":
        return
    if not _update_checkout(ROOT, GOLDEN_GATE_REPOSITORY, "Golden Gate"):
        return
    os.environ["GOLDEN_GATE_UPDATED"] = "1"
    try:
        os.execv(sys.executable, [sys.executable, str(ROOT / entry), *args])
    except OSError:
        os.environ.pop("GOLDEN_GATE_UPDATED", None)


def update_local_source(entry: str, args: list[str]) -> bool:
    """An implicit sibling follows releases unless it contains local test work."""
    if not _updates_enabled(entry, args):
        return False
    source = local_source()
    if source is not None:
        return _update_checkout(source, TAHOE_REPOSITORY, "Tahoe")
    return False


def main(entry: str = "installer", args: list[str] | None = None) -> int:
    if entry not in ENTRY_POINTS:
        raise ValueError("Unknown entry point")
    args = sys.argv[1:] if args is None else args
    maintenance_requested = entry in UPDATE_ENTRY_POINTS and args == ["--free-space"]
    original_no_update = os.environ.get("MAC_TAHOE_NO_UPDATE_CHECK")
    original_uid, original_gid = os.geteuid(), os.getegid()
    try:
        if maintenance_requested:
            # Maintenance uses the local source or verified offline pin, never
            # queries or installs a newer release as a side effect.
            os.environ["MAC_TAHOE_NO_UPDATE_CHECK"] = "true"
        update_wrapper(entry, args)
        source_updated = update_local_source(entry, args)
        # sudo entry points retain their root hop for Tahoe's own privilege
        # handling; downloads and extraction belong to the invoking user.
        if original_uid == 0 and os.environ.get("SUDO_UID"):
            os.setegid(int(os.environ["SUDO_GID"]))
            os.seteuid(int(os.environ["SUDO_UID"]))
        source = prepare(lease=args != ["--prepare"])
        maintenance = source / "src/scripts/repository_maintenance.py"
        roots = [ROOT]
        sibling = local_source()
        if sibling is not None:
            roots.append(sibling)
        maintenance_args = [arg for root in roots for arg in ("--repository", str(root))]
        if _updates_enabled(entry, args) and maintenance.is_file():
            try:
                result = subprocess.run([sys.executable, str(maintenance), "--auto", *maintenance_args],
                                        check=False, timeout=660)
                if result.returncode:
                    print("Golden Gate: Git maintenance did not finish; continuing with the update.", file=sys.stderr)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"Golden Gate: Git maintenance did not finish: {exc}", file=sys.stderr)
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f"Golden Gate: {exc}", file=sys.stderr)
        return 1
    finally:
        if os.geteuid() != original_uid:
            os.seteuid(original_uid)
            os.setegid(original_gid)
    # Keep the selected local snapshot or release throughout this invocation.
    os.environ["MAC_TAHOE_NO_UPDATE_CHECK"] = "true"
    if args == ["--prepare"]:
        print(source)
        return 0
    if maintenance_requested:
        # Preparing the pinned source was offline. Restore the caller's policy
        # so explicit cleanup may verify public cache ownership without updating.
        if original_no_update is None:
            os.environ.pop('MAC_TAHOE_NO_UPDATE_CHECK', None)
        else:
            os.environ['MAC_TAHOE_NO_UPDATE_CHECK'] = original_no_update
        if not maintenance.is_file():
            print("Golden Gate: this Tahoe source does not support --free-space yet.", file=sys.stderr)
            return 1
        os.execv(sys.executable, [sys.executable, str(maintenance), *maintenance_args])
        return 0
    os.chdir(source)
    os.execv(sys.executable, [sys.executable, str(source / entry), *args])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
