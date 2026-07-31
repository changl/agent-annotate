"""`annotate publish` must not print a URL for a page that does not render.

Every working page on this machine was finished by hand because publish
reported success from a route it had never loaded. The gate below is the
contract: a URL appears in the output only after the page has been read back,
and "could not check" is reported as UNVERIFIED rather than as success.
"""

import json
from types import SimpleNamespace

import pytest

from agent_annotate import cli
from agent_annotate.verify import FAIL, PASS, UNAVAILABLE, StageResult, VerifyReport

PUBLIC_URL = "https://reviews.example.com/demo/"


@pytest.fixture
def published(tmp_path, monkeypatch):
    """A slug ready to publish, with every side effect stubbed but the gate."""
    slug_dir = tmp_path / "reviews" / "demo"
    (slug_dir / "versions").mkdir(parents=True)
    (slug_dir / "versions" / "v1.html").write_text(
        "<html><body><p data-anchor-id='s:a'>a</p></body></html>", encoding="utf-8")

    saved = {}
    monkeypatch.setattr(cli, "_load_projects_toml", lambda: {})
    monkeypatch.setattr(cli, "_check_js_lint", lambda p, skip=False: (True, []))
    monkeypatch.setattr(cli, "_load_state_for_project",
                        lambda project: {"project": project, "slugs": {}})
    monkeypatch.setattr(cli, "_save_state_for_project",
                        lambda project, state: saved.update(state["slugs"]))
    monkeypatch.setattr(cli, "_find_free_port_after", lambda start: 8900)
    monkeypatch.setattr(cli, "_start_server", lambda *a, **k: 4242)
    monkeypatch.setattr(cli, "BUS_ROOT", tmp_path / "bus")

    transport = SimpleNamespace(
        publish=lambda slug, port, **opts: {
            "url": PUBLIC_URL,
            "details": {"transport": "cloudflare_tailscale", "https_port": 8456,
                        "tailscale": {"hostname": "host.ts.net", "https_port": 8456}},
        }
    )
    monkeypatch.setattr("agent_annotate.transports.load", lambda name: transport)

    return SimpleNamespace(slug_dir=slug_dir, saved=saved)


def _args(slug_dir, **over):
    base = dict(slug_dir=str(slug_dir), project=None, port=None,
                transport="cloudflare_tailscale", hostname="reviews.example.com",
                path_prefix=None, skip_js_lint=True, no_verify=False,
                verify_timeout=1.0)
    base.update(over)
    return SimpleNamespace(**base)


def _report(*stages):
    return VerifyReport([StageResult(n, f"http://x/{n}", s, d)
                         for n, s, d in stages])


def test_a_failing_stage_suppresses_the_url_and_exits_nonzero(published, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: _report(
        ("origin", PASS, "shell + 3 anchors"),
        ("public", FAIL, "Cloudflare 502 — the tunnel could not reach the origin"),
    ))

    rc = cli.cmd_publish(_args(published.slug_dir))
    out = capsys.readouterr().out

    assert rc == 1
    assert PUBLIC_URL not in out
    assert "NOT PUBLISHED" in out
    assert "502" in out
    assert "public stage failed" in out


def test_the_failing_stage_is_named_so_the_broken_hop_is_obvious(published, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: _report(
        ("origin", PASS, "ok"),
        ("tailscale", FAIL, "connection refused"),
    ))

    cli.cmd_publish(_args(published.slug_dir))
    out = capsys.readouterr().out

    assert "tailscale stage failed" in out
    assert "FAIL  tailscale" in out


def test_all_stages_passing_prints_the_url(published, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: _report(
        ("origin", PASS, "shell + 3 anchors in /content"),
        ("tailscale", PASS, "shell + 3 anchors in /content"),
        ("public", PASS, "rendered 30610 bytes with 11 anchors"),
    ))

    rc = cli.cmd_publish(_args(published.slug_dir))
    out = capsys.readouterr().out

    assert rc == 0
    assert PUBLIC_URL in out
    assert "UNVERIFIED" not in out
    assert published.saved["demo"]["verified"] is True


