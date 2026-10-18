import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bootstrap


def archive_at(tmp_path, members):
    path = tmp_path / "source.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, kind, payload in members:
            member = tarfile.TarInfo(name)
            member.type = kind
            if kind == tarfile.REGTYPE:
                member.size = len(payload)
                member.mode = 0o755
                archive.addfile(member, io.BytesIO(payload))
            else:
                member.linkname = payload
                archive.addfile(member)
    return path


def test_extract_preserves_internal_links_and_executables(tmp_path):
    path = archive_at(tmp_path, [("repo/install", tarfile.REGTYPE, b"code"),
                                ("repo/link", tarfile.SYMTYPE, "install")])
    source = bootstrap.extract_archive(path, tmp_path / "out")
    assert (source / "link").read_bytes() == b"code"
    assert (source / "link").is_symlink()
    assert (source / "install").stat().st_mode & 0o111


@pytest.mark.parametrize("member", [
    ("../escape", tarfile.REGTYPE, b"bad"),
    ("/escape", tarfile.REGTYPE, b"bad"),
    ("repo/link", tarfile.SYMTYPE, "../../escape"),
    ("repo/link", tarfile.SYMTYPE, "/etc/passwd"),
    ("repo/link", tarfile.LNKTYPE, "repo/file"),
    ("repo/device", tarfile.CHRTYPE, ""),
])
def test_extract_rejects_unsafe_members(tmp_path, member):
    with pytest.raises(ValueError):
        bootstrap.extract_archive(archive_at(tmp_path, [member]), tmp_path / "out")
    assert not (tmp_path / "escape").exists()


def test_download_checks_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"archive"))
    pin = {"commit": "a" * 40, "sha256": "0" * 64}
    with pytest.raises(ValueError, match="checksum"):
        bootstrap.download(pin, tmp_path / "download")
    pin["sha256"] = hashlib.sha256(b"archive").hexdigest()
    bootstrap.download(pin, tmp_path / "download")


def test_unpublished_pin_fails_before_download(tmp_path, monkeypatch):
    def unexpected_network(*args, **kwargs):
        pytest.fail("An unpublished pin must not trigger a download")
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", unexpected_network)
    with pytest.raises(ValueError, match="Publish and pin"):
        bootstrap.download({"commit": None, "sha256": None}, tmp_path / "download")


def test_prepare_changes_only_defaults_and_reuses_verified_cache(tmp_path, monkeypatch):
    root = tmp_path / "wrapper"
    root.mkdir()
    (root / "bootstrap.py").write_text("recipe")
    (root / "defaults.json").write_text('{"wallpaper":"MacGoldenGate"}')
    (root / "upstream.json").write_text('{"commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
    members = [
        ("repo/src/scripts/defaults.json", tarfile.REGTYPE, b'{"wallpaper":"MacTahoe"}'),
        ("repo/src/offline/wallpapers/MacGoldenGate/metadata.json", tarfile.REGTYPE, b'{}'),
        ("repo/install", tarfile.REGTYPE, b"unchanged implementation"),
    ]
    archive = archive_at(tmp_path, members)
    calls = []
    def download(pin, destination):
        calls.append(pin)
        destination.write_bytes(archive.read_bytes())
    monkeypatch.setattr(bootstrap, "ROOT", root)
    monkeypatch.delenv("GOLDEN_GATE_TAHOE_SOURCE", raising=False)
    monkeypatch.setattr(bootstrap, "download", download)
    prepared = bootstrap.prepare()
    assert json.loads((prepared / "src/scripts/defaults.json").read_text()) == {"wallpaper":"MacGoldenGate"}
    assert (prepared / "install").read_bytes() == b"unchanged implementation"
    assert bootstrap.prepare() == prepared
    assert len(calls) == 1


def test_missing_upstream_support_is_not_silently_ignored(tmp_path):
    with pytest.raises(ValueError, match="lacks edition support"):
        bootstrap.apply_defaults(tmp_path, {"wallpaper":"MacGoldenGate"})


def test_launch_forwards_arguments_and_disables_independent_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "prepare", lambda: tmp_path)
    monkeypatch.setattr(bootstrap.os, "chdir", lambda path: None)
    calls = []
    monkeypatch.setattr(bootstrap.os, "execv", lambda executable, args: calls.append(args))
    monkeypatch.setenv("MAC_TAHOE_NO_UPDATE_CHECK", "false")
    assert bootstrap.main("install", ["--dark", "--reset-wallpapers"]) == 0
    assert calls == [[sys.executable, str(tmp_path / "install"), "--dark", "--reset-wallpapers"]]
    assert bootstrap.os.environ["MAC_TAHOE_NO_UPDATE_CHECK"] == "true"
