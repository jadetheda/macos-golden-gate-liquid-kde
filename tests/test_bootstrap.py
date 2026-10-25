import hashlib
import io
import json
import subprocess
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
    monkeypatch.delenv("MAC_TAHOE_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(bootstrap, "latest_tahoe", lambda: None)  # GitHub unreachable
    monkeypatch.setattr(bootstrap, "download", download)
    prepared = bootstrap.prepare()
    assert json.loads((prepared / "src/scripts/defaults.json").read_text()) == {"wallpaper":"MacGoldenGate"}
    assert (prepared / "install").read_bytes() == b"unchanged implementation"
    assert bootstrap.prepare() == prepared
    assert len(calls) == 1


def test_missing_upstream_support_is_not_silently_ignored(tmp_path):
    with pytest.raises(ValueError, match="lacks edition support"):
        bootstrap.apply_defaults(tmp_path, {"wallpaper":"MacGoldenGate"})


@pytest.mark.parametrize("preset", [1, 2])
def test_launcher_preset_requires_shared_support_and_is_forwarded(tmp_path, preset):
    scripts = tmp_path / "src/scripts"
    scripts.mkdir(parents=True)
    config = scripts / "defaults.json"
    config.write_text('{"wallpaper":"MacTahoe","launcher_preset":1}')
    wallpaper = tmp_path / "src/offline/wallpapers/MacGoldenGate"
    wallpaper.mkdir(parents=True)
    (wallpaper / "metadata.json").write_text('{}')
    defaults = {"wallpaper": "MacGoldenGate", "launcher_preset": preset}
    with pytest.raises(ValueError, match="lacks launcher presets"):
        bootstrap.apply_defaults(tmp_path, defaults)
    assert json.loads(config.read_text())["wallpaper"] == "MacTahoe"
    (scripts / "launcher_defaults.py").write_text("# shared preset support\n")
    bootstrap.apply_defaults(tmp_path, defaults)
    assert json.loads(config.read_text()) == defaults


def test_golden_gate_defaults_to_second_launcher_preset():
    defaults = json.loads((bootstrap.ROOT / "defaults.json").read_text())
    assert defaults["launcher_preset"] == 2


def test_launch_forwards_arguments_and_disables_independent_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "prepare", lambda: tmp_path)
    monkeypatch.setattr(bootstrap, "update_wrapper", lambda entry, args: None)
    monkeypatch.setattr(bootstrap.os, "chdir", lambda path: None)
    calls = []
    monkeypatch.setattr(bootstrap.os, "execv", lambda executable, args: calls.append(args))
    monkeypatch.setenv("MAC_TAHOE_NO_UPDATE_CHECK", "false")
    assert bootstrap.main("install", ["--dark", "--reset-wallpapers"]) == 0
    assert calls == [[sys.executable, str(tmp_path / "install"), "--dark", "--reset-wallpapers"]]
    assert bootstrap.os.environ["MAC_TAHOE_NO_UPDATE_CHECK"] == "true"


