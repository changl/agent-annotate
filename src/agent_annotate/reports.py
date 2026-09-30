"""A short weekly page from local usage evidence, without an agent run."""

from __future__ import annotations

import datetime as dt
import json
import statistics
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlsplit, urlunsplit

from . import cli, costs
from .pagegen import _publish_namespace, generate


def _cost_summary(rows: list[dict]) -> dict:
    calls = [r for r in rows if r["kind"] == "cli"]
    rounds = costs.rounds(rows)
    return {"calls": len(calls), "failures": sum(bool(r["failed"]) for r in calls),
            "rounds": len(rounds), "output_tokens": sum(r["out_tokens"] for r in rows),
            "median_round_tokens": statistics.median([sum(r["out_tokens"] for r in rd) for rd in rounds]) if rounds else None}


def _markdown_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe="/%:@!$&'*=+-._~"), "", ""))


def report_source(metrics: dict, previous: dict, agent_cost: dict, date: str, fleet: dict | None = None) -> str:
    current = metrics["global"]
    prior = previous["global"]
    counts = ["submitted_rounds", "reviewer_decisions", "publish_successes", "publish_failures"]
    lines = ["---", "title: Agent-annotate weekly progress", f"date: {date}",
             "full_plan: true", "other_files_required: none", "---", "",
             "## Review loop", "",
             "This page combines local review events with agent usage. Delivery acceptance and owner receipt are separate from completed work.", "",
             "| Measure | Last 7 days | Previous 7 days |", "|---|---|---|"]
    for key in counts:
        lines.append(f"| {key.replace('_', ' ').capitalize()} | {current.get(key, 0)} | {prior.get(key, 0)} |")
    lines += ["", "## Feedback delivery", "", "| State | Rounds |", "|---|---|"]
    for key, value in current.get("deliveries", {}).items():
        lines.append(f"| {key.replace('_', ' ')} | {value} |")
    lines += ["", "Only Finish review queues an automatic owner prompt. Individual answers remain drafts until submission. Pending and uncertain delivery need owner or runtime attention.",
              "", "## Agent cost", "", f"{agent_cost['calls']} CLI calls; {agent_cost['failures']} failed calls; {agent_cost['rounds']} closed authoring rounds; {agent_cost['output_tokens']:,} attributed output tokens.", ""]
    if agent_cost["median_round_tokens"] is not None:
        lines.append(f"Median output tokens per closed authoring round: {agent_cost['median_round_tokens']:,.0f}.")
    else:
        lines.append("No completed authoring rounds in this window; no median can be inferred.")
    quality = current.get("decision_quality", {})
    lines += ["", "## Improvement queue", "",
              f"Current estate: {current.get('active_pages', 0)} registered pages. {quality.get('cards_with_warnings', 0)} cards need usable choice controls.",
              "", "Priorities: investigate delivery backlog, migrate legacy runtime forks, keep hosted project links current, and compare future changes against this baseline.",
              "", "## Measurement limits", "",
              "This report covers this machine's registry and transcripts, not every remote host. Output-token attribution is an estimate from existing transcripts. Browser load time, resource opens, and completed implementation are not inferred from a prompt receipt.",
              "", "## Feedback carried forward", "",
              "Feedback on earlier reports remains open for the project owner; generating a new report does not resolve it.", ""]
    if fleet is not None:
        lines += ["", "## Fleet runtime and delivery coverage", ""]
        if "summary" not in fleet:
            lines += ["Fleet collection is unavailable. Reconcile the configured inventory; missing observations are not zero activity."]
        else:
            summary = fleet["summary"]
            lines += [f"{summary['total']} configured page URLs across {len(summary['by_machine'])} machine labels; "
                      f"{summary['healthy']} healthy API observations, {summary['degraded']} degraded and {summary['unreachable']} unreachable.",
                      "", "| Machine label | Project / page | Runtime | Owner metadata | Latest delivery | API health |",
                      "|---|---|---|---|---|---|"]
            for row in fleet["targets"]:
                owner = "present" if row["owner_present"] is True else "absent" if row["owner_present"] is False else "unknown"
                lines.append(f"| {row['machine']} | [{row['project']}/{row['slug']}]({_markdown_url(row['url'])}) | "
                             f"{row['package_version'] or 'unknown'} | {owner} | {row['latest_delivery_state']} | {row['health']} |")
            lines += ["", "```details", "Fleet measurement limits", *[f"- {limit}" for limit in fleet["limitations"]], "```"]
    return "\n".join(lines)


