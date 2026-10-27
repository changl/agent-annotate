"""Copy edits append usable formatted proposals without losing approved content."""

import copy
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_annotate.copy_state import (
    StaleRevisionError,
    approve_revision,
    discard_revisions,
    load_copy,
    propose_copy,
    restore_revision,
    save_copy,
    submit_revisions,
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


def test_ui28_start_item_is_kept_and_must_name_a_block(tmp_path):
    saved = save_copy(tmp_path, dict(document(), start_item="home-hero"))
    assert saved["start_item"] == "home-hero" and load_copy(tmp_path)["start_item"] == "home-hero"
    with pytest.raises(ValueError, match="start_item"):
        validate_copy(dict(document(), start_item="missing"))


def waiting_document(status="needs_you"):
    """An approved r1 and the agent's newer draft r2 waiting on the reviewer."""
    data = document()
    block = data["blocks"][0]
    block.update(status=status, current="draft-1")
    block["revisions"][0]["status"] = "approved"
    block["revisions"].append({"id": "r2", "created_at": "2026-10-03T12:00:00Z", "author": {"id": "agent:copy"},
                               "status": "draft", "delta": {"ops": [{"insert": "Rebex knives.\n"}]}})
    return data


def test_approve_appends_an_approved_copy_and_keeps_every_revision(tmp_path):
    original = save_copy(tmp_path, waiting_document())
    request_id = str(uuid.uuid4())
    result = approve_revision(tmp_path, "home-hero", "r2", {"id": "reviewer:chang", "name": "Chang"}, request_id=request_id)
    block = result["blocks"][0]
    assert block["revisions"][:2] == original["blocks"][0]["revisions"]
    approval = block["revisions"][-1]
    assert approval["id"] == "r_" + request_id and approval["status"] == "approved"
    assert approval["delta"] == original["blocks"][0]["revisions"][1]["delta"]
    assert approval["base_revision"] == "r2" and approval["round_pending"] is True
    assert approval["previous"] == {"current": "draft-1", "status": "needs_you"}
    assert block["current"] == approval["id"] and block["status"] == "done"
    assert load_copy(tmp_path) == result
    # A retry is the same approval; a second approval of approved copy is refused.
    mtime = (tmp_path / "copy.json").stat().st_mtime_ns
    assert approve_revision(tmp_path, "home-hero", "r2", {"id": "reviewer:chang"}, request_id=request_id) == result
    assert (tmp_path / "copy.json").stat().st_mtime_ns == mtime
    with pytest.raises(ValueError, match="already approved"):
        approve_revision(tmp_path, "home-hero", approval["id"], {"id": "reviewer:chang"}, request_id=str(uuid.uuid4()))
    # An agent export taken before the approval cannot silently drop it.
    with pytest.raises(ValueError, match="cannot be changed or removed"):
        save_copy(tmp_path, original)


def test_approve_refuses_an_older_revision_and_keeps_held_copy_held(tmp_path):
    save_copy(tmp_path, waiting_document(status="held"))
    with pytest.raises(StaleRevisionError):
        approve_revision(tmp_path, "home-hero", "draft-1", {"id": "reviewer:chang"}, request_id=str(uuid.uuid4()))
    with pytest.raises(KeyError):
        approve_revision(tmp_path, "home-hero", "missing", {"id": "reviewer:chang"}, request_id=str(uuid.uuid4()))
    block = approve_revision(tmp_path, "home-hero", "r2", {"id": "reviewer:chang"}, request_id=str(uuid.uuid4()))["blocks"][0]
    assert block["status"] == "held" and block["current"] == block["revisions"][-1]["id"]


def test_edit_approved_copy_into_a_new_draft_then_approve_it(tmp_path):
    save_copy(tmp_path, waiting_document())
    chang = {"id": "reviewer:chang"}
    first = approve_revision(tmp_path, "home-hero", "r2", chang, request_id=str(uuid.uuid4()))["blocks"][0]["revisions"][-1]["id"]
    edit = str(uuid.uuid4())
    propose_copy(tmp_path, "home-hero", {"ops": [{"insert": "Rebex knives, engraved.\n"}]}, chang,
                 base_revision=first, request_id=edit)
    block = load_copy(tmp_path)["blocks"][0]
    assert block["current"] == first and block["revisions"][-1]["status"] == "proposed"
    block = approve_revision(tmp_path, "home-hero", "r_" + edit, chang, request_id=str(uuid.uuid4()))["blocks"][0]
    assert block["current"] == block["revisions"][-1]["id"] and block["revisions"][-1]["base_revision"] == "r_" + edit
    assert block["revisions"][-1]["previous"] == {"current": first, "status": "done"}
    assert [r["status"] for r in block["revisions"]] == ["approved", "draft", "approved", "proposed", "approved"]


def test_discard_undoes_unsent_approvals_and_send_keeps_them(tmp_path):
    original = save_copy(tmp_path, waiting_document())
    chang = {"id": "reviewer:chang"}
    approve_revision(tmp_path, "home-hero", "r2", chang, request_id=str(uuid.uuid4()))
    first = load_copy(tmp_path)["blocks"][0]["revisions"][-1]["id"]
    edit = str(uuid.uuid4())
    propose_copy(tmp_path, "home-hero", {"ops": [{"insert": "Another\n"}]}, chang, base_revision=first, request_id=edit)
    approve_revision(tmp_path, "home-hero", "r_" + edit, chang, request_id=str(uuid.uuid4()))
    assert len(discard_revisions(tmp_path, {"reviewer:other"})) == 0
    assert len(discard_revisions(tmp_path, {"reviewer:chang"})) == 3
    assert load_copy(tmp_path) == original
    # A sent approval is the agent's to act on: Discard leaves it.
    request_id = str(uuid.uuid4())
    approve_revision(tmp_path, "home-hero", "r2", chang, request_id=request_id)
    submit_revisions(tmp_path, {"r_" + request_id}, {"reviewer:chang"})
    assert discard_revisions(tmp_path, {"reviewer:chang"}) == []
    block = load_copy(tmp_path)["blocks"][0]
    assert block["current"] == "r_" + request_id and block["status"] == "done"


def test_discard_keeps_a_status_the_agent_set_after_the_approval(tmp_path):
    # Review P1-1: a later held, or a later needs_you on a newer draft, stays.
    save_copy(tmp_path, waiting_document())
    document = approve_revision(tmp_path, "home-hero", "r2", {"id": "reviewer:a"}, request_id=str(uuid.uuid4()))
    document["blocks"][0].update(status="held", held_note="Later agent hold")
    save_copy(tmp_path, document)
    discard_revisions(tmp_path, {"reviewer:a"})
    block = load_copy(tmp_path)["blocks"][0]
    assert block["status"] == "held" and block["current"] == "draft-1"
    save_copy(tmp_path / "b", waiting_document(status="done"))
    document = approve_revision(tmp_path / "b", "home-hero", "r2", {"id": "reviewer:a"}, request_id=str(uuid.uuid4()))
    document["blocks"][0]["revisions"].append({"id": "r3", "created_at": "2026-10-04T12:00:00Z", "author": {"id": "agent:copy"},
                                               "status": "draft", "delta": {"ops": [{"insert": "Newer\n"}]}})
    document["blocks"][0]["status"] = "needs_you"
    save_copy(tmp_path / "b", document)
    discard_revisions(tmp_path / "b", {"reviewer:a"})
    assert load_copy(tmp_path / "b")["blocks"][0]["status"] == "needs_you"


def test_discard_keeps_an_approval_another_approval_replaced_and_never_sends_it(tmp_path):
    # Review P1-2: B's approval names A's as the current revision it replaced.
    save_copy(tmp_path, waiting_document())
    document = approve_revision(tmp_path, "home-hero", "r2", {"id": "reviewer:a"}, request_id=str(uuid.uuid4()))
    first = document["blocks"][0]["current"]
    document["blocks"][0]["revisions"].append({"id": "r3", "created_at": "2026-10-04T12:00:00Z", "author": {"id": "agent:copy"},
                                               "status": "draft", "delta": {"ops": [{"insert": "Newer\n"}]}})
    document["blocks"][0]["status"] = "needs_you"
    save_copy(tmp_path, document)
    approve_revision(tmp_path, "home-hero", "r3", {"id": "reviewer:b"}, request_id=str(uuid.uuid4()))
    assert discard_revisions(tmp_path, {"reviewer:a"}) == []
    block = load_copy(tmp_path)["blocks"][0]
    kept = next(r for r in block["revisions"] if r["id"] == first)
    assert kept["round_pending"] is False and block["revisions"][-1]["author"]["id"] == "reviewer:b"
    assert block["current"] == block["revisions"][-1]["id"] and block["status"] == "done"


def test_previous_is_only_valid_on_an_approval_naming_an_earlier_revision():
    data = waiting_document()
    data["blocks"][0]["revisions"][1]["previous"] = {"current": "draft-1"}
    with pytest.raises(ValueError, match="previous"):
        validate_copy(data)
    data = waiting_document()
    data["blocks"][0]["revisions"][1].update(status="approved", previous={"current": "r9"})
    with pytest.raises(ValueError, match="previous"):
        validate_copy(data)
    data["blocks"][0]["revisions"][1]["previous"] = {"current": "draft-1", "status": "bogus"}
    with pytest.raises(ValueError, match="previous"):
        validate_copy(data)
