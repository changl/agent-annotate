"""Only agent_annotate/store.py writes a page's record files.

Runs the write-heavy test modules again in a child pytest with a guard
(tests/write_guard/sitecustomize.py) loaded into every Python process, the
child's servers and CLI calls included. Any record-file write whose stack
has an agent_annotate frame but no store.py frame is logged; the log must
stay empty.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITERS = [
    "test_fast_writes.py", "test_decision_api.py", "test_categories_api.py", "test_plan_topics.py",
    "test_project_state.py", "test_delivery.py", "test_publish_version.py", "test_pagegen.py",
    "test_review_history.py", "test_page_names.py", "test_explicit_send.py", "test_meta_stamp_safety.py",
    "test_close_retire.py", "test_consolidate.py", "test_plans_backfill.py", "test_ask_numbers.py",
    "test_delete_comment.py", "test_copy_api.py",
]


def test_only_store_writes_record_files(tmp_path):
    log = tmp_path / "violations.log"
    log.touch()
    env = {**os.environ, "ANNOTATE_WRITE_GUARD": str(log),
           "PYTHONPATH": os.pathsep.join([str(ROOT / "tests" / "write_guard"), str(ROOT / "src"),
                                          os.environ.get("PYTHONPATH", "")])}
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x",
                           *(str(ROOT / "tests" / name) for name in WRITERS)],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    assert log.read_text() == ""


def test_guard_catches_a_direct_write(tmp_path):
    log = tmp_path / "violations.log"
    page = tmp_path / "page"
    page.mkdir()
    script = ("import json, pathlib, sys\n"
              "sys.modules[__name__].__file__ = 'x'\n"
              "from agent_annotate import store\n"
              f"store.write_json(pathlib.Path({str(page)!r}) / 'comments.json', {{}})\n"
              "exec(compile('open(sys.argv[1], \"w\").write(\"{}\")', '/fake/agent_annotate/cli.py', 'exec'))\n")
    env = {**os.environ, "ANNOTATE_WRITE_GUARD": str(log),
           "PYTHONPATH": os.pathsep.join([str(ROOT / "tests" / "write_guard"), str(ROOT / "src")])}
    subprocess.run([sys.executable, "-c", script, str(page / "seen.json")], env=env, check=True, timeout=60)
    lines = log.read_text().splitlines()
    assert len(lines) == 1 and lines[0].startswith(f"open {page / 'seen.json'} from cli.py:1")
