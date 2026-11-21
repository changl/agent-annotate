"""Eleventh check: an unread board is never zero tasks, and Pages & links re-reads its list on every return."""
import time
from pathlib import Path

import pytest

from agent_annotate.proto_data import running as R

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
RUN, LINKS = ((WEB / n).read_text() for n in ("running.js", "links.js"))


def test_a_board_whose_location_did_not_answer_is_an_error_not_zero(tmp_path, monkeypatch):
    """Running 2: the checkout is there but `bd where` failed, so the board is unread, not empty."""
    monkeypatch.setattr(R, "CHECKOUTS", {"fld": tmp_path})
    with pytest.raises(RuntimeError):
        R.board("fld", None)
    assert "error" in R.safe(lambda: R.board("fld", None), None)


def test_an_unread_board_is_read_again_at_once(tmp_path, monkeypatch):
    """Running 2: a cached result with an unread board starts a fresh build on the next read, inside the minute."""
    started = []
    monkeypatch.setattr(R.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda s: started.append(args)})())
    R._behind(tmp_path, (time.time(), {"board": {"error": "RuntimeError: x"}}))
    R._busy.discard(str(tmp_path))
    R._behind(tmp_path, (time.time(), {"board": {"tasks": []}}))
    assert started == [(tmp_path,)]


def test_tasks_never_show_zero_for_an_unread_board():
    """Running 2: an unread board shows a plain line and Try again in place of the counts."""
    assert "board could not be read just now. <button class=\"btn sm\" data-reread>Try again</button>" in RUN
    assert "if (t.hasAttribute('data-reread')) return reread(t);" in RUN


def test_links_rereads_on_every_return():
    """Frame 4, running 4: no throttle on the fresh read when the tab opens."""
    assert "readAt" not in LINKS and "ctx.data('links', true).then(F =>" in LINKS