def wrapper_at(tmp_path, monkeypatch, version="0.59.4"):
    root = tmp_path / "wrapper"
    root.mkdir()
    (root / "bootstrap.py").write_text("recipe")
    (root / "defaults.json").write_text('{"wallpaper":"MacGoldenGate"}')
    (root / "upstream.json").write_text(json.dumps({"commit": "a" * 40, "sha256": "0" * 64}))
    (root / "VERSION").write_text(version + "\n")
    monkeypatch.setattr(bootstrap, "ROOT", root)
    monkeypatch.delenv("GOLDEN_GATE_TAHOE_SOURCE", raising=False)
    monkeypatch.delenv("MAC_TAHOE_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("GOLDEN_GATE_UPDATED", raising=False)
    return root


def tahoe_archive(tmp_path, version):
    return archive_at(tmp_path, [
        ("repo/VERSION", tarfile.REGTYPE, version.encode() + b"\n"),
        ("repo/src/scripts/defaults.json", tarfile.REGTYPE, b'{"wallpaper":"MacTahoe"}'),
        ("repo/src/offline/wallpapers/MacGoldenGate/metadata.json", tarfile.REGTYPE, b'{}'),
    ])


@pytest.mark.parametrize("archived", ["0.60.0", "0.59.4"])
def test_prepare_installs_the_latest_tahoe_release(tmp_path, monkeypatch, archived):
    wrapper_at(tmp_path, monkeypatch)
    release = {"repository": bootstrap.TAHOE_REPOSITORY, "commit": "b" * 40, "version": "0.60.0"}
    monkeypatch.setattr(bootstrap, "latest_tahoe", lambda: release)
    archive = tahoe_archive(tmp_path, archived)
    calls = []
    def download(pin, destination):
        calls.append(pin)
        destination.write_bytes(archive.read_bytes())
    monkeypatch.setattr(bootstrap, "download", download)
    if archived != release["version"]:
        with pytest.raises(ValueError, match="does not match its version"):
            bootstrap.prepare()
        return
    prepared = bootstrap.prepare()
    assert calls == [release]
    assert (prepared / ".golden-gate-ready").read_text() == "b" * 40 + "\n"
    assert json.loads((prepared / "src/scripts/defaults.json").read_text())["wallpaper"] == "MacGoldenGate"


def test_disabled_updates_install_the_verified_pin(tmp_path, monkeypatch):
    root = wrapper_at(tmp_path, monkeypatch)
    monkeypatch.setenv("MAC_TAHOE_NO_UPDATE_CHECK", "true")
    monkeypatch.setattr(bootstrap, "latest_tahoe", lambda: pytest.fail("updates are disabled"))
    archive = tahoe_archive(tmp_path, "0.59.4")
    calls = []
    def download(pin, destination):
        calls.append(pin)
        destination.write_bytes(archive.read_bytes())
    monkeypatch.setattr(bootstrap, "download", download)
    bootstrap.prepare()
    assert calls == [json.loads((root / "upstream.json").read_text())]


def test_release_download_is_checked_by_version_not_pin_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"archive"))
    bootstrap.download({"commit": "a" * 40, "version": "0.60.0"}, tmp_path / "download")
    with pytest.raises(ValueError, match="checksum"):
        bootstrap.download({"commit": "a" * 40}, tmp_path / "download")


def test_latest_tahoe_resolves_the_release_commit(monkeypatch):
    replies = {
        f"{bootstrap.TAHOE_REPOSITORY}/releases/latest": b'{"tag_name": "v0.60.0"}',
        f"{bootstrap.TAHOE_REPOSITORY}/commits/v0.60.0": b"c" * 40 + b"\n",
    }
    monkeypatch.setattr(bootstrap, "_github", lambda path, accept=None: replies.get(path))
    assert bootstrap.latest_tahoe() == {
        "repository": bootstrap.TAHOE_REPOSITORY, "commit": "c" * 40, "version": "0.60.0"}
    replies[f"{bootstrap.TAHOE_REPOSITORY}/releases/latest"] = b'{"tag_name": "nightly"}'
    assert bootstrap.latest_tahoe() is None
    monkeypatch.setattr(bootstrap, "_github", lambda path, accept=None: None)
    assert bootstrap.latest_tahoe() is None


class Git:
    def __init__(self, root, status="", pull=0):
        self.root, self.status, self.pull, self.calls = root, status, pull, []

    def __call__(self, *args):
        self.calls.append(args)
        stdout = {"rev-parse": str(self.root) + "\n", "status": self.status}.get(args[0], "")
        code = self.pull if args[0] == "pull" else 0
        return subprocess.CompletedProcess(["git", *args], code, stdout, "")


@pytest.fixture
def updater(tmp_path, monkeypatch):
    root = wrapper_at(tmp_path, monkeypatch)
    (root / ".git").mkdir()
    # Recorded so the restart flag set by update_wrapper is undone afterwards.
    monkeypatch.setenv("GOLDEN_GATE_UPDATED", "0")
    execs = []
    monkeypatch.setattr(bootstrap.os, "execv", lambda executable, args: execs.append(args))
    monkeypatch.setattr(bootstrap, "latest_release", lambda repository: "v0.60.0")
    return root, execs


def test_newer_release_pulls_a_clean_checkout_and_restarts(updater, monkeypatch):
    root, execs = updater
    git = Git(root)
    monkeypatch.setattr(bootstrap, "_git", git)
    bootstrap.update_wrapper("install", ["--dark"])
    assert ("pull", "--ff-only") in git.calls
    assert execs == [[sys.executable, str(root / "install"), "--dark"]]
    assert bootstrap.os.environ["GOLDEN_GATE_UPDATED"] == "1"