def write_report(slug_dir: Path, now: dt.datetime | None = None) -> dict:
    from .metrics import collect_metrics
    now = now or dt.datetime.now(dt.UTC)
    since = now - dt.timedelta(days=7)
    current = collect_metrics(since, now)
    previous = collect_metrics(since - dt.timedelta(days=7), since)
    rows = costs.collect(SimpleNamespace(since=since.date().isoformat(), root=None, codex=True,
                                         codex_root=None, include_dev=False))
    rows = [r for r in rows if r.get("ts") and since <= costs._when(r["ts"]) < now]
    cost = _cost_summary(rows)
    fleet = None
    if (cli.CONFIG_DIR / "fleet.json").exists():
        try:
            fleet = cli._fleet_snapshot()
        except (OSError, ValueError):
            fleet = {"error": "inventory_unavailable"}
    slug_dir = Path(slug_dir)
    meta = cli._read_meta(slug_dir)
    version = f"v{max([int(h['version'][1:]) for h in meta.get('history', []) if h.get('version', '').startswith('v') and h['version'][1:].isdigit()] or [0]) + 1}"
    slug_dir.mkdir(parents=True, exist_ok=True)
    source = slug_dir / "weekly-source.md"
    source.write_text(report_source(current, previous, cost, now.date().isoformat(), fleet))
    result = generate(source, slug_dir, version, f"Week ending {now.date().isoformat()}")
    # Aggregate evidence only; no reviewer text or transcript fragments copied.
    (slug_dir / "metrics.json").write_text(json.dumps({"current": current, "previous": previous, "agent_cost": cost, "fleet": fleet}, indent=2))
    return result


def cmd_report(args) -> int:
    directory = Path(args.slug_dir).expanduser().resolve()
    if getattr(args, "uninstall", False):
        import os
        path = cli.LAUNCH_AGENTS_DIR / "com.agent-annotate.weekly-report.plist"
        cli._launchctl("bootout", f"gui/{os.getuid()}/com.agent-annotate.weekly-report")
        path.unlink(missing_ok=True)
        print("Weekly report schedule removed; report history preserved")
        return 0
    state = cli._load_state_for_project(args.project)
    record = state.get("slugs", {}).get(directory.name)
    if record and Path(record.get("slug_dir", "")).resolve() != directory:
        print("ERROR: report slug is registered to another directory; no report or feedback changed")
        return 1
    if args.install:
        import os
        import plistlib
        import shutil
        import sys
        if sys.platform != "darwin":
            print("ERROR: built-in weekly scheduling requires macOS; run report through your existing scheduler")
            return 1
        if not record or record.get("owner_session") in (None, "unknown"):
            print("ERROR: publish this report from its owning session before scheduling it")
            return 1
        path = cli.LAUNCH_AGENTS_DIR / "com.agent-annotate.weekly-report.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        cli.LOG_DIR.mkdir(parents=True, exist_ok=True)
        command = shutil.which("annotate") or str(cli.SHIM_PATH)
        path.write_bytes(plistlib.dumps({"Label": "com.agent-annotate.weekly-report",
            "ProgramArguments": [command, "report", str(directory), "--publish", "--project", args.project],
            "StartCalendarInterval": {"Weekday": 1, "Hour": 9, "Minute": 0},
            "AbandonProcessGroup": True,
            "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            "StandardOutPath": str(cli.LOG_DIR / "weekly-report.log"),
            "StandardErrorPath": str(cli.LOG_DIR / "weekly-report.log")}))
        domain = f"gui/{os.getuid()}"
        cli._launchctl("bootout", f"{domain}/com.agent-annotate.weekly-report")
        result = cli._launchctl("bootstrap", domain, str(path))
        if result.returncode:
            print(f"ERROR: weekly report schedule: {result.stderr}")
            return 1
        print(f"Weekly report scheduled Mondays 09:00 local: {directory}")
        return 0
    result = write_report(directory)
    if not args.publish:
        print(result["html"])
        return 0
    if record:
        if not cli._is_process_alive(record.get("pid", 0)):
            outcome, detail = cli._revive_one(args.project, directory.name, cli._running_servers(), False, cli._live_tailnet_host())
            if outcome not in ("alive", "revived", "adopted", "rerouted"):
                print(f"ERROR: weekly report revival: {detail}")
                return 1
            record = cli._load_state_for_project(args.project)["slugs"][directory.name]
        for blocker in cli._carryover_blockers(directory, result["version"]):
            if blocker["reason"] != "no resolution or carry-forward":
                continue
            code, body = cli._api(record, "PUT", f"/api/comments/{blocker['id']}",
                {"carry_forward": {"version": result["version"], "anchor_id": "s:feedback-carried-forward"}},
                "agent:weekly-report")
            if not 200 <= code < 300:
                print(f"ERROR: weekly report feedback carry: {body}")
                return 1
        code = cli.cmd_publish_version(SimpleNamespace(slug_dir=str(directory), version=result["version"],
                                                       label=result["label"], project=args.project))
        if code:
            return code
        return cli._publish_already_running(args.project, directory.name, directory, record,
                                             _publish_namespace(directory, args))
    return cli.cmd_publish(_publish_namespace(directory, args))
