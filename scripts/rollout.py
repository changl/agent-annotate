#!/usr/bin/env python3
"""Roll an agent-annotate release out to one Mac and print one line per Mac.

  rollout.py plan VERSION --mac M1          read-only: what apply would do
  rollout.py apply VERSION --mac M1         install, sync skills, restart pages, check, log
  rollout.py rollback --mac M1              back to the version the last apply replaced
  rollout.py apply VERSION --mac M1 --hold-json SLUG   keep a page on JSON across applies
  rollout.py apply VERSION --mac M1 --move-page SLUG   move just that held page later
  rollout.py status                         every Mac's version from here
  ... --mac M5 --approval "card #212"       another Mac, through an Orca environment terminal

Stdlib only (macOS python3 3.9+); ships as a release asset listed in SHA256SUMS.
Every step stops on failure and rolls the Mac back. Another Mac needs --approval
(Chang's yes) even for plan, because it runs commands there; without it nothing
is sent. Sandbox: UV_TOOL_DIR + UV_TOOL_BIN_DIR, the package's ANNOTATE_* path
overrides, ANNOTATE_ROLLOUT_HOME, ANNOTATE_ROLLOUT_RELEASES (https or file:// base).
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid
from pathlib import Path

ENVIRONMENTS = {"M1": None, "M5": "M5Max", "M1Max16": "M1Max16"}  # Mac -> Orca environment
LOCAL_HOSTS = {"M1Max": "M1"}  # short hostname -> Mac; the remote side always gets --local
WORKTREES = {"M5": "id:b8f85d95-9f94-4fa2-a306-0189b3c3f017::/Users/changlee/projects/agent-annotate/codex"}
HOME = Path(os.environ.get("ANNOTATE_ROLLOUT_HOME") or Path.home() / ".local/share/annotate-rollout")
RELEASES = os.environ.get("ANNOTATE_ROLLOUT_RELEASES") or "https://github.com/changl/agent-annotate/releases/download"
RELEASES_API = "https://api.github.com/repos/changl/agent-annotate/releases?per_page=50"
TOOL_DIR = Path(os.environ.get("UV_TOOL_DIR") or Path.home() / ".local/share/uv/tools")
PYTHON = TOOL_DIR / "agent-annotate/bin/python"
MIN_FREE = 2 * 1024 ** 3
REMOTE_TIMEOUT = 1800
REASONS = {"page registry lacks a valid directory, current document or port": "no current version"}


class Failed(Exception):
    def __init__(self, step, detail):
        super().__init__(f"{step}: {detail}")
        self.step, self.detail = step, detail


def vtuple(version):
    parts = version.lstrip("v").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise SystemExit(f"rollout.py: not a release version: {version}")
    return tuple(int(p) for p in parts)


def wheel_name(version):
    return f"agent_annotate-{version}-py3-none-any.whl"


def asset_url(version, name):
    return f"{RELEASES}/v{version}/{name}"


def run(argv, timeout=600, step=None):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    proc = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout, env=env)
    if step and proc.returncode:
        raise Failed(step, last_line(proc))
    return proc


def last_line(proc):
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return re.sub(r"^[\w.]+(Error|Exception): ", "", tail[-1])[:160] if tail else f"exit {proc.returncode}"


# --- the Mac's state, each a seam the sandbox tests replace ---------------------------------

INSPECT = r"""
import json
from pathlib import Path
from agent_annotate import __version__, cli, deployment, store, version_guard
from agent_annotate.consolidate import inactive
from agent_annotate.paths import CONFIG_DIR
entries, pages = cli._registry_entries(), []
for project, slug, record in entries:
    if inactive(record):
        continue
    record = {**record, "project": project}
    row = {"project": project, "slug": slug, "port": record.get("port"), "base": record.get("public_base_path") or ""}
    directory = record.get("slug_dir")
    row["backend"] = store.backend(directory) if directory else "json"
    comments = Path(directory or "") / "comments.json"
    row["bytes"] = comments.stat().st_size if comments.is_file() else 0
    try:
        row["action"] = "restart" if deployment._identity(record)["pid"] else "not running"
    except Exception as exc:
        row["action"] = str(exc)
    pages.append(row)
for server in version_guard._unregistered_servers([r for _p, _s, r in entries]):
    pages.append({"project": None, "slug": server["slug"], "port": server["port"], "action": "unregistered"})
