import json
import stat
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from agent_annotate import cli, fleet, review_access
from agent_annotate.urls import page_url, redact_review_key, redact_share_links
from agent_annotate.verify import FAIL, PASS, StageResult, VerifyReport


@pytest.fixture
def published_page(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(review_access, "STATE_DIR", tmp_path / "state")
    directory = tmp_path / "repo" / "reviews" / "workspace"
    directory.mkdir(parents=True)
    (directory / "current.meta.json").write_text('{"current":"v1","history":[]}')
    key = review_access.ensure_key(directory)
    base = "https://host.ts.net/annotate/project/workspace/"
    record = {"slug_dir": str(directory), "slug": "workspace", "project": "project", "port": 8800,
              "pid": 1234, "transport": "funnel", "url": base, "public_url": base,
              "public_base_path": "/annotate/project/workspace", "local_url": "http://localhost:8800/",
              "owner_session": "owner-session", "owner_label": "Project > Workspace > Terminal",
              "owner_target": {"terminal": "terminal-id", "label": "Project > Workspace > Terminal"},
              "bus_file": str(tmp_path / "bus" / "project" / "workspace.ndjson")}
    full = page_url(record)
    assert full == base + "#review=" + key
    return SimpleNamespace(record=record, directory=directory, key=key, base=base, full=full)


@pytest.mark.parametrize("fragment,expected", [
    ("", ""), ("#details", "#details"), ("#review", "#review"),
    ("#review=private-key", ""), ("#%72eview=private-key", ""),
    ("#details&review=private-key&tab=feedback", "#details&tab=feedback"),
    ("#code-review=normal-anchor", "#code-review=normal-anchor"),
])
def test_redaction_removes_only_review_fragment_and_preserves_normal_anchors(fragment, expected):
    base = "https://host.ts.net/page/?review=normal-query"
    assert redact_review_key(base + fragment) == base + expected
    assert redact_review_key(None) is None


@pytest.mark.parametrize("retired", [False, True])
def test_registry_birth_and_rewrite_are_private_and_scrub_old_share_keys(published_page, retired):
    page = published_page
    page.record["verify_stages"] = [{"name": "public", "status": PASS, "url": page.full,
        "detail": f"Probe result ({page.full}).", "normal_anchor": "https://docs.example/#details"}]
    state = {"project": "project", "slugs": {"workspace": page.record}, "selected": "workspace", "cursor": 41}
    save = cli._save_retired_for_project if retired else cli._save_state_for_project
    path = cli._retired_file("project") if retired else cli.STATE_DIR / "project.json"
    save("project", state)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert page.key not in path.read_text()
    stored = json.loads(path.read_text())
    assert stored["selected"] == "workspace" and stored["cursor"] == 41
    record = stored["slugs"]["workspace"]
    assert record["owner_target"] == page.record["owner_target"]
    assert record["owner_session"] == "owner-session" and record["url"] == page.base
    assert record["verify_stages"][0]["url"] == page.base
    assert record["verify_stages"][0]["normal_anchor"] == "https://docs.example/#details"
    assert record["verify_stages"][0]["detail"] == f"Probe result ({page.base})."
    assert page.record["verify_stages"][0]["url"] == page.full  # Sanitization does not mutate caller state.
    path.write_text(json.dumps(state))
    path.chmod(0o644)
    save("project", json.loads(path.read_text()))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and page.key not in path.read_text()
    assert page_url(record) == page.full


def test_registry_writer_avoids_predictable_temporary_symlink_and_parallel_collision(published_page, tmp_path):
    page = published_page
    cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("PRIVATE_INERT_MARKER")
    (cli.STATE_DIR / "project.json.tmp").symlink_to(outside)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda writer: cli._save_state_for_project("project", {
            "project": "project", "slugs": {"workspace": page.record}, "writer": writer}), range(12)))
    path = cli.STATE_DIR / "project.json"
    assert outside.read_text() == "PRIVATE_INERT_MARKER"
    assert json.loads(path.read_text())["writer"] in range(12)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(cli.STATE_DIR.glob(".project.json.*"))


def test_gate_and_publish_keep_one_human_link_but_no_bearer_key_in_bus(published_page, monkeypatch, capsys):
    page = published_page
    report = VerifyReport([StageResult("origin", "http://127.0.0.1:8800/", PASS, "shell + 2 anchors"),
                           StageResult("public", page.full, PASS, "rendered 2 anchors")])
    monkeypatch.setattr(cli, "_verify_published", lambda *args, **kwargs: report)
    monkeypatch.setattr(cli, "_inv", lambda: "annotate")
    assert cli._run_gate(page.record, SimpleNamespace(no_verify=False)) is report
    assert page.record["verify_stages"][1]["url"] == page.base
    assert cli._print_publish("project", "workspace", page.directory, page.record, report, False) == 0
    output = capsys.readouterr().out
    assert output.count(page.full) == 1
    assert "http://127.0.0.1:8800" not in output
    assert "PASS  public" in output
    event = json.loads(open(page.record["bus_file"]).read())
    assert event["event"] == "page_published" and event["url"] == page.base
    assert page.key not in json.dumps(event)
    assert page_url(page.record) == page.full


def test_publish_failure_and_exception_details_do_not_put_keys_in_bus(published_page, monkeypatch):
    page = published_page
    report = VerifyReport([StageResult("public", page.full, FAIL, f"Could not open {page.full}")])
    monkeypatch.setattr(cli, "_inv", lambda: "annotate")
    assert cli._print_publish("project", "workspace", page.directory, page.record, report, False) == 1
    raw = open(page.record["bus_file"]).read()
    event = json.loads(raw)
    assert event["event"] == "page_publish_failed" and event["url"] == page.base
    assert page.key not in raw
    assert redact_share_links({"detail": f"Private link ({page.full})."}) == {"detail": f"Private link ({page.base})."}


def test_fleet_includes_funnel_page_using_base_url_without_share_key(published_page, monkeypatch):
    page = published_page
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "workspace", page.record)])
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "testmac")
    captured = []

    def collect(config):
        captured.append(config)
        return {"targets": config["targets"], "limitations": [], "diagnostic": f"Probe {page.full}"}

    monkeypatch.setattr(fleet, "collect_fleet", collect)
    snapshot = cli._fleet_snapshot()
    assert len(captured[0]["targets"]) == 1
    assert captured[0]["targets"][0]["url"] == page.base
    assert snapshot["excluded_local_records"] == 0
    assert page.key not in json.dumps(snapshot) + json.dumps(captured)
    assert page_url(page.record) == page.full
