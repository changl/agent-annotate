from agent_annotate import paths
from agent_annotate.cli import _slug_project


def test_web_assets_are_packaged():
    for filename in ("shell.html", "shell.js", "shell.css", "adapter.js", "template.html"):
        assert (paths.WEB_DIR / filename).is_file()


def test_runtime_paths_are_not_provider_owned():
    rendered = " ".join(str(path) for path in (paths.CONFIG_DIR, paths.DATA_DIR, paths.STATE_DIR))
    assert "/.claude/" not in rendered
    assert "/.codex/" not in rendered


def test_explicit_project_does_not_rename_slug(tmp_path):
    project, slug = _slug_project(tmp_path / "review-page", "portfolio")
    assert project == "portfolio"
    assert slug == "review-page"
