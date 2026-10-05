"""Copy edits append usable formatted proposals without losing approved content."""

import copy
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_annotate.copy_state import (
    StaleRevisionError,
    load_copy,
    propose_copy,
    restore_revision,
    save_copy,
    validate_copy,
    validate_delta,
)


def document():
    return {"schema_version": 1, "blocks": [{"id": "home-hero", "title": "Home hero", "current": "draft-1",
        "revisions": [{"id": "draft-1", "created_at": "2026-10-02T12:00:00Z", "author": {"id": "agent:copy"},
                       "status": "draft", "delta": {"ops": [{"insert": "Rebex", "attributes": {"bold": True}},
                                                            {"insert": "\n"}, {"insert": "Everyday essentials.\n"}]}}]}]}


def test_formatted_proposal_preserves_original_and_retry_identity(tmp_path):
    original = save_copy(tmp_path, document())
    delta = {"ops": [{"insert": "Rebex", "attributes": {"bold": True}}, {"insert": "\n", "attributes": {"header": 2}},
                     {"insert": "Shop", "attributes": {"link": "https://rebex.example/shop"}}, {"insert": "\n"}]}
    request_id = str(uuid.uuid4())
    result = propose_copy(tmp_path, "home-hero", delta, {"id": "reviewer:chang", "name": "Chang"},
                          base_revision="draft-1", request_id=request_id)
    assert result["blocks"][0]["current"] == "draft-1"
    assert result["blocks"][0]["revisions"][0] == original["blocks"][0]["revisions"][0]
    assert result["blocks"][0]["revisions"][1]["delta"] == delta
    assert load_copy(tmp_path) == result
    mtime = (tmp_path / "copy.json").stat().st_mtime_ns
    assert propose_copy(tmp_path, "home-hero", delta, {"id": "reviewer:chang", "name": "Chang Lee"},
                        base_revision="draft-1", request_id=request_id) == result
    assert (tmp_path / "copy.json").stat().st_mtime_ns == mtime
    with pytest.raises(ValueError, match="different proposal"):
        propose_copy(tmp_path, "home-hero", delta, {"id": "reviewer:other"},
                     base_revision="draft-1", request_id=request_id)


def test_simultaneous_proposals_keep_every_author_and_current(tmp_path):
    save_copy(tmp_path, document())
    def propose(index):
        # UI-3: a proposal on a revision that is no longer the latest is refused,
        # so each writer re-reads the latest and tries again; none is lost.
        while True:
            base = load_copy(tmp_path)["blocks"][0]["revisions"][-1]["id"]
            try:
                return propose_copy(tmp_path, "home-hero", {"ops": [{"insert": f"Draft {index}\n"}]},
                                    {"id": f"reviewer:{index}"}, base_revision=base, request_id=str(uuid.uuid4()))
            except StaleRevisionError:
                continue
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(propose, range(24)))
    block = load_copy(tmp_path)["blocks"][0]
    assert block["current"] == "draft-1"
    assert len(block["revisions"]) == 25
    assert {revision["author"]["id"] for revision in block["revisions"][1:]} == {f"reviewer:{index}" for index in range(24)}


@pytest.mark.parametrize("delta", [
    {"ops": [{"insert": {"image": "https://evil.example/image"}}]},
    {"ops": [{"insert": {"formula": "</span><img src=x onerror=alert(1)>"}}]},
    {"ops": [{"insert": {"video": 'https://evil.example/" onmouseover="alert(1)'}}]},
    {"ops": [{"insert": "Click", "attributes": {"link": "javascript:alert(1)"}}, {"insert": "\n"}]},
    {"ops": [{"insert": "Click", "attributes": {"link": "https://user:pass@example.com"}}, {"insert": "\n"}]},
    {"ops": [{"insert": "Click", "attributes": {"link": "https://good.example\\@evil.example"}}, {"insert": "\n"}]},
    {"ops": [{"insert": "Click", "attributes": {"link": " https://good.example"}}, {"insert": "\n"}]},
    {"ops": [{"insert": "x\n", "attributes": {"color": "red"}}]},
    {"ops": [{"insert": "x\n", "attributes": {"bold": "true"}}]},
    {"ops": [{"insert": "x\n", "attributes": {"header": True}}]},
    {"ops": [{"insert": "x\n", "attributes": {"header": 2, "list": "bullet"}}]},
    {"ops": [{"retain": 1}]}, {"ops": [{"delete": 1}]},
    {"ops": [{"insert": "missing newline"}]},
    {"ops": [{"insert": "x" * 50000 + "\n"}]},
    {"ops": [{"insert": "x\n", "attributes": {"list": {}}}]},
])
def test_unsafe_or_invalid_delta_cannot_write(delta, tmp_path):
    save_copy(tmp_path, document())
    before = (tmp_path / "copy.json").read_bytes()
    with pytest.raises(ValueError):
        propose_copy(tmp_path, "home-hero", delta, {"id": "reviewer:chang"},
                     base_revision="draft-1", request_id=str(uuid.uuid4()))
    assert (tmp_path / "copy.json").read_bytes() == before