installs = CONFIG_DIR / "skill-installs.json"
skills = sorted(json.loads(installs.read_text())) if installs.is_file() else []
print(json.dumps({"version": __version__, "pages": pages, "skills": skills}))
"""

RESTART = ("import json, sys; from agent_annotate.deployment import restart_record; "
           "print(json.dumps(restart_record(sys.argv[1], sys.argv[2], "
           "**(json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})), default=str))")


def inspect():
    if not PYTHON.exists():
        raise Failed("plan", f"agent-annotate is not installed as a uv tool ({PYTHON})")
    proc = run([PYTHON, "-I", "-c", INSPECT], timeout=120, step="plan")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def free_bytes():
    return shutil.disk_usage(Path.home()).free


def install(url):
    run(["uv", "tool", "install", "--python", "3.12", "--force", f"agent-annotate[mcp] @ {url}"], step="install")


def sync_skills():
    run([PYTHON, "-I", "-m", "agent_annotate.cli", "sync-skills"], timeout=120, step="skills")


def restart(project, slug, **options):
    proc = run([PYTHON, "-I", "-c", RESTART, project, slug, json.dumps(options)], timeout=600)
    if proc.returncode:
        raise Failed(f"restart {slug}", last_line(proc))
    return json.loads(proc.stdout.strip().splitlines()[-1])


def disable_databases(pages):
    for project, slug, _port, _base in pages:
        run([PYTHON, "-I", "-m", "agent_annotate.cli", "db", "off", f"{project}/{slug}"],
            timeout=600, step=f"db off {slug}")


def doctor():
    proc = run([PYTHON, "-I", "-m", "agent_annotate.cli", "doctor", "--versions", "--json"], timeout=300)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise Failed("check", "doctor --versions printed no JSON")


def capabilities(port, base):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{base}/api/capabilities", timeout=5) as response:
        return json.loads(response.read(1024 * 1024))


# --- plan, apply, rollback --------------------------------------------------------------------

def plan(mac, target):
    info = inspect()
    restarts = [p for p in info["pages"] if p["action"] == "restart"]
    skips = [p for p in info["pages"] if p["action"] != "restart"]
    reasons = collections.Counter(REASONS.get(p["action"], p["action"]) for p in skips)
    why = ", ".join(r if len(reasons) == 1 else f"{n} {r}" for r, n in reasons.items())
    problem = None
    if vtuple(target) < vtuple(info["version"]):
        problem = f"{target} is older than installed {info['version']}; use rollback"
    else:
        try:
            sums = fetch(asset_url(target, "SHA256SUMS")).decode()
            if wheel_name(target) not in sums:
                problem = f"v{target} SHA256SUMS lists no wheel"
        except OSError as exc:
            problem = f"release v{target} not found ({exc})"
    line = (f"{mac} {info['version']} → {target} · {len(info['pages'])} pages: {len(restarts)} restart, "
            f"{len(skips)} skip" + (f" ({why})" if skips else "") + f" · {len(info['skills'])} skill dirs · "
            + ("ready" if problem is None else f"not ready: {problem}"))
    return {**info, "restarts": restarts, "skips": skips, "problem": problem, "line": line}


def preflight(target):
    sums = fetch(asset_url(target, "SHA256SUMS")).decode()
    digest = next((line.split()[0] for line in sums.splitlines()
                   if line.split()[1:] in ([wheel_name(target)], ["*" + wheel_name(target)])), None)
    if not digest:
        raise Failed("preflight", f"SHA256SUMS lists no {wheel_name(target)}")
    if hashlib.sha256(fetch(asset_url(target, wheel_name(target)))).hexdigest() != digest:
        raise Failed("preflight", "wheel SHA256 does not match SHA256SUMS")
    if free_bytes() < MIN_FREE:
        raise Failed("preflight", f"{free_bytes() / 1024 ** 3:.1f} GiB free, need 2")


def backup(info):
    folder = HOME / f"{info['version']}-{time.strftime('%Y%m%dT%H%M%S')}"
    folder.mkdir(parents=True)
    skills = [str(Path(p).resolve()) for p in info["skills"] if Path(p).is_dir()]
    with tarfile.open(folder / "skills.tar.gz", "w:gz") as tar:
        for i, path in enumerate(skills):
            tar.add(path, arcname=str(i))
    record = {"version": info["version"], "wheel_url": asset_url(info["version"], wheel_name(info["version"])),
              "skills": skills, "pages": [[p["project"], p["slug"], p["port"], p["base"]] for p in info["restarts"]]}
    if info.get("page_db"):
        record["page_db"] = True
    (folder / "backup.json").write_text(json.dumps(record, indent=1) + "\n")
    return folder, record


def restore_skills(folder, skills):
    staging = folder / "restore"
    shutil.rmtree(staging, ignore_errors=True)
    with tarfile.open(folder / "skills.tar.gz") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(staging, filter="data")
        else:  # shortcut: pre-3.12 Pythons lack the data filter; the tarball is our own backup
            tar.extractall(staging)
    for i, path in enumerate(skills):
        shutil.rmtree(path, ignore_errors=True)
        shutil.move(str(staging / str(i)), path)
    shutil.rmtree(staging, ignore_errors=True)


def check(version, pages):
    """doctor --versions for launcher, skills and plugin; one loopback capabilities read per page."""
    result = doctor()
    off = [f"{row['kind']} {row['name']}" for row in result.get("components", [])
           if row.get("kind") != "page" and row.get("status") != "SKIP" and row.get("version") != version]
    for _project, slug, port, base in pages:
        try:
            if capabilities(port, base).get("version") != version:
                off.append(f"page {slug}")
        except (OSError, ValueError):
            off.append(f"page {slug} unreachable")
    if off:
        raise Failed("check", "not on " + version + ": " + ", ".join(off[:3]) + (f" +{len(off) - 3}" if len(off) > 3 else ""))


def log(entry):
    HOME.mkdir(parents=True, exist_ok=True)
    entry = {"t": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **entry}
    with (HOME / "log.ndjson").open("a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def restore(folder, record, pages):
    """Old wheel, skills tarball, restart `pages`, check. Returns 'doctor ok' or raises Failed."""
    if record.get("page_db"):
        disable_databases(pages)  # Release N exports current JSON before the old runtime is installed.
    install(record["wheel_url"])
    restore_skills(folder, record["skills"])
    for project, slug, _port, _base in pages:
        restart(project, slug)
    check(record["version"], pages)
    return "doctor ok"


def apply(mac, target, approval, hold_json=(), move_page=None):
    info = plan(mac, target)
    migrate = vtuple(target) >= (2, 30, 0)
    if (hold_json or move_page) and not migrate:
        return 2, f"{mac} refused: page.db rollout needs 2.30.0 or later"
    requested = set(hold_json) | ({move_page} if move_page else set())
    known = {p["slug"] for p in info["pages"]} | {f"{p['project']}/{p['slug']}" for p in info["pages"]}
    if requested - known:
        return 2, f"{mac} refused: unknown page(s): {', '.join(sorted(requested - known))}"
    if mac == "M1" and not (move_page and move_page.split("/")[-1] == "fld-stack-round8"):
        if any(p["slug"] == "fld-stack-round8" and p.get("backend") != "sqlite" for p in info["pages"]):
            hold_json = [*hold_json, "fld-stack-round8"]
    if migrate:
        info["restarts"].sort(key=lambda p: p.get("bytes", 0))
    if move_page:
        info["restarts"] = [p for p in info["restarts"] if move_page in (p["slug"], f"{p['project']}/{p['slug']}")]
        if len(info["restarts"]) != 1:
            return 2, f"{mac} refused: {move_page} is not one restartable page"
        page = info["restarts"][0]
        if any(held in (page["slug"], f"{page['project']}/{page['slug']}") for held in hold_json):
            return 2, f"{mac} refused: cannot hold and move {move_page}"
    info["page_db"] = migrate
    if info["problem"]:
        return 1, f"{mac} FAILED at preflight ({info['problem']}) · nothing changed"
    old = info["version"]
    try:
        preflight(target)
    except (Failed, OSError) as exc:
        detail = exc.detail if isinstance(exc, Failed) else str(exc)
        return 1, f"{mac} FAILED at preflight ({detail}) · nothing changed"
    folder, record = backup(info)
    touched = []
    json_pages = []
    try:
        install(asset_url(target, wheel_name(target)))
        sync_skills()
        for page in record["pages"]:
            touched.append(page)  # a refused restart still respawns the old argv on the new venv
            if migrate:
                held = page[1] in hold_json or f"{page[0]}/{page[1]}" in hold_json
                result = restart(page[0], page[1], migrate_db=True, hold_json=held, move=bool(move_page))
                storage = result["storage"]
                if storage["backend"] == "json":
                    json_pages.append(f"{page[1]} ({storage['reason']})")
            else:
                restart(page[0], page[1])
        check(target, [] if migrate else record["pages"])  # Each migrated restart already proved its runtime over loopback.
    except Failed as exc:
        try:
            state = f"rolled back to {old} · {restore(folder, record, touched)}"
        except Failed as again:
            state = f"rollback to {old} FAILED at {again.step} ({again.detail}); backup {folder}"
        line = f"{mac} FAILED at {exc.step} ({exc.detail}) · {state}"
        log({"mac": mac, "action": "apply", "from": old, "to": target, "approval": approval,
             "result": "failed", "backup": str(folder), "line": line})
        return 1, line
    line = (f"{mac} {target} ok · {len(record['pages'])} pages restarted · {len(info['skips'])} skipped · "
            f"doctor ok · rollback kept: {old}")
    if migrate:
        json_pages += [f"{p['slug']} ({REASONS.get(p['action'], p['action'])})" for p in info["skips"]]
        line += " · JSON: " + (", ".join(json_pages) or "none")
    log({"mac": mac, "action": "apply", "from": old, "to": target, "approval": approval,
         "result": "ok", "backup": str(folder), "line": line})
    return 0, line


def entries():
    try:
        return [json.loads(line) for line in (HOME / "log.ndjson").read_text().splitlines() if line.strip()]
    except (OSError, ValueError):
        return []


def rollback(mac, approval):
    last = next((e for e in reversed(entries()) if e.get("mac") == mac and e.get("action") == "apply"
                 and e.get("result") == "ok" and e.get("backup")), None)
    if last is None:
        return 1, f"{mac} FAILED at rollback (no successful apply logged here)"
    folder = Path(last["backup"])
    record = json.loads((folder / "backup.json").read_text())
    try:
        state = restore(folder, record, record["pages"])
    except Failed as exc:
        line = f"{mac} FAILED at rollback {exc.step} ({exc.detail})"
        log({"mac": mac, "action": "rollback", "to": record["version"], "approval": approval,
             "result": "failed", "line": line})
        return 1, line
    line = f"{mac} back on {record['version']} · {len(record['pages'])} pages restarted · {state}"
    log({"mac": mac, "action": "rollback", "from": last.get("to"), "to": record["version"],
         "approval": approval, "result": "ok", "line": line})
    return 0, line


# --- status and other Macs --------------------------------------------------------------------

def this_mac():
    return os.environ.get("ANNOTATE_ROLLOUT_MAC") or LOCAL_HOSTS.get(socket.gethostname().split(".")[0])


def releases():
    try:
        data = json.loads(fetch(RELEASES_API))
        return sorted({vtuple(r["tag_name"]) for r in data if not r.get("draft") and not r.get("prerelease")})
    except (OSError, ValueError, KeyError, TypeError, SystemExit):
        return []


def status():
    known, local = releases(), this_mac()
    parts = []
    for mac in ENVIRONMENTS:
        ok = True
        if mac == local:
            result = doctor()
            version, ok = (result.get("release") or {}).get("version"), result.get("ok")
        else:
            last = next((e for e in reversed(entries()) if e.get("mac") == mac and e.get("version")), None)
            version = last and last["version"]
        if not version:
            parts.append(f"{mac} unknown")
            continue
        behind = sum(1 for v in known if v > vtuple(version))
        parts.append(f"{mac} {version} " + (f"({behind} behind)" if behind else "ok" if ok else "(doctor not ok)"))
    return 0, " · ".join(parts)


def remote(mac, command, version, approval, worktree, hold_json=(), move_page=None):
    """Run `rollout.py COMMAND --local` on another Mac in an Orca terminal; print its line."""
    if not approval:
        return 2, f"refused: {mac} needs Chang's yes · ask on the page, then add --approval \"card #N\""
    if any(c in approval for c in "$`\n\r"):
        return 2, "refused: --approval text may not contain $, backticks or newlines"
    worktree = worktree or WORKTREES.get(mac)
    if not worktree:
        return 2, f"refused: {mac} needs --worktree (an Orca worktree selector on that Mac)"
    folder = "~/.local/share/annotate-rollout"
    marker = "ROLLOUT-END-" + uuid.uuid4().hex[:12]
    script = f"python3 -I {folder}/rollout.py {command}" + (f" {version}" if version else "")
    for slug in hold_json:
        script += " --hold-json " + shlex.quote(slug)
    if move_page:
        script += " --move-page " + shlex.quote(move_page)
    fetch_step = ""
    if version:
        fetch_step = (f"mkdir -p {folder}/v{version} && cd {folder}/v{version} && "
                      f"curl -fsSLO {RELEASES}/v{version}/rollout.py && curl -fsSLO {RELEASES}/v{version}/SHA256SUMS && "
                      f"grep -F '  rollout.py' SHA256SUMS | shasum -a 256 -c - && cp rollout.py ../rollout.py && ")
    # The marker is split in the typed text, so only the echo's output matches it exactly.
    text = (f"{fetch_step}{script} --mac {mac} --local --approval {shlex.quote(approval)}; "
            f"echo {marker[:7]}\"\"{marker[7:]}")
    assert "$" not in text and "\n" not in text  # nothing may expand on this side or break the line
    orca = ["orca", "--environment", ENVIRONMENTS[mac], "terminal"]
    proc = run([*orca, "create", "--worktree", worktree, "--title", "annotate rollout", "--command", text, "--json"])
    handle = _find(json.loads(proc.stdout or "{}"), "handle") if proc.returncode == 0 else None
    if not handle:
        return 1, f"{mac} FAILED at remote terminal ({(proc.stderr or proc.stdout).strip()[:160]})"
    deadline, tail = time.time() + REMOTE_TIMEOUT, []
    while time.time() < deadline:
        read = run([*orca, "read", "--terminal", handle, "--limit", "400", "--json"], timeout=60)
        try:
            tail = (_find(json.loads(read.stdout), "terminal") or {}).get("tail") or []
        except ValueError:
            tail = []
        if any(line.strip() == marker for line in tail):
            break
        time.sleep(5)
    else:
        return 1, f"{mac} FAILED at remote wait (no result in {REMOTE_TIMEOUT // 60} min; terminal {handle})"
    before = [line.strip() for line in tail[:[line.strip() for line in tail].index(marker)]]
    line = next((x for x in reversed(before) if x.startswith((f"{mac} ", "refused"))),
                f"{mac} FAILED at remote (no result line; terminal {handle})")
    code = 0 if line.startswith(f"{mac} ") and " FAILED " not in line and "not ready" not in line else 1
    version_now = (version if command == "apply" and code == 0 else
                   line.split()[3] if command == "rollback" and code == 0 else None)
    log({"mac": mac, "action": command, "remote": True, "approval": approval, "terminal": handle,
         "result": "ok" if code == 0 else "failed", "line": line,
         **({"version": version_now} if version_now else {})})
    if code == 0:
        run([*orca, "close", "--terminal", handle], timeout=60)
    return code, line


def _find(data, key):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        data = list(data.values())
    if isinstance(data, list):
        for item in data:
            found = _find(item, key)
            if found is not None:
                return found
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("plan", "apply", "rollback", "status"))
    parser.add_argument("version", nargs="?")
    parser.add_argument("--mac", choices=sorted(ENVIRONMENTS))
    parser.add_argument("--approval", default="", help="Chang's yes, e.g. \"card #212\"; required for another Mac")
    parser.add_argument("--local", action="store_true", help="run here (what the remote side receives)")
    parser.add_argument("--worktree", help="Orca worktree selector on the other Mac")
    parser.add_argument("--hold-json", action="append", default=[], metavar="SLUG",
                        help="keep this page on JSON until --move-page (repeatable)")
    parser.add_argument("--move-page", metavar="SLUG", help="migrate only this held page on a later apply")
    args = parser.parse_args(argv)
    if (args.hold_json or args.move_page) and args.command != "apply":
        parser.error("--hold-json and --move-page apply only to apply")
    if any(c in slug for slug in [*args.hold_json, args.move_page or ""] for c in "$`\n\r"):
        parser.error("page names may not contain $, backticks or newlines")
    if args.command == "status":
        code, line = status()
        print(line)
        return code
    if not args.mac or (args.command != "rollback") != bool(args.version):
        parser.error("plan and apply take VERSION and --mac; rollback takes --mac")
    if args.version:
        vtuple(args.version)
    here = this_mac()
    if args.local and here and here != args.mac:
        print(f"refused: this Mac is {here}, not {args.mac}")
        return 2
    if not args.local and args.mac != here:
        code, line = remote(args.mac, args.command, args.version, args.approval, args.worktree,
                            args.hold_json, args.move_page)
    elif os.environ.get("UV_TOOL_DIR") and not os.environ.get("UV_TOOL_BIN_DIR"):
        code, line = 2, "refused: UV_TOOL_DIR without UV_TOOL_BIN_DIR would replace the live annotate launcher"
    elif args.command == "plan":
        try:
            info = plan(args.mac, args.version)
            code, line = (0 if info["problem"] is None else 1), info["line"]
        except Failed as exc:
            code, line = 1, f"{args.mac} FAILED at {exc.step} ({exc.detail})"
    elif args.command == "apply":
        code, line = apply(args.mac, args.version, args.approval, args.hold_json, args.move_page)
    else:
        code, line = rollback(args.mac, args.approval)
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
