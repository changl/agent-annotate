"""Install a release wheel on this Mac only after a validated full-suite receipt for its exact source.

scripts/release.py stamps every wheel with agent_annotate/_build.json, naming
the main commit it was built from. This entrypoint reads that stamp from the
very wheel it will install, requires a Windmill receipt for the "full" profile
at exactly that commit, has the shared wm-test helper validate it against the
server's own record, and only then runs uv tool install on the same bytes
(agent-annotate-4zw). --tool-dir/--bin-dir install into a disposable target.

    python scripts/verified_install.py WHEEL_URL_OR_PATH --request STATE.json [--job JOB_ID]
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

REPO = "agent-annotate"
PROFILE = "full"
WHEEL = re.compile(r"agent_annotate-([0-9]+\.[0-9]+\.[0-9]+)-py3-none-any\.whl")


def fetch(url, directory):
    """Download a release wheel and check it against the release's SHA256SUMS."""
    name = url.rsplit("/", 1)[-1]
    if not url.startswith("https://") or not WHEEL.fullmatch(name):
        raise ValueError("wheel URL must be an https release wheel")
    directory.mkdir(parents=True, exist_ok=True)
    body = urlopen(url, timeout=60).read()
    sums = urlopen(url.rsplit("/", 1)[0] + "/SHA256SUMS", timeout=60).read().decode()
    if f"{hashlib.sha256(body).hexdigest()}  {name}" not in sums.splitlines():
        raise ValueError("wheel does not match the release's SHA256SUMS")
    wheel = directory / name
    wheel.write_bytes(body)
    return wheel


def wheel_identity(wheel):
    """The exact source commit and tag stamped into this wheel by scripts/release.py."""
    match = WHEEL.fullmatch(wheel.name)
    try:
        with zipfile.ZipFile(wheel) as archive:
            stamp = json.loads(archive.read("agent_annotate/_build.json"))
    except (KeyError, zipfile.BadZipFile, ValueError):
        raise ValueError("wheel carries no build stamp") from None
    build_id, tag = stamp.get("build_id", ""), stamp.get("tag", "")
    if not re.fullmatch(r"[0-9a-f]{40}", build_id):
        raise ValueError("wheel stamp names no exact source commit")
    if not match or tag != "v" + match[1]:
        raise ValueError("wheel name and build stamp disagree")
    return build_id, tag


def validated_receipt(request_file, job_id, wm_test, build_id):
    """wm-test's own validation of the server's record, for the full profile at build_id."""
    state = json.loads(Path(request_file).read_text())
    request = state.get("request", state)
    job_id = job_id or state.get("job_id")
    if request.get("repo") != REPO or request.get("profile") != PROFILE or request.get("sha") != build_id:
        raise ValueError(f"receipt request is not the {PROFILE} profile of {REPO} at {build_id}")
    if not job_id:
        raise ValueError("no Windmill job id for the receipt")
    result = subprocess.run([wm_test, "validate", job_id, "--request", str(request_file)],
                            capture_output=True, text=True, timeout=300)
    try:
        verdict = json.loads(result.stdout or "{}")
    except ValueError:
        verdict = {}
    if (result.returncode != 0 or verdict.get("validated") is not True
            or verdict.get("verdict") != "passed" or verdict.get("cleanup") != "verified"):
        try:
            reason = json.loads(result.stderr or "{}").get("error")
        except ValueError:
            reason = None
        raise ValueError("receipt rejected: " + (reason or f"wm-test exit {result.returncode}"))
    return verdict


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wheel", help="release wheel URL (https) or local path")
    parser.add_argument("--request", required=True, type=Path, help="wm-test request or state file of the full run")
    parser.add_argument("--job", help="Windmill job id (default: the state file's job_id)")
    parser.add_argument("--wm-test", default=str(Path.home() / ".local/bin/wm-test"))
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--wheel-dir", type=Path, default=Path.home() / ".local/share/agent-annotate/wheels",
                        help="where a downloaded wheel is kept (uv records its path)")
    parser.add_argument("--tool-dir", type=Path, help="UV_TOOL_DIR for a disposable install target")
    parser.add_argument("--bin-dir", type=Path, help="UV_TOOL_BIN_DIR for a disposable install target")
    parser.add_argument("--dry-run", action="store_true", help="validate and report; install nothing")
    args = parser.parse_args(argv)
    try:
        wheel = fetch(args.wheel, args.wheel_dir) if "://" in args.wheel else Path(args.wheel).resolve()
        build_id, tag = wheel_identity(wheel)
        verdict = validated_receipt(args.request, args.job, args.wm_test, build_id)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"installed": False, "error": str(error)}), file=sys.stderr)
        return 2
    env = dict(os.environ)
    if args.tool_dir:
        env["UV_TOOL_DIR"] = str(args.tool_dir)
    if args.bin_dir:
        env["UV_TOOL_BIN_DIR"] = str(args.bin_dir)
    report = {"tag": tag, "build_id": build_id, "receipt_job": verdict.get("result_job_id"),
              "evidence_url": verdict.get("evidence_url"), "counts": verdict.get("counts"),
              "installed": False}
    if not args.dry_run:
        subprocess.run([args.uv, "tool", "install", "--python", "3.12", "--force",
                        f"agent-annotate[mcp] @ {wheel.as_uri()}"], env=env, check=True)
        report["installed"] = True
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
