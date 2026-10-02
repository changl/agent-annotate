"""Copy reads stay bounded to the delivered asset, imports preserve its history."""
import json
from types import SimpleNamespace

from agent_annotate import cli
from agent_annotate.copy_state import load_copy, save_copy


def test_copy_read_one_asset_and_identical_import_is_noop(tmp_path, monkeypatch, capsys):
    document = {"schema_version": 1, "blocks": [{"id": name, "title": name, "current": "r1", "revisions": [
        {"id": "r1", "created_at": "2026-10-02T00:00:00+00:00", "author": {"id": "agent:builder", "name": "Builder"},
         "status": "draft", "delta": {"ops": [{"insert": name + "\n"}]}}]} for name in ("hero", "footer")]}
    save_copy(tmp_path, document)
    record = {"slug_dir": str(tmp_path), "bus_file": str(tmp_path / "bus.ndjson"), "transport_url": "https://example.test/page/", "transport": "local"}
    monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *args: ("project", "page", record))
    args = SimpleNamespace(slug="project/page", project=None, from_file=None, block="hero")
    assert cli.cmd_copy(args) == 0
    assert [block["id"] for block in json.loads(capsys.readouterr().out)["blocks"]] == ["hero"]
    source = tmp_path / "input.json"
    source.write_text(json.dumps(document))
    args.from_file = str(source)
    assert cli.cmd_copy(args) == 2
    assert "complete copy document" in capsys.readouterr().err
    args.block = None
    assert cli.cmd_copy(args) == 0
    assert not (tmp_path / "bus.ndjson").exists()
    assert load_copy(tmp_path) == document
