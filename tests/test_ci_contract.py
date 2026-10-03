"""Release guards validate shipping artifacts and cannot replace another source build."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from agent_annotate.updates import _checksum

SPEC = importlib.util.spec_from_file_location("release_script", Path(__file__).parents[1] / "scripts/release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
COMMIT = "a" * 40
TAG = "v2.23.0"
ASSETS = [{"name": "agent_annotate-2.23.0-py3-none-any.whl"}, {"name": "SHA256SUMS"}]


@pytest.fixture
def shipping_wheel(tmp_path):
    root = tmp_path / "source"
    web = root / "src/agent_annotate/web"
    web.mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nversion="2.23.0"\n')
    (web / "shell.js").write_text("window.shipping=true;")
    (web / "daisyui.css").write_text(":root{color:black}")
    wheel = tmp_path / "agent_annotate-2.23.0-py3-none-any.whl"
    def write(*, build_id=COMMIT, altered=False, missing=False):
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("agent_annotate/_build.json", json.dumps({"build_id": build_id, "tag": TAG}))
            for path in web.iterdir():
                if missing and path.name == "daisyui.css":
                    continue
                archive.writestr("agent_annotate/web/" + path.name, b"wrong" if altered else path.read_bytes())
    write()
    return root, wheel, write


def test_actual_packaged_assets_stamp_and_checksum_match_updater(shipping_wheel):
    root, wheel, _write = shipping_wheel
    release.verify_wheel(wheel, root, COMMIT)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert _checksum(f"{digest}  {wheel.name}\n".encode(), wheel.name) == digest


@pytest.mark.parametrize("change", ["build_id", "altered", "missing"])
def test_wrong_identity_changed_or_missing_packaged_asset_rejects_release(shipping_wheel, change):
    root, wheel, write = shipping_wheel
    write(**({"build_id": "b" * 40} if change == "build_id" else {change: True}))
    with pytest.raises((ValueError, KeyError)):
        release.verify_wheel(wheel, root, COMMIT)


def test_existing_matching_stable_release_is_idempotent_without_build_or_upload(monkeypatch):
    responses = {"git/ref/tags/" + TAG: {"object": {"type": "tag", "sha": "annotated"}},
                 "git/tags/annotated": {"object": {"type": "commit", "sha": COMMIT}},
                 "releases/tags/" + TAG: {"draft": False, "prerelease": False, "assets": ASSETS}}
    monkeypatch.setattr(release, "github", responses.__getitem__)
    assert release.release_needed(TAG, COMMIT) is False


@pytest.mark.parametrize("existing_release", [False, True])
def test_existing_tag_at_other_source_commit_fails_before_any_publish(monkeypatch, existing_release):
    calls = []
    def github(route):
        calls.append(route)
        if route.startswith("git/ref/"):
            return {"object": {"type": "commit", "sha": "b" * 40}}
        return {"assets": ASSETS} if existing_release else None
    monkeypatch.setattr(release, "github", github)
    with pytest.raises(ValueError, match="never overwrite"):
        release.release_needed(TAG, COMMIT)
    assert calls == ["git/ref/tags/" + TAG]


@pytest.mark.parametrize("assets", [[], ASSETS + [ASSETS[0]]])
def test_existing_release_with_missing_or_duplicate_updater_assets_is_not_replaced(monkeypatch, assets):
    monkeypatch.setattr(release, "github", lambda route: {"object": {"type": "commit", "sha": COMMIT}}
                        if route.startswith("git/ref/") else {"assets": assets})
    with pytest.raises(ValueError, match="refusing to replace"):
        release.release_needed(TAG, COMMIT)


def test_missing_release_can_be_built_but_lookup_failures_fail_closed(monkeypatch):
    original_github = release.github
    monkeypatch.setattr(release, "github", lambda route: None)
    assert release.release_needed(TAG, COMMIT) is True
    monkeypatch.setattr(release, "github", original_github)
    monkeypatch.setenv("REPOSITORY", "changl/agent-annotate")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "gh: Forbidden (HTTP 403)"))
    with pytest.raises(RuntimeError, match="lookup failed"):
        release.github("releases/tags/" + TAG)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "gh: Not Found (HTTP 404)"))
    assert release.github("releases/tags/" + TAG) is None


def test_mismatched_tag_or_ambiguous_build_identity_cannot_ship(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="2.23.0"\n')
    monkeypatch.setenv("BUILD_ID", COMMIT)
    monkeypatch.setenv("RELEASE_REF", "refs/tags/v2.22.0")
    with pytest.raises(ValueError, match="match the package"):
        release.identity(tmp_path)
    monkeypatch.setenv("RELEASE_REF", "refs/heads/main")
    monkeypatch.setenv("BUILD_ID", "main")
    with pytest.raises(ValueError, match="exact source commit"):
        release.identity(tmp_path)


def test_publish_checks_artifact_checksum_before_any_upload(shipping_wheel, monkeypatch):
    root, wheel, _write = shipping_wheel
    manifest = wheel.parent / "SHA256SUMS"
    manifest.write_text("incorrect checksum\n")
    calls = []
    monkeypatch.setattr(release, "identity", lambda: ("2.23.0", TAG, COMMIT))
    monkeypatch.setattr(release, "ROOT", root)
    monkeypatch.setattr(release, "release_needed", lambda *args: True)
    monkeypatch.setenv("REPOSITORY", "changl/agent-annotate")
    monkeypatch.setattr(sys, "argv", ["release.py", "publish", "--dist", str(wheel.parent)])
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: calls.append(command))
    with pytest.raises(ValueError, match="checksum"):
        release.main()
    assert calls == []
    manifest.write_text(f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n")
    release.main()
    assert calls == [["gh", "release", "create", TAG, str(wheel), str(manifest),
                      "--repo", "changl/agent-annotate", "--target", COMMIT, "--generate-notes"]]


def test_build_cannot_overwrite_an_existing_shipping_artifact(shipping_wheel):
    root, wheel, _write = shipping_wheel
    before = wheel.read_bytes()
    with pytest.raises(ValueError, match="never overwritten"):
        release.build_wheel(root, wheel.parent, "2.23.0", TAG, COMMIT)
    assert wheel.read_bytes() == before
    assert not (root / "src/agent_annotate/_build.json").exists()
