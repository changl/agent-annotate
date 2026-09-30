"""Opt-in, release-pinned updates; staging never activates a runtime.

GitHub's stable release supplies one wheel and its SHA256SUMS entry. Each
version gets a separate environment. Runtime activation, page restart and
scheduling belong to the caller, not this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import __version__
from .paths import CONFIG_DIR, PACKAGE_DIR, STATE_DIR, WEB_DIR

RELEASE_API = "https://api.github.com/repos/changl/agent-annotate/releases/latest"
RELEASE_DOWNLOAD = "https://github.com/changl/agent-annotate/releases/download"
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
NETWORK_TIMEOUT = 20
_VERSION_RE = re.compile(r"(?:v)?(\d+)\.(\d+)\.(\d+)\Z", re.ASCII)
_TAG_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)\Z", re.ASCII)
_REDIRECT_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def version_tuple(version: str) -> tuple[int, int, int]:
    """Compare stable versions numerically, never lexicographically."""
    match = _VERSION_RE.fullmatch(str(version))
    if not match:
        raise ValueError(f"invalid stable version: {version!r}")
    return tuple(int(part) for part in match.groups())


def is_newer(candidate: str, installed: str = __version__) -> bool:
    return version_tuple(candidate) > version_tuple(installed)


def _asset_url(url: str, tag: str, name: str) -> str:
    expected = f"{RELEASE_DOWNLOAD}/{tag}/{name}"
    if url != expected:
        raise ValueError(f"release asset must use its exact GitHub download URL: {name}")
    return url


class _ReleaseRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if (parsed.scheme != "https" or parsed.hostname not in _REDIRECT_HOSTS
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            raise ValueError("release download redirected outside GitHub's HTTPS asset hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_url(request):
    return urllib.request.build_opener(_ReleaseRedirectHandler()).open(request, timeout=NETWORK_TIMEOUT)


def _fetch_bytes(url: str, limit: int = MAX_DOWNLOAD_BYTES) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": f"agent-annotate/{__version__}",
        "Accept": "application/vnd.github+json" if url == RELEASE_API else "application/octet-stream",
    })
    try:
        with _open_url(request) as response:
            size = response.headers.get("Content-Length")
            if size is not None and int(size) > limit:
                raise ValueError(f"release download exceeds {limit} bytes")
            body = response.read(limit + 1)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"GitHub release download failed: {exc}") from exc
    if len(body) > limit:
        raise ValueError(f"release download exceeds {limit} bytes")
    return body


def _release_identity(tag: str) -> tuple[str, str]:
    if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
        raise ValueError("stable release tag must have form vMAJOR.MINOR.PATCH")
    version = tag[1:]
    return version, f"agent_annotate-{version}-py3-none-any.whl"


def latest_release() -> dict:
    """Read stable release metadata. No config write or environment install."""
    release = json.loads(_fetch_bytes(RELEASE_API, MAX_METADATA_BYTES))
    if not isinstance(release, dict):
        raise ValueError("GitHub release metadata must be an object")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError("draft and prerelease builds cannot enter the stable channel")
    tag = release.get("tag_name")
    version, wheel_name = _release_identity(tag)
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("stable release lacks asset metadata")
    urls = {}
    for name in (wheel_name, "SHA256SUMS"):
        matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"stable release must contain exactly one {name}")
        asset = matches[0]
        size = asset.get("size")
        if isinstance(size, int) and size > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"release asset exceeds {MAX_DOWNLOAD_BYTES} bytes: {name}")
        urls[name] = _asset_url(asset.get("browser_download_url"), tag, name)
    return {
        "tag_name": tag,
        "version": version,
        "wheel_name": wheel_name,
        "wheel_url": urls[wheel_name],
        "checksums_url": urls["SHA256SUMS"],
        "published_at": release.get("published_at"),
        "html_url": f"https://github.com/changl/agent-annotate/releases/tag/{tag}",
    }


def _checksum(manifest: bytes, wheel_name: str) -> str:
    matches = []
    for line in manifest.decode("utf-8").splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64})[ \t]+\*?([^/\\\r\n]+)", line)
        if match and match.group(2) == wheel_name:
            matches.append(match.group(1).lower())
    if len(matches) != 1:
        raise ValueError(f"SHA256SUMS must contain exactly one checksum for {wheel_name}")
    return matches[0]


def _verify_python(python: Path, version: str) -> None:
    result = subprocess.run(
        [str(python), "-I", "-m", "agent_annotate.cli", "--version"],
        check=True, capture_output=True, text=True, timeout=30,
    )
    if result.stdout.strip() != f"agent-annotate {version}":
        raise ValueError("staged runtime version does not match the stable release tag")


def stage_release(release: dict) -> Path:
    """Download, hash-check and install a release into its own environment.

    Returns the staged Python executable. Never changes a launcher, active
    environment, page registry, comments, bus, owner or transport. An existing
    version directory is reused only with a matching verified staging receipt.
    """
    version, wheel_name = _release_identity(release.get("tag_name"))
    if release.get("version") != version or release.get("wheel_name") != wheel_name:
        raise ValueError("release version and wheel must match its tag")
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("draft and prerelease builds cannot be staged as stable")
    wheel_url = _asset_url(release.get("wheel_url"), release["tag_name"], wheel_name)
    sums_url = _asset_url(release.get("checksums_url"), release["tag_name"], "SHA256SUMS")
    digest = _checksum(_fetch_bytes(sums_url, MAX_METADATA_BYTES), wheel_name)
    root = STATE_DIR / "releases"
    stage = root / version
    python = stage / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    receipt = {"version": version, "tag_name": release["tag_name"], "wheel_sha256": digest}
    if stage.exists():
        marker = stage / "staged.json"
        if stage.is_symlink() or not marker.is_file() or json.loads(marker.read_text()) != receipt:
            raise ValueError(f"existing release directory is unmanaged or conflicts with release: {stage}")
        _verify_python(python, version)
        return python
    wheel = _fetch_bytes(wheel_url)
    if hashlib.sha256(wheel).hexdigest() != digest:
        raise ValueError("release wheel SHA256 does not match SHA256SUMS")
    root.mkdir(parents=True, exist_ok=True)
    # mkdir is the per-version claim: a competing updater cannot replace it.
    stage.mkdir()
    try:
        artifact = stage / wheel_name
        artifact.write_bytes(wheel)
        subprocess.run(["uv", "venv", str(stage / "venv")], check=True,
                       capture_output=True, text=True, timeout=120)
        subprocess.run(["uv", "pip", "install", "--python", str(python), str(artifact)],
                       check=True, capture_output=True, text=True, timeout=300)
        _verify_python(python, version)
        _atomic_json(stage / "staged.json", receipt)
    except BaseException:
        # Only this call's newly claimed directory is removed on failure.
        shutil.rmtree(stage)
        raise
    return python


def runtime_manifest() -> dict:
    """Identify both release version and actual code/assets of this runtime."""
    build_id = None
    build_file = PACKAGE_DIR / "_build.json"
    if build_file.is_file():
        build = json.loads(build_file.read_text(encoding="utf-8"))
        if isinstance(build, dict):
            build_id = next((build[key] for key in ("build_id", "git_commit", "commit", "build")
                             if isinstance(build.get(key), str) and build[key]), None)
    if build_id is None and (PACKAGE_DIR.parent.parent / ".git").exists():
        try:
            result = subprocess.run(["git", "-C", str(PACKAGE_DIR), "rev-parse", "HEAD"],
                                    check=True, capture_output=True, text=True, timeout=5)
            build_id = result.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
    assets = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(WEB_DIR.iterdir()) if path.is_file()}
    if build_id is None:
        build_id = "assets:" + hashlib.sha256(json.dumps(assets, sort_keys=True).encode()).hexdigest()
    return {"package_version": __version__, "build_id": build_id, "assets": assets}


def _validate_enrollment(config: dict) -> dict:
    if not isinstance(config, dict) or config.get("channel") != "stable":
        raise ValueError("update enrollment only supports the stable channel")
    if not isinstance(config.get("enabled"), bool):
        raise ValueError("update enrollment enabled must be a boolean")
    return config


def read_enrollment() -> dict:
    """Absent config means disabled. Reading does not create any directories."""
    path = CONFIG_DIR / "update.json"
    config = {"channel": "stable", "enabled": False}
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            raise ValueError("update enrollment must be an object")
        config.update(saved)
    return _validate_enrollment(config)


def _atomic_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(content, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def write_enrollment(config: dict) -> dict:
    """Merge explicit enrollment changes without dropping local config keys."""
    updated = read_enrollment()
    updated.update(config)
    _validate_enrollment(updated)
    _atomic_json(CONFIG_DIR / "update.json", updated)
    return updated