@pytest.mark.parametrize("link", ["https://example.com/path?q=hello", "http://example.com", "mailto:chang@example.com"])
def test_supported_links_and_line_formats(link):
    delta = {"ops": [{"insert": "Link", "attributes": {"link": link, "italic": True}},
                     {"insert": "\n", "attributes": {"list": "ordered", "indent": 1}},
                     {"insert": "Quote\n", "attributes": {"blockquote": True}}]}
    assert validate_delta(delta) == delta


def test_trusted_import_cannot_erase_or_rewrite_history(tmp_path):
    original = save_copy(tmp_path, document())
    changed = copy.deepcopy(original)
    changed["blocks"][0]["revisions"][0]["author"]["id"] = "agent:replacement"
    with pytest.raises(ValueError, match="cannot be changed"):
        save_copy(tmp_path, changed)
    with pytest.raises(ValueError, match="cannot be removed"):
        save_copy(tmp_path, {"blocks": []})
    assert load_copy(tmp_path) == original
    mtime = (tmp_path / "copy.json").stat().st_mtime_ns
    assert save_copy(tmp_path, original) == original
    assert (tmp_path / "copy.json").stat().st_mtime_ns == mtime


def test_absent_unknown_or_invalid_metadata_is_explicit(tmp_path):
    assert load_copy(tmp_path) == {"schema_version": 1, "blocks": []}
    save_copy(tmp_path, document())
    with pytest.raises(KeyError):
        propose_copy(tmp_path, "missing", {"ops": [{"insert": "Hello\n"}]}, {"id": "reviewer:chang"},
                     base_revision="draft-1", request_id=str(uuid.uuid4()))
    with pytest.raises(ValueError, match="base_revision"):
        propose_copy(tmp_path, "home-hero", {"ops": [{"insert": "Hello\n"}]}, {"id": "reviewer:chang"},
                     base_revision="missing", request_id=str(uuid.uuid4()))
    invalid = document()
    invalid["blocks"][0]["revisions"][0]["status"] = []
    with pytest.raises(ValueError):
        validate_copy(invalid)
    (tmp_path / "copy.json").write_text('{"blocks":[],"blocks":[]}')
    with pytest.raises(ValueError, match="duplicate"):
        load_copy(tmp_path)
    (tmp_path / "copy.json").write_text(json.dumps({"blocks": [], "schema_version": 2}))
    with pytest.raises(ValueError, match="schema_version"):
        load_copy(tmp_path)


def test_ui3_a_proposal_on_an_older_revision_is_refused(tmp_path):
    save_copy(tmp_path, document())
    first = str(uuid.uuid4())
    propose_copy(tmp_path, "home-hero", {"ops": [{"insert": "A\n"}]}, {"id": "reviewer:a"},
                 base_revision="draft-1", request_id=first)
    with pytest.raises(StaleRevisionError):
        propose_copy(tmp_path, "home-hero", {"ops": [{"insert": "B\n"}]}, {"id": "reviewer:b"},
                     base_revision="draft-1", request_id=str(uuid.uuid4()))
    # A retry of the committed save still answers with the stored revision.
    assert len(propose_copy(tmp_path, "home-hero", {"ops": [{"insert": "A\n"}]}, {"id": "reviewer:a"},
                            base_revision="draft-1", request_id=first)["blocks"][0]["revisions"]) == 2
    latest = "r_" + first
    propose_copy(tmp_path, "home-hero", {"ops": [{"insert": "B\n"}]}, {"id": "reviewer:b"},
                 base_revision=latest, request_id=str(uuid.uuid4()))
    assert len(load_copy(tmp_path)["blocks"][0]["revisions"]) == 3


def test_ui3_restore_refuses_a_stale_latest_and_old_clients_still_restore(tmp_path):
    save_copy(tmp_path, document())
    first = str(uuid.uuid4())
    propose_copy(tmp_path, "home-hero", {"ops": [{"insert": "A\n"}]}, {"id": "reviewer:a"},
                 base_revision="draft-1", request_id=first)
    with pytest.raises(StaleRevisionError):
        restore_revision(tmp_path, "home-hero", "draft-1", {"id": "reviewer:b"},
                         request_id=str(uuid.uuid4()), base_revision="draft-1")
    restored = restore_revision(tmp_path, "home-hero", "draft-1", {"id": "reviewer:b"},
                                request_id=str(uuid.uuid4()), base_revision="r_" + first)
    assert restored["blocks"][0]["revisions"][-1]["delta"] == document()["blocks"][0]["revisions"][0]["delta"]
    # An old client sends no base_revision and restores onto the latest.
    old = restore_revision(tmp_path, "home-hero", "r_" + first, {"id": "reviewer:b"}, request_id=str(uuid.uuid4()))
    assert len(old["blocks"][0]["revisions"]) == 4
