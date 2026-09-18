"""`publish-version` keeps history as a set keyed on version.

Every version of every observed live page was listed twice: `publish`
registered it through the meta repair and a later `publish-version` for the
same vN appended a second entry, as did any re-run.
"""

import json
from types import SimpleNamespace

from agent_annotate import cli


def _slug(tmp_path):
    slug_dir = tmp_path / "proj" / "demo"
    (slug_dir / "versions").mkdir(parents=True)
    for v in ("v1", "v2"):
        (slug_dir / "versions" / f"{v}.html").write_text(f"<html><p data-anchor-id='s:{v}'>{v}</p></html>")
    (slug_dir / "current.html").symlink_to("versions/v1.html")
    (slug_dir / "current.meta.json").write_text(json.dumps({
        "current": "v1",
        "history": [{"version": "v1", "ts": "2026-09-01T00:00:00Z", "label": "initial"}],
        "content_stamps": {"v1": {"whole": "abc"}},
    }))
    return slug_dir


def _args(slug_dir, version, label=None):
    return SimpleNamespace(slug_dir=str(slug_dir), version=version, label=label, project=None)


def test_repeat_calls_update_in_place(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_registry_entries", lambda: [])
    slug_dir = _slug(tmp_path)

    assert cli.cmd_publish_version(_args(slug_dir, "v2", "round 2")) == 0
    assert "added v2" in capsys.readouterr().out
    assert cli.cmd_publish_version(_args(slug_dir, "v2", "round 2, again")) == 0
    assert "updated in place" in capsys.readouterr().out

    meta = json.loads((slug_dir / "current.meta.json").read_text())
    assert meta["current"] == "v2"
    assert [h["version"] for h in meta["history"]] == ["v1", "v2"]
    assert meta["history"][1]["label"] == "round 2, again"
    assert meta["content_stamps"]["v1"]["whole"] == "abc"   # server cache survives
    assert (slug_dir / "current.html").resolve().name == "v2.html"

    bus = cli.BUS_ROOT / "proj" / "demo.ndjson"
    events = [json.loads(line) for line in bus.read_text().splitlines()]
    assert [e["event"] for e in events] == ["version_published", "version_published"]
    assert events[0]["version"] == "v2" and events[0]["label"] == "round 2"


def test_missing_version_file_is_refused(tmp_path, capsys):
    slug_dir = _slug(tmp_path)
    assert cli.cmd_publish_version(_args(slug_dir, "v9")) == 2
    assert "versions/v9.html not found" in capsys.readouterr().err
    meta = json.loads((slug_dir / "current.meta.json").read_text())
    assert meta["current"] == "v1"


def test_publish_then_publish_version_for_the_same_version_is_one_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_registry_entries", lambda: [])
    slug_dir = _slug(tmp_path)
    (slug_dir / "current.meta.json").unlink()
    (slug_dir / "current.html").unlink()
    (slug_dir / "current.html").symlink_to("versions/v2.html")
    assert cli._ensure_meta_history(slug_dir, "v2")
    cli.cmd_publish_version(_args(slug_dir, "v2"))
    meta = json.loads((slug_dir / "current.meta.json").read_text())
    assert [h["version"] for h in meta["history"]] == ["v2"]
