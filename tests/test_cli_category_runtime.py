"""Real CLI processes and HTTP category reads share one sandbox page."""

import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from agent_annotate import cli, pagegen, sync_server


def test_cli_category_lifecycle_over_real_http(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "main"
    source = tmp_path / "review.md"
    source.write_text("---\ntitle: Runtime workspace\n---\n\n## Scope\n\nObserve the actual result.\n")
    pagegen.generate(source, directory, version="v1")
    state = tmp_path / "state"
    state.mkdir()
    bus = tmp_path / "bus/project"
    record = {"project": "project", "slug": "main", "slug_dir": str(directory), "port": 8984,
              "local_url": "http://localhost:8984/", "url": "http://localhost:8984/", "transport": "local",
              "bus_file": str(bus / "main.ndjson"), "workspace_primary": True, "workspace_key": "integration:test"}
    (state / "project.json").write_text(json.dumps({"project": "project", "slugs": {"main": record}}))
    monkeypatch.setattr(cli, "STATE_DIR", state)
    monkeypatch.setattr(sync_server, "STATE_DIR", state)
    handler = sync_server.make_handler(artifact_dir=directory, public_base_path="", slug="main", bus_dir=bus,
                                       v2_mode=True, local_author="reviewer@example.test", local_author_name="Reviewer")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 8984), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = {**os.environ, "ANNOTATE_STATE_DIR": str(state)}

    def run(*arguments):
        result = subprocess.run([sys.executable, "-m", "agent_annotate.cli", *arguments],
                                cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def get(path):
        with urllib.request.urlopen("http://localhost:8984" + path, timeout=3) as response:
            return response.read()

    try:
        cards = tmp_path / "cards.json"
        cards.write_text(json.dumps([{"number": 1, "anchor_id": "d:q1", "decision_request": {
            "prompt": "Fix contrast?", "context": "The label is unreadable.", "recommendation": "fix",
            "options": [{"id": "fix", "label": "Fix", "consequence": "Make it readable."},
                        {"id": "keep", "label": "Keep", "consequence": "Preserve the current contrast."}],
            "evidence": [{"label": "Scope", "anchor": "s:scope"}]}}]))
        assert run("ask", "project/main", "--from", str(cards), "--category", "findings", "--set", "design", "--json")["created"] == 1
        observed = run("cards", "project/main", "--category", "findings", "--json")
        assert observed[0]["finding"] == {"set": "design", "title": "Fix contrast?"}
        proof = tmp_path / "proof.txt"
        proof.write_text("Observed contrast proof")
        fixed = run("finding", "project/main", "--fixed", "1", "--proof", str(proof), "--note", "Checked", "--json")
        attachment = fixed["fixed"]["proof"][0]["attachment"]
        assert get("/attachments/" + attachment) == proof.read_bytes()
        current = (directory / "current.meta.json").read_bytes()
        plan = tmp_path / "rollout.md"
        plan.write_text("## Scope\n\n**Observe** rollout.\n")
        assert run("plan", "project/main", "rollout", "--from", str(plan), "--title", "Rollout", "--json")["current"] == "v1"
        served_plan = get("/plans/rollout/v1.html").decode()
        assert "<strong>Observe</strong>" in served_plan
        assert '"doc": "plan:rollout"' in served_plan and '"category": "plans"' in served_plan
        assert (directory / "current.meta.json").read_bytes() == current
        block = {"id": "hero", "title": "Hero", "current": "r1", "group": "home", "status": "waiting",
                 "revisions": [{"id": "r1", "created_at": "2026-10-04T00:00:00Z", "author": {"id": "agent:test", "name": "Test"},
                                "status": "draft", "delta": {"ops": [{"insert": "Headline\n"}]}}]}
        library = tmp_path / "copy.json"
        library.write_text(json.dumps({"schema_version": 1, "groups": [{"id": "home", "label": "Home"}], "blocks": [block]}))
        assert run("library", "project/main", "--from", str(library), "--json")["blocks"][0]["group"] == "home"
        summary = json.loads(get("/api/categories"))
        assert summary["findings_sets"] == [{"id": "design", "label": "design"}]
        assert summary["plans"][0]["id"] == "rollout"
        counts = {entry["id"]: entry["counts"] for entry in summary["categories"]}
        assert counts["findings"]["done"] == 1 and counts["library"]["waiting"] == 1
        linked = tmp_path / "linked"
        linked.mkdir()
        child = {**record, "slug": "linked", "slug_dir": str(linked), "workspace_primary": False, "standalone": True,
                 "exception": {"reason": "Explicit worksheet", "parent_slug": "project/main"},
                 "url": "http://localhost:8985/", "local_url": "http://localhost:8985/"}
        (state / "project.json").write_text(json.dumps({"project": "project", "slugs": {"main": record, "linked": child}}))
        assert json.loads(get("/api/categories"))["linked_pages"][0]["reason"] == "Explicit worksheet"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert Path(record["bus_file"]).exists()
