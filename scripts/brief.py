#!/usr/bin/env python3
"""Print the standard worker brief for a bead; the coordinator adds only the task delta.

  brief.py BEAD --run RUN [--base BRANCH] [--branch NAME] [--delta TEXT | --delta-file PATH]

Pipe or save the output and start the worker with
`orca orchestration worker-start --spec-file BRIEF ...`.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

LEASE = Path(__file__).resolve().parent / "lease.py"

RULES = """\
Rules:
- Claim {bead} (`bd update {bead} --claim`) and close it with proof when done; create no other beads.
- Bash: one command per call. Read the section you need, not whole files or logs.
- Mail: send no progress notes; Orca already tracks you. Anything that needs an answer is
  `orca orchestration ask`. A note that needs a reply goes as `--type status --priority high`.
- Ports, CI slots and disk: take a lease yourself instead of asking for a GO:
  `python3 {lease} take NAME --run {run} --note WHY` (refused = held; only then ask).
  Release before worker_done: `python3 {lease} release --run {run}`.
- Sandbox servers use ports 18700-18799 only. No live page writes; no other Macs.
- full suite: M1Max16 posts it as the "full-suite" status on every PR head; don't run it
  locally. To rerun it: scripts/ci.py --full → read the receipt line.
- worker_done --body is three sentences: what changed where, the evidence, what is left
  (PR URL if any). Use --outcome failed if the work is not done."""


def bead_record(bead):
    proc = subprocess.run(["bd", "show", bead, "--json"], capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        raise SystemExit(f"brief.py: bd show {bead} failed: {(proc.stderr or proc.stdout).strip()[:200]}")
    return data[0] if isinstance(data, list) else data


def render(record, run, base, branch, delta):
    bead = record["id"]
    lines = [f"Bead {bead}: {record.get('title', '')}", "", (record.get("description") or "").strip()]
    if record.get("acceptance_criteria"):
        lines += ["", "Done when: " + record["acceptance_criteria"].strip()]
    if base:
        work = f"Base origin/{base}; work on branch {branch or 'a new branch'}; open a PR against {base} (do not merge)."
        lines += ["", work]
    if delta:
        lines += ["", delta.strip()]
    lines += ["", RULES.format(bead=bead, run=run, lease=LEASE)]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bead")
    parser.add_argument("--run", required=True)
    parser.add_argument("--base")
    parser.add_argument("--branch")
    parser.add_argument("--delta", help="Task-specific lines")
    parser.add_argument("--delta-file")
    args = parser.parse_args(argv)
    delta = Path(args.delta_file).read_text() if args.delta_file else args.delta
    print(render(bead_record(args.bead), args.run, args.base, args.branch, delta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