@pytest.mark.parametrize("case", ["current", "dirty", "failed-pull", "no-git"])
def test_wrapper_update_falls_back_to_the_current_wrapper(updater, monkeypatch, capsys, case):
    root, execs = updater
    git = Git(root, status=" M bootstrap.py\n" if case == "dirty" else "",
              pull=1 if case == "failed-pull" else 0)
    monkeypatch.setattr(bootstrap, "_git", git)
    if case == "current":
        (root / "VERSION").write_text("0.60.0\n")
    if case == "no-git":
        (root / ".git").rmdir()
    bootstrap.update_wrapper("install", [])
    assert execs == []
    assert ("pull", "--ff-only") not in git.calls or case == "failed-pull"
    assert ("v0.60.0 is available" in capsys.readouterr().out) == (case != "current")


@pytest.mark.parametrize("entry, args, env", [
    ("uninstall", [], {}),
    ("install", ["--prepare"], {}),
    ("install", [], {"GOLDEN_GATE_UPDATED": "1"}),
    ("install", [], {"MAC_TAHOE_NO_UPDATE_CHECK": "true"}),
])
def test_wrapper_update_is_skipped_when_not_wanted(updater, monkeypatch, entry, args, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(bootstrap, "latest_release", lambda repository: pytest.fail("no update check"))
    bootstrap.update_wrapper(entry, args)


def local_checkout(path):
    path.mkdir()
    files = {
        "VERSION": "0.61.0\n",
        "installer": "# local installer\n",
        "src/installer/installer_ui.py": "# local UI\n",
        "src/scripts/defaults.json": '{"wallpaper":"MacTahoe","launcher_preset":1}',
        "src/scripts/launcher_defaults.py": "# presets\n",
        "src/offline/wallpapers/MacGoldenGate/metadata.json": "{}",
    }
    for name, contents in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    obsolete = path / "legacy-install"
    obsolete.write_text("retired")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    obsolete.unlink()
    (path / "new-ui.py").write_text("untracked UI")
    return path


@pytest.mark.parametrize("explicit", [False, True])
def test_local_checkout_stages_current_files_without_network(tmp_path, monkeypatch, explicit):
    wrapper_at(tmp_path, monkeypatch)
    source = local_checkout(tmp_path / "macos-tahoe-liquid-kde")
    if explicit:
        override = local_checkout(tmp_path / "another-tahoe")
        monkeypatch.setenv("GOLDEN_GATE_TAHOE_SOURCE", str(override))
        source = override
    def no_network(*args, **kwargs):
        pytest.fail("Local sources must not query, pull or download releases")
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", no_network)
    monkeypatch.setattr(bootstrap, "_git", no_network)
    assert bootstrap.local_source() == source
    for entry in ("installer", "install", "uninstall"):
        bootstrap.update_wrapper(entry, [])
    original = (source / "src/scripts/defaults.json").read_bytes()
    prepared = bootstrap.prepare()
    assert prepared != source
    assert (prepared / ".golden-gate-ready").read_text() == "local-development\n"
    assert (prepared / "new-ui.py").read_text() == "untracked UI"
    assert not (prepared / "legacy-install").exists()
    assert json.loads((prepared / "src/scripts/defaults.json").read_text())["wallpaper"] == "MacGoldenGate"
    assert (source / "src/scripts/defaults.json").read_bytes() == original
    assert bootstrap.prepare() == prepared
    (source / "new-ui.py").write_text("changed UI")
    refreshed = bootstrap.prepare()
    assert refreshed != prepared
    assert (refreshed / "new-ui.py").read_text() == "changed UI"
    assert (source / "src/scripts/defaults.json").read_bytes() == original


def test_incomplete_explicit_source_does_not_download(tmp_path, monkeypatch):
    wrapper_at(tmp_path, monkeypatch)
    monkeypatch.setenv("GOLDEN_GATE_TAHOE_SOURCE", str(tmp_path / "missing"))
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network"))
    assert bootstrap.main("installer", []) == 1


def test_incomplete_sibling_does_not_shadow_release(tmp_path, monkeypatch):
    wrapper_at(tmp_path, monkeypatch)
    (tmp_path / "macos-tahoe-liquid-kde").mkdir()
    assert bootstrap.local_source() is None
