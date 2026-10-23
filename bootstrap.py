"""Fetch the latest shared Tahoe release and select Golden Gate defaults."""

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
ENTRY_POINTS = {"install", "uninstall", "installer", "legacy-install",
                "legacy-uninstall", "test", "vm"}
# Entry points that fast-forward this checkout before running.
UPDATE_ENTRY_POINTS = {"install", "installer"}
TAHOE_REPOSITORY = "lestercorderomurillo/macos-tahoe-liquid-kde"
GOLDEN_GATE_REPOSITORY = "lestercorderomurillo/macos-golden-gate-liquid-kde"
RELEASES_URL = f"https://github.com/{GOLDEN_GATE_REPOSITORY}/releases/latest"


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
    return sorted(set(filter(None, result.stdout.decode().split("\0"))))


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


def prepare() -> Path:
    # Install the latest Tahoe release; the audited pin is the fallback when
    # GitHub's API is unreachable or updates are disabled.
    pin = json.loads((ROOT / "upstream.json").read_text())
    defaults = json.loads((ROOT / "defaults.json").read_text())
    local = os.environ.get("GOLDEN_GATE_TAHOE_SOURCE")
    if not local and os.environ.get("MAC_TAHOE_NO_UPDATE_CHECK", "").lower() != "true":
        pin = latest_tahoe() or pin
    digest = hashlib.sha256((ROOT / "bootstrap.py").read_bytes())
    digest.update(json.dumps([pin, defaults], sort_keys=True).encode())
    source = Path(local).resolve() if local else None
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
        if (target / ".golden-gate-ready").is_file():
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
                (pin["commit"] or "local-development") + "\n")
            checkout.rename(target)
    return target


def _git(*args: str) -> subprocess.CompletedProcess | None:
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
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                              timeout=120, env=env, preexec_fn=drop, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _clean_checkout() -> bool:
    if not (ROOT / ".git").exists():
        return False
    top = _git("rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0 or Path(top.stdout.strip()).resolve() != ROOT:
        return False
    status = _git("status", "--porcelain")
    return status is not None and status.returncode == 0 and not status.stdout.strip()


def update_wrapper(entry: str, args: list[str]) -> None:
    """Fast-forward a clean checkout to the newest Golden Gate release and
    restart the same entry point. Any other case continues with this wrapper."""
    if (entry not in UPDATE_ENTRY_POINTS or args == ["--prepare"]
            or os.environ.get("GOLDEN_GATE_UPDATED") == "1"
            or os.environ.get("MAC_TAHOE_NO_UPDATE_CHECK", "").lower() == "true"):
        return
    try:
        current = (ROOT / "VERSION").read_text()
    except OSError:
        return
    latest = latest_release(GOLDEN_GATE_REPOSITORY)
    if not latest or _version(latest) <= _version(current):
        return
    manual = f"Golden Gate {latest} is available: git pull, or download it from {RELEASES_URL}"
    if not _clean_checkout():
        print(manual, flush=True)
        return
    print(f"Updating Golden Gate to {latest}…", flush=True)
    pull = _git("pull", "--ff-only")
    if pull is None or pull.returncode != 0:
        print(manual, flush=True)
        return
    os.environ["GOLDEN_GATE_UPDATED"] = "1"
    try:
        os.execv(sys.executable, [sys.executable, str(ROOT / entry), *args])
    except OSError:
        os.environ.pop("GOLDEN_GATE_UPDATED", None)


def main(entry: str = "installer", args: list[str] | None = None) -> int:
    if entry not in ENTRY_POINTS:
        raise ValueError("Unknown entry point")
    args = sys.argv[1:] if args is None else args
    update_wrapper(entry, args)
    original_uid, original_gid = os.geteuid(), os.getegid()
    try:
        # sudo entry points retain their root hop for Tahoe's own privilege
        # handling; downloads and extraction belong to the invoking user.
        if original_uid == 0 and os.environ.get("SUDO_UID"):
            os.setegid(int(os.environ["SUDO_GID"]))
            os.seteuid(int(os.environ["SUDO_UID"]))
        source = prepare()
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f"Golden Gate: {exc}", file=sys.stderr)
        return 1
    finally:
        if os.geteuid() != original_uid:
            os.seteuid(original_uid)
            os.setegid(original_gid)
    # The prepared source is not a git checkout; this wrapper already updated
    # itself and selected the latest Tahoe release.
    os.environ["MAC_TAHOE_NO_UPDATE_CHECK"] = "true"
    if args == ["--prepare"]:
        print(source)
        return 0
    os.chdir(source)
    os.execv(sys.executable, [sys.executable, str(source / entry), *args])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
