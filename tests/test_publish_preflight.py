"""Two silent publish failures that produced a page nobody could use.

1. `ln -sf v1.html ../current.html` run from inside versions/ makes a link
   whose target resolves against the SLUG dir, not versions/. It dangles. The
   only thing publish ever said was
   "JS lint: skipped (no current.html found yet)" and the page 404'd.
2. Without a history entry in current.meta.json the version rail renders
   "No versions found" — a page that reads as broken while every byte of its
   content is being served correctly.

Both are now repaired by publish, or refused loudly when the intent is
genuinely ambiguous.
"""

import json
import os
from pathlib import Path

from agent_annotate import cli


def _slug(tmp_path, versions=("v1",)):
    slug_dir = tmp_path / "demo"
    (slug_dir / "versions").mkdir(parents=True)
    for v in versions:
        (slug_dir / "versions" / f"{v}.html").write_text(
            f"<html><body><p data-anchor-id='s:{v}'>{v}</p></body></html>", encoding="utf-8"
        )
    return slug_dir


def test_dangling_relative_symlink_is_repaired_to_versions(tmp_path):
    slug_dir = _slug(tmp_path)
    # Exactly what `cd versions && ln -sf v1.html ../current.html` produces.
    (slug_dir / "current.html").symlink_to("v1.html")
    assert not (slug_dir / "current.html").exists()  # dangling

    version, notes = cli._ensure_current_symlink(slug_dir)

    assert version == "v1"
    assert os.readlink(slug_dir / "current.html") == "versions/v1.html"
    assert (slug_dir / "current.html").exists()
    assert any("versions/v1.html" in n for n in notes)


def test_missing_symlink_with_one_version_is_created(tmp_path):
    slug_dir = _slug(tmp_path)
    version, notes = cli._ensure_current_symlink(slug_dir)
    assert version == "v1"
    assert os.readlink(slug_dir / "current.html") == "versions/v1.html"


def test_missing_symlink_uses_the_version_named_by_meta(tmp_path):
    slug_dir = _slug(tmp_path, versions=("v1", "v2", "v3"))
    (slug_dir / "current.meta.json").write_text(json.dumps({"current": "v2"}))

    version, _ = cli._ensure_current_symlink(slug_dir)

    assert version == "v2"
    assert os.readlink(slug_dir / "current.html") == "versions/v2.html"


def test_ambiguous_missing_symlink_refuses_rather_than_picking(tmp_path):
    """Guessing between three versions would publish the wrong document."""
    slug_dir = _slug(tmp_path, versions=("v1", "v2", "v3"))
    version, notes = cli._ensure_current_symlink(slug_dir)

    assert version is None
    assert not (slug_dir / "current.html").exists()
    assert any("publish-version" in n for n in notes)
    assert any("v1, v2, v3" in n for n in notes)


def test_dangling_link_wins_over_an_ambiguous_version_set(tmp_path):
    """The broken link still records which version was intended."""
    slug_dir = _slug(tmp_path, versions=("v1", "v2", "v3"))
    (slug_dir / "current.html").symlink_to("v3.html")

    version, _ = cli._ensure_current_symlink(slug_dir)

    assert version == "v3"
    assert os.readlink(slug_dir / "current.html") == "versions/v3.html"


def test_a_correct_symlink_is_left_alone(tmp_path):
    slug_dir = _slug(tmp_path, versions=("v1", "v2"))
    (slug_dir / "current.html").symlink_to(Path("versions") / "v2.html")

    version, notes = cli._ensure_current_symlink(slug_dir)

    assert version == "v2"
    assert notes == []
    assert os.readlink(slug_dir / "current.html") == "versions/v2.html"


def test_a_plain_file_current_html_is_left_alone(tmp_path):
    slug_dir = _slug(tmp_path)
    (slug_dir / "current.html").write_text("<html>hand-written</html>")
    version, notes = cli._ensure_current_symlink(slug_dir)
    assert notes == []
    assert not (slug_dir / "current.html").is_symlink()


def test_no_versions_is_not_publishable(tmp_path):
    slug_dir = tmp_path / "demo"
    slug_dir.mkdir()
    version, notes = cli._ensure_current_symlink(slug_dir)
    assert version is None
    assert "nothing to publish" in notes[0]


# ── current.meta.json history ───────────────────────────────────────────────

def test_missing_meta_gets_current_and_history(tmp_path):
    slug_dir = _slug(tmp_path)
    notes = cli._ensure_meta_history(slug_dir, "v1")

    meta = json.loads((slug_dir / "current.meta.json").read_text())
    assert meta["current"] == "v1"
    assert [h["version"] for h in meta["history"]] == ["v1"]
    assert notes


def test_meta_with_stamps_but_no_history_keeps_the_stamps(tmp_path):
    """The sync server caches content_stamps here while it runs. Registering
    the version must not drop them."""
    slug_dir = _slug(tmp_path)
    (slug_dir / "current.meta.json").write_text(json.dumps({
        "content_stamps": {"v1": {"whole": "abc", "_mtime": 1.0}},
    }))

    cli._ensure_meta_history(slug_dir, "v1")

    meta = json.loads((slug_dir / "current.meta.json").read_text())
    assert meta["content_stamps"]["v1"]["whole"] == "abc"
    assert meta["current"] == "v1"
    assert [h["version"] for h in meta["history"]] == ["v1"]


def test_existing_history_is_not_duplicated(tmp_path):
    slug_dir = _slug(tmp_path)
    (slug_dir / "current.meta.json").write_text(json.dumps({
        "current": "v1",
        "history": [{"version": "v1", "ts": "2026-01-01T00:00:00Z", "label": "first"}],
    }))

    notes = cli._ensure_meta_history(slug_dir, "v1")

    meta = json.loads((slug_dir / "current.meta.json").read_text())
    assert len(meta["history"]) == 1
    assert meta["history"][0]["label"] == "first"
    assert notes == []


def test_unparseable_meta_is_rebuilt_rather_than_crashing_publish(tmp_path):
    slug_dir = _slug(tmp_path)
    (slug_dir / "current.meta.json").write_text("{ not json")

    cli._ensure_meta_history(slug_dir, "v1")

    meta = json.loads((slug_dir / "current.meta.json").read_text())
    assert meta["current"] == "v1"
    assert [h["version"] for h in meta["history"]] == ["v1"]
