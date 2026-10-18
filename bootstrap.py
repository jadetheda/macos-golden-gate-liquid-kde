"""Fetch the shared Tahoe implementation and select Golden Gate defaults."""

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
ENTRY_POINTS = {"install", "uninstall", "installer", "legacy-install",
                "legacy-uninstall", "test", "vm"}


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
    if digest.hexdigest() != pin["sha256"]:
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
    config.write_text(json.dumps(defaults, indent=2) + "\n")


def prepare() -> Path:
    pin = json.loads((ROOT / "upstream.json").read_text())
    defaults = json.loads((ROOT / "defaults.json").read_text())
    digest = hashlib.sha256((ROOT / "bootstrap.py").read_bytes())
    digest.update(json.dumps([pin, defaults], sort_keys=True).encode())
    local = os.environ.get("GOLDEN_GATE_TAHOE_SOURCE")
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
            apply_defaults(checkout, defaults)
            (checkout / ".golden-gate-ready").write_text(
                (pin["commit"] or "local-development") + "\n")
            checkout.rename(target)
    return target


def main(entry: str = "installer", args: list[str] | None = None) -> int:
    if entry not in ENTRY_POINTS:
        raise ValueError("Unknown entry point")
    args = sys.argv[1:] if args is None else args
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
    # Updates happen by moving this wrapper's audited pin, never by silently
    # replacing its prepared source with a different Tahoe release.
    os.environ["MAC_TAHOE_NO_UPDATE_CHECK"] = "true"
    if args == ["--prepare"]:
        print(source)
        return 0
    os.chdir(source)
    os.execv(sys.executable, [sys.executable, str(source / entry), *args])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