def test_an_unreachable_browser_prints_the_url_but_says_unverified(published, monkeypatch, capsys):
    """Degrading to a warning is correct; degrading to silence is not."""
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: _report(
        ("origin", PASS, "ok"),
        ("public", UNAVAILABLE, "`orca` is not on PATH"),
    ))

    rc = cli.cmd_publish(_args(published.slug_dir))
    out = capsys.readouterr().out

    assert rc == 0
    assert PUBLIC_URL in out
    assert "UNVERIFIED" in out
    assert "authenticated browser" in out
    assert published.saved["demo"]["verified"] is False


def test_no_verify_says_so_instead_of_claiming_success(published, capsys):
    rc = cli.cmd_publish(_args(published.slug_dir, no_verify=True))
    out = capsys.readouterr().out

    assert rc == 0
    assert "UNVERIFIED" in out
    assert "--no-verify" in out
    assert "verified" not in published.saved["demo"]


def test_a_failed_page_is_still_recorded_so_it_can_be_torn_down(published, monkeypatch, capsys):
    """Leaving a running server out of the state file strands it: neither
    `annotate status` nor `annotate unpublish` can see it."""
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: _report(
        ("origin", FAIL, "connection refused"),
    ))

    cli.cmd_publish(_args(published.slug_dir))

    rec = published.saved["demo"]
    assert rec["pid"] == 4242
    assert rec["port"] == 8900
    assert rec["verified"] is False
    assert rec["verify_stages"][0]["status"] == FAIL


def test_publish_repairs_the_slug_dir_before_serving_it(published, monkeypatch, capsys):
    """The dangling-symlink and missing-history repairs run as part of a normal
    publish, not as a separate command nobody knew to run."""
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: _report(
        ("origin", PASS, "ok"),
    ))
    slug_dir = published.slug_dir
    (slug_dir / "current.html").symlink_to("v1.html")  # the broken form

    rc = cli.cmd_publish(_args(slug_dir))
    out = capsys.readouterr().out

    assert rc == 0
    assert (slug_dir / "current.html").exists()
    meta = json.loads((slug_dir / "current.meta.json").read_text())
    assert meta["current"] == "v1"
    assert [h["version"] for h in meta["history"]] == ["v1"]
    assert "Repaired" in out


def test_an_already_running_slug_is_re_verified_not_waved_through(
        published, monkeypatch, capsys):
    """A live process is not proof the page renders. This branch used to print
    the recorded URL and exit 0, so re-running publish on a page that had just
    failed the gate reported it as fine."""
    monkeypatch.setattr(cli, "_load_state_for_project", lambda project: {
        "project": project,
        "slugs": {"demo": {"slug": "demo", "pid": 4242, "port": 8900,
                           "url": PUBLIC_URL, "local_url": "http://localhost:8900/",
                           "transport": "cloudflare_tailscale",
                           "public_base_path": "/demo",
                           "transport_details": {}, "bus_file": "/tmp/b.ndjson"}},
    })
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: True)
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: _report(
        ("origin", FAIL, "connection refused"),
    ))

    rc = cli.cmd_publish(_args(published.slug_dir))
    out = capsys.readouterr().out

    assert rc == 1
    assert PUBLIC_URL not in out
    assert "NOT PUBLISHED" in out


def test_an_already_running_healthy_slug_prints_its_url(published, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_state_for_project", lambda project: {
        "project": project,
        "slugs": {"demo": {"slug": "demo", "pid": 4242, "port": 8900,
                           "url": PUBLIC_URL, "local_url": "http://localhost:8900/",
                           "transport": "cloudflare_tailscale",
                           "public_base_path": "/demo",
                           "transport_details": {}, "bus_file": "/tmp/b.ndjson"}},
    })
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: True)
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: _report(
        ("origin", PASS, "ok"), ("public", PASS, "rendered 900 bytes with 4 anchors"),
    ))

    rc = cli.cmd_publish(_args(published.slug_dir))
    out = capsys.readouterr().out

    assert rc == 0
    assert PUBLIC_URL in out
    assert "Already running" in out
    assert "re-verified in place" in out


def test_an_unpublishable_slug_dir_fails_before_starting_a_server(published, capsys):
    slug_dir = published.slug_dir
    (slug_dir / "versions" / "v2.html").write_text("<html></html>")
    (slug_dir / "versions" / "v3.html").write_text("<html></html>")

    rc = cli.cmd_publish(_args(slug_dir))
    err = capsys.readouterr().err

    assert rc == 2
    assert "publish-version" in err
    assert published.saved == {}
