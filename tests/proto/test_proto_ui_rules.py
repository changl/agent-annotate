"""Round-12 Running, History and Pages & links fixes: the hour chart's data, plus source checks for the broken
items that live in the browser code (no JS test runner in this repo)."""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_annotate.proto_data import running as R

WEB = Path(R.__file__).resolve().parents[1] / "web" / "proto"
js = lambda n: (WEB / n).read_text()


def test_hours_counts_this_projects_workers_per_hour(monkeypatch):
    now = datetime(2026, 11, 20, 12, 30, tzinfo=timezone.utc)
    iso = lambda h: (now - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db = sqlite3.connect(":memory:")
    db.execute("create table runs (id, objective)")
    db.execute("create table dispatch_contexts (run_id, dispatched_at, completed_at)")
    db.executemany("insert into runs values (?, ?)", [("f", "FLD go-live"), ("o", "Rebex copy")])
    db.executemany("insert into dispatch_contexts values (?, ?, ?)", [
        ("f", iso(2), None),          # still running: counts in the last three hours
        ("f", iso(30), iso(28)),      # ended before the window
        ("o", iso(1), None)])         # another project's worker
    monkeypatch.setattr(R, "_orca_db", lambda: db)
    h = R.hours(now.timestamp())
    assert len(h) == 24 and h[-3:] == [1, 1, 1] and sum(h) == 3


def test_running_chip_keeps_crashed_for_failures_and_calls_silence_blocked():  # #1
    s = js("running.js")
    assert "blocked`, tone: 'orange'" in s and "no sign of life" in s


def test_running_render_drops_a_stale_tab():  # #2: a slow data read never paints Running over another tab
    assert "if (!el.classList.contains('tab-' + tab)) return;" in js("running.js")


def test_chart_tooltip_follows_mouse_and_touch_events():  # #3
    assert "['pointermove', 'mouseover', 'pointerdown']" in js("running.js")


def test_history_lists_every_published_version():  # #4: a version with no Send still opens from the list
    s = js("history.js")
    assert "Object.keys(D.versions)" in s and "no answers sent" in s


def test_picture_sizes_are_a_share_of_the_column():  # #5: 25% on a phone is a quarter of the column
    s = js("history.js")
    assert "img.style.width = pct ? `${pct}%` : ''" in s and "naturalWidth || img.width) * pct" not in s
