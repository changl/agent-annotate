"""Release updates stay deterministic, sandboxed and inactive until applied."""

import hashlib
import io
import json
import subprocess
from types import SimpleNamespace

import pytest

from agent_annotate import updates


@pytest.fixture
def estate(tmp_path, monkeypatch):
    state = tmp_path / "state"
    config = tmp_path / "config"
    state.mkdir()
    config.mkdir()
    page = tmp_path / "page"
    page.mkdir()
    comments = page / "comments.json"
    comments.write_text('{"reviewer":"preserve me"}')
    registry = state / "project.json"
    registry.write_text('{"slugs":{"review":{"owner_session":"original","port":8802}}}')
    transport = config / "projects.toml"
    transport.write_text('[reviews]\ntransport="tailscale"\n')
    monkeypatch.setattr(updates, "STATE_DIR", state)
    monkeypatch.setattr(updates, "CONFIG_DIR", config)
    monkeypatch.setattr(updates, "_inherited_mcp_version", lambda: None)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs.get("shell") is None
        if argv[-1] == "--version":
            return SimpleNamespace(stdout="agent-annotate 2.20.0\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(updates.subprocess, "run", run)
    return SimpleNamespace(state=state, config=config, comments=comments,
                           registry=registry, transport=transport, calls=calls)


def _github_release(**changes):
    tag = "v2.20.0"
    wheel = "agent_annotate-2.20.0-py3-none-any.whl"
    release = {
        "tag_name": tag, "draft": False, "prerelease": False,
        "assets": [{"name": name, "size": 100,
                    "browser_download_url": f"{updates.RELEASE_DOWNLOAD}/{tag}/{name}"}
                   for name in (wheel, "SHA256SUMS")],
    }
    release.update(changes)
    return release


def _mock_downloads(monkeypatch, wheel=b"verified wheel"):
    source = _github_release()
    name = source["assets"][0]["name"]
    digest = hashlib.sha256(wheel).hexdigest()
    manifest = f"{digest}  {name}\n".encode()

    def fetch(url, limit=updates.MAX_DOWNLOAD_BYTES):
        if url == updates.RELEASE_API:
            return json.dumps(source).encode()
        if url.endswith("/SHA256SUMS"):
            return manifest
        if url.endswith("/" + name):
            return wheel
        raise AssertionError(f"unexpected network URL: {url}")

    monkeypatch.setattr(updates, "_fetch_bytes", fetch)
    return source


@pytest.mark.parametrize("candidate,installed,newer", [
    ("2.10.0", "2.9.99", True), ("v2.20.0", "2.19.0", True),
    ("2.19.0", "2.19.0", False), ("2.9.0", "2.10.0", False),
])
def test_versions_are_compared_numerically(candidate, installed, newer):
    assert updates.is_newer(candidate, installed) is newer


@pytest.mark.parametrize("tag", ["2.20.0", "v2.20", "v2.20.0-rc1", "main", "v2.20.0/../../x", "v２.20.0"])
def test_latest_refuses_bad_stable_tags(monkeypatch, tag):
    monkeypatch.setattr(updates, "_fetch_bytes", lambda *args: json.dumps(_github_release(tag_name=tag)).encode())
    with pytest.raises(ValueError, match="tag"):
        updates.latest_release()


@pytest.mark.parametrize("flag", ["draft", "prerelease"])
def test_latest_refuses_nonstable_release(monkeypatch, flag):
    monkeypatch.setattr(updates, "_fetch_bytes", lambda *args: json.dumps(_github_release(**{flag: True})).encode())
    with pytest.raises(ValueError, match="stable channel"):
        updates.latest_release()


def test_latest_check_does_not_install_or_write_config(estate, monkeypatch):
    _mock_downloads(monkeypatch)
    release = updates.latest_release()
    assert release["version"] == "2.20.0"
    assert release["wheel_name"] == "agent_annotate-2.20.0-py3-none-any.whl"
    assert estate.calls == []
    assert not (estate.state / "releases").exists()
    assert not (estate.config / "update.json").exists()


@pytest.mark.parametrize("url", [
    "http://github.com/changl/agent-annotate/releases/download/v2.20.0/SHA256SUMS",
    "https://example.com/SHA256SUMS",
    "https://github.com/other/repo/releases/download/v2.20.0/SHA256SUMS",
    "https://github.com/changl/agent-annotate/releases/download/v2.20.0/SHA256SUMS?next=evil",
])
def test_latest_rejects_arbitrary_asset_urls(monkeypatch, url):
    release = _github_release()
    release["assets"][1]["browser_download_url"] = url
    monkeypatch.setattr(updates, "_fetch_bytes", lambda *args: json.dumps(release).encode())
    with pytest.raises(ValueError, match="exact GitHub"):
        updates.latest_release()


@pytest.mark.parametrize("asset_change", ["missing", "duplicate", "oversize"])
def test_latest_requires_unique_bounded_artifacts(monkeypatch, asset_change):
    release = _github_release()
    if asset_change == "missing":
        release["assets"].pop()
    elif asset_change == "duplicate":
        release["assets"].append(release["assets"][0])
    else:
        release["assets"][0]["size"] = updates.MAX_DOWNLOAD_BYTES + 1
    monkeypatch.setattr(updates, "_fetch_bytes", lambda *args: json.dumps(release).encode())
    with pytest.raises(ValueError):
        updates.latest_release()


def test_stage_creates_separate_environment_and_preserves_estate(estate, monkeypatch):
    _mock_downloads(monkeypatch)
    before = {path: path.read_bytes() for path in (estate.comments, estate.registry, estate.transport)}
    python = updates.stage_release(updates.latest_release())
    assert python == estate.state / "releases" / "2.20.0" / "venv" / "bin" / "python"
    assert estate.calls[0] == ["uv", "venv", str(python.parent.parent)]
    assert estate.calls[1][:5] == ["uv", "pip", "install", "--python", str(python)]
    assert estate.calls[2] == [str(python), "-I", "-m", "agent_annotate.cli", "--version"]
    assert (python.parent.parent.parent / "staged.json").is_file()
    assert all(path.read_bytes() == body for path, body in before.items())
    assert not (estate.config / "update.json").exists()


def test_stage_reuses_only_verified_existing_environment(estate, monkeypatch):
    _mock_downloads(monkeypatch)
    release = updates.latest_release()
    python = updates.stage_release(release)
    estate.calls.clear()
    assert updates.stage_release(release) == python
    assert estate.calls == [[str(python), "-I", "-m", "agent_annotate.cli", "--version"]]


def test_stage_never_overwrites_existing_unmanaged_directory(estate, monkeypatch):
    _mock_downloads(monkeypatch)
    target = estate.state / "releases" / "2.20.0"
    target.mkdir(parents=True)
    sentinel = target / "active-runtime"
    sentinel.write_text("keep")
    with pytest.raises(ValueError, match="unmanaged"):
        updates.stage_release(updates.latest_release())
    assert sentinel.read_text() == "keep"
    assert estate.calls == []


def test_stage_refuses_hash_mismatch_before_install(estate, monkeypatch):
    _mock_downloads(monkeypatch)
    original = updates._fetch_bytes
    monkeypatch.setattr(updates, "_fetch_bytes", lambda url, limit=updates.MAX_DOWNLOAD_BYTES:
                        b"tampered" if url.endswith(".whl") else original(url, limit))
    with pytest.raises(ValueError, match="SHA256"):
        updates.stage_release(updates.latest_release())
    assert estate.calls == []
    assert not (estate.state / "releases").exists()


def test_stage_checks_tag_version_and_url_again(estate, monkeypatch):
    _mock_downloads(monkeypatch)
    release = updates.latest_release()
    release["wheel_url"] = "https://example.com/tampered.whl"
    with pytest.raises(ValueError, match="exact GitHub"):
        updates.stage_release(release)
    assert estate.calls == []


def test_wrong_installed_version_cleans_only_new_stage(estate, monkeypatch):
    _mock_downloads(monkeypatch)
    def run(argv, **kwargs):
        return SimpleNamespace(stdout="agent-annotate 2.19.0\n")
    monkeypatch.setattr(updates.subprocess, "run", run)
    with pytest.raises(ValueError, match="version does not match"):
        updates.stage_release(updates.latest_release())
    assert not (estate.state / "releases" / "2.20.0").exists()
    assert estate.registry.exists()
    assert estate.comments.exists()


def test_install_failure_does_not_modify_active_state(estate, monkeypatch):
    _mock_downloads(monkeypatch)
    def run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)
    monkeypatch.setattr(updates.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        updates.stage_release(updates.latest_release())
    assert not (estate.state / "releases" / "2.20.0").exists()
    assert json.loads(estate.registry.read_text())["slugs"]["review"]["owner_session"] == "original"


@pytest.mark.parametrize("declared", [None, "99999999"])
def test_download_limit_applies_with_and_without_content_length(monkeypatch, declared):
    response = io.BytesIO(b"x" * 5)
    response.headers = {} if declared is None else {"Content-Length": declared}
    monkeypatch.setattr(updates, "_open_url", lambda request: response)
    with pytest.raises(ValueError, match="exceeds"):
        updates._fetch_bytes(updates.RELEASE_API, limit=4)


@pytest.mark.parametrize("url", ["http://github.com/file", "https://example.com/file", "https://user@github.com/file"])
def test_redirects_cannot_escape_https_github_asset_hosts(url):
    handler = updates._ReleaseRedirectHandler()
    request = updates.urllib.request.Request(updates.RELEASE_API)
    with pytest.raises(ValueError, match="redirected outside"):
        handler.redirect_request(request, None, 302, "Found", {}, url)


@pytest.mark.parametrize("manifest", [b"", b"badchecksum  wheel.whl\n", b"0" * 64 + b"  other.whl\n"])
def test_checksum_requires_exact_wheel_entry(manifest):
    with pytest.raises(ValueError, match="exactly one"):
        updates._checksum(manifest, "wheel.whl")


def test_duplicate_checksums_are_rejected():
    line = "0" * 64 + "  wheel.whl\n"
    with pytest.raises(ValueError, match="exactly one"):
        updates._checksum((line + line).encode(), "wheel.whl")


def test_enrollment_is_disabled_by_default_and_preserves_local_keys(estate):
    assert updates.read_enrollment() == {"channel": "stable", "enabled": False}
    assert not (estate.config / "update.json").exists()
    updates.write_enrollment({"enabled": True, "machine_note": "keep", "last_check": "2026-09-29"})
    updates.write_enrollment({"last_check": "2026-09-30"})
    assert updates.read_enrollment() == {"channel": "stable", "enabled": True,
                                         "machine_note": "keep", "last_check": "2026-09-30"}
    assert not list(estate.config.glob(".update.json.*"))


@pytest.mark.parametrize("config", [{"channel": "main"}, {"enabled": "true"}])
def test_enrollment_rejects_ambiguous_or_unstable_config(estate, config):
    with pytest.raises(ValueError):
        updates.write_enrollment(config)
    assert not (estate.config / "update.json").exists()


def test_config_write_is_atomic_and_preserves_previous_on_failure(estate, monkeypatch):
    updates.write_enrollment({"enabled": True})
    def fail_replace(*args):
        raise OSError("cannot replace")
    monkeypatch.setattr(updates.os, "replace", fail_replace)
    with pytest.raises(OSError):
        updates.write_enrollment({"enabled": False})
    assert updates.read_enrollment()["enabled"] is True
    assert not list(estate.config.glob(".update.json.*"))


def test_manifest_distinguishes_same_version_different_builds(estate, monkeypatch, tmp_path):
    package = tmp_path / "package"
    web = package / "web"
    web.mkdir(parents=True)
    (web / "shell.js").write_text("first")
    monkeypatch.setattr(updates, "PACKAGE_DIR", package)
    monkeypatch.setattr(updates, "WEB_DIR", web)
    (package / "_build.json").write_text('{"commit":"build-one"}')
    first = updates.runtime_manifest()
    (package / "_build.json").write_text('{"commit":"build-two"}')
    (web / "shell.js").write_text("second")
    second = updates.runtime_manifest()
    assert first["package_version"] == second["package_version"]
    assert first["build_id"] != second["build_id"]
    assert first["assets"] != second["assets"]


def test_manifest_includes_source_checkout_head(estate, monkeypatch, tmp_path):
    root = tmp_path / "checkout"
    package = root / "src" / "agent_annotate"
    web = package / "web"
    web.mkdir(parents=True)
    (root / ".git").write_text("gitdir: somewhere\n")
    (web / "shell.js").write_text("asset")
    monkeypatch.setattr(updates, "PACKAGE_DIR", package)
    monkeypatch.setattr(updates, "WEB_DIR", web)
    monkeypatch.setattr(updates.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="source-head\n"))
    assert updates.runtime_manifest()["build_id"] == "source-head"


def test_manifest_falls_back_to_asset_digest(estate, monkeypatch, tmp_path):
    package = tmp_path / "package"
    web = package / "web"
    web.mkdir(parents=True)
    (web / "shell.js").write_text("first")
    monkeypatch.setattr(updates, "PACKAGE_DIR", package)
    monkeypatch.setattr(updates, "WEB_DIR", web)
    first = updates.runtime_manifest()
    (web / "shell.js").write_text("second")
    assert first["build_id"] != updates.runtime_manifest()["build_id"]


def test_mcp_capability_and_version_are_preserved(estate, monkeypatch):
    _mock_downloads(monkeypatch, wheel=b"wheel")
    release = updates.latest_release()
    monkeypatch.setattr(updates, "_inherited_mcp_version", lambda: "2.2.0")
    updates.stage_release(release)
    assert any("mcp==2.2.0" in command for command in estate.calls)
    assert any("from agent_annotate.mcp_server import build_server; build_server()" in command for command in estate.calls)
