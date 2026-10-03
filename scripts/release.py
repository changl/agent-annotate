"""Build one immutable stable wheel; publishing is restricted to trusted main/tag runs."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def identity(root=ROOT):
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Stable releases require a numeric X.Y.Z version")
    build_id = os.environ.get("BUILD_ID", "")
    if not re.fullmatch(r"[0-9a-f]{40}", build_id):
        raise ValueError("BUILD_ID must identify the exact source commit")
    tag = "v" + version
    ref = os.environ.get("RELEASE_REF", "")
    if ref.startswith("refs/tags/") and ref != "refs/tags/" + tag:
        raise ValueError("Release tag must match the package version")
    return version, tag, build_id


def github(route):
    repository = os.environ["REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository")
    result = subprocess.run(["gh", "api", f"repos/{repository}/{route}"], capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        return json.loads(result.stdout)
    if "(HTTP 404)" in result.stderr:
        return None
    raise RuntimeError("GitHub release lookup failed; refusing to treat an error as a missing release")


def release_needed(tag, build_id):
    ref = github("git/ref/tags/" + tag)
    commit = ref["object"] if ref else None
    for _ in range(8):
        if not commit or commit["type"] != "tag":
            break
        commit = github("git/tags/" + commit["sha"])["object"]
    if commit and (commit["type"] != "commit" or commit["sha"] != build_id):
        raise ValueError(f"{tag} already identifies another commit; bump the version, never overwrite a release")
    release = github("releases/tags/" + tag)
    if release:
        if not commit or release.get("draft") or release.get("prerelease"):
            raise ValueError("Existing release is incomplete or unstable; refusing to replace it")
        assets = [asset["name"] for asset in release.get("assets", [])]
        for name in (f"agent_annotate-{tag[1:]}-py3-none-any.whl", "SHA256SUMS"):
            if assets.count(name) != 1:
                raise ValueError("Existing stable release lacks unique updater assets; refusing to replace it")
        return False
    return True


def verify_wheel(wheel, root, build_id):
    """Compare the actual wheel's stamp/assets with the checked-out shipping source."""
    with zipfile.ZipFile(wheel) as archive:
        stamp = json.loads(archive.read("agent_annotate/_build.json"))
        version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
        if stamp.get("build_id") != build_id or stamp.get("tag") != "v" + version:
            raise ValueError("Wheel has the wrong source identity")
        for path in (root / "src/agent_annotate/web").iterdir():
            if path.is_file() and archive.read("agent_annotate/web/" + path.name) != path.read_bytes():
                raise ValueError(f"Wheel asset differs from source: {path.name}")


def build_wheel(root, destination, version, tag, build_id):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    wheel = destination / f"agent_annotate-{version}-py3-none-any.whl"
    if wheel.exists():
        raise ValueError("Use an empty build directory; existing wheels are never overwritten")
    with tempfile.TemporaryDirectory(prefix="annotate-release-") as temporary:
        stage = Path(temporary) / "source"
        stage.mkdir()
        for name in ("pyproject.toml", "README.md", "CHANGELOG.md", "LICENSE"):
            shutil.copy2(root / name, stage / name)
        shutil.copytree(root / "src", stage / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        (stage / "src/agent_annotate/_build.json").write_text(json.dumps({"build_id": build_id, "tag": tag}) + "\n")
        subprocess.run([sys.executable, "-m", "build", "--quiet", "--wheel", "--no-isolation", "--outdir", str(destination), str(stage)], check=True)
        verify_wheel(wheel, root, build_id)
        installed = Path(temporary) / "installed"
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--target", str(installed), str(wheel)], check=True)
        # The explicit wheel path wins; -I excludes cwd/PYTHONPATH imports.
        smoke = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import agent_annotate
from agent_annotate.updates import runtime_manifest
from agent_annotate.copy_state import validate_copy
from agent_annotate.project_state import validate_project
from agent_annotate.mcp_server import build_server
assert Path(agent_annotate.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
assert agent_annotate.__version__ == sys.argv[2]
assert runtime_manifest()['build_id'] == sys.argv[3]
assert validate_copy({'blocks':[]}) == {'schema_version':1,'blocks':[]}
validate_project({'modules':[],'tabs':[{'id':'details','label':'Details','kind':'document'}]})
build_server()
print('Installed wheel import, assets, identity, MCP and schemas passed')
"""
        subprocess.run([sys.executable, "-I", "-c", smoke, str(installed), version, build_id], check=True)
    (destination / "SHA256SUMS").write_text(f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n")
    return wheel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "build", "publish"))
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    version, tag, build_id = identity()
    if args.command == "prepare":
        needed = release_needed(tag, build_id)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as target:
            target.write("needed=" + str(needed).lower() + "\n")
        print(f"{tag}: {'build needed' if needed else 'already published from this commit'}")
    elif args.command == "build":
        build_wheel(ROOT, args.dist, version, tag, build_id)
    elif release_needed(tag, build_id):
        wheel = args.dist / f"agent_annotate-{version}-py3-none-any.whl"
        verify_wheel(wheel, ROOT, build_id)
        expected = f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n"
        if (args.dist / "SHA256SUMS").read_text() != expected:
            raise ValueError("Wheel checksum does not match the updater manifest")
        subprocess.run(["gh", "release", "create", tag, str(wheel), str(args.dist / "SHA256SUMS"),
                        "--repo", os.environ["REPOSITORY"], "--target", build_id, "--generate-notes"], check=True)


if __name__ == "__main__":
    main()
