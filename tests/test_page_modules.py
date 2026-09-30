import json
import re

import pytest

from agent_annotate.decision_quality import decision_warnings
from agent_annotate.pagegen import PageGenError, generate
from agent_annotate.sync_server import _mtime_stamp


def test_project_and_details_compile_and_project_survives_next_version(tmp_path):
    source = tmp_path / "page.md"
    project = {"title":"Workspace", "modules":[{"id":"resources","title":"Open project","kind":"links","items":[{"label":"CMS","url":"https://cms.example/admin"}]}]}
    text = "---\ntitle: Progress\nfull_plan: true\nother_files_required: none\n---\n## Scope\nVisible progress.\n\n```details\nSupporting evidence\nA retained detail.\n- Detail one\n```\n\n```project\n" + json.dumps(project) + "\n```\n"
    source.write_text(text)
    directory = tmp_path / "review"
    result = generate(source, directory)
    html = result["html"].read_text()
    assert '<details class="aa-details"' in html
    assert '<summary>Supporting evidence</summary>' in html
    assert 'data-anchor-id="s:scope:p2"' in html
    before = (directory / "project.json").read_bytes()
    source.write_text(text.split("```project", 1)[0])
    generate(source, directory, "v2")
    assert (directory / "project.json").read_bytes() == before


def test_bad_project_does_not_write_any_version(tmp_path):
    source = tmp_path / "page.md"
    source.write_text('## Scope\n```project\n{"modules":[{"kind":"links"}]}\n```\n')
    with pytest.raises(PageGenError):
        generate(source, tmp_path / "review")
    assert not (tmp_path / "review").exists()


def test_manual_option_prompt_warns_but_intentional_text_question_does_not():
    assert decision_warnings({"prompt":"Choose an option. Answer with the option letter.","options":["comment"]})
    assert not decision_warnings({"prompt":"What detail should change?","options":["comment"]})


def test_asset_key_uses_bytes_even_when_timestamp_stays_identical(tmp_path):
    asset = tmp_path / "shell.js"
    asset.write_text("first")
    first = _mtime_stamp(asset)
    stamp = asset.stat().st_mtime
    asset.write_text("second")
    import os
    os.utime(asset, (stamp, stamp))
    assert _mtime_stamp(asset) != first
    assert re.fullmatch(r"[0-9]+", first)
    assert _mtime_stamp(tmp_path / "absent") == "0"
