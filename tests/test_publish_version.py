"""Publishing is a single commit; a visible version can never be republished."""
import argparse
import json

import pytest
from test_version_ready import _http
from test_version_ready import round_server as round_server

from agent_annotate import cli, pagegen
from agent_annotate.review_versions import draft_path, fingerprint, read_draft
from agent_annotate.sync_server import _atomic_write_json


@pytest.mark.parametrize("generated", [True, False])
def test_publish_version_commits_once(round_server, tmp_path, monkeypatch, capsys, generated):
    directory, httpd = round_server
    source = tmp_path / 'page.md'
    source.write_text('---\ntitle: Next\n---\n\n## Evidence\n\nReady.\n')
    if generated:
        pagegen.generate(source, directory, 'v2', label='Round 2')
    else:
        (directory / 'versions/v2.html').write_text('<h2 data-anchor-id="s:evidence">Ready</h2>')
    record = {'slug_dir': str(directory), 'port': httpd.server_port,
              'local_url': f'http://127.0.0.1:{httpd.server_port}/'}
    monkeypatch.setattr(cli, '_resolve_scoped_slug', lambda *a: ('test', 'review', record))

    def check(directory, args):
        data = read_draft(directory, args.candidate_version)
        data.update(verified=True, fingerprint=fingerprint(directory, args.candidate_version))
        _atomic_write_json(draft_path(directory, args.candidate_version), data)
        return 0

    monkeypatch.setattr(pagegen, '_call_publish', check)
    args = argparse.Namespace(slug_dir=str(directory), version='v2', label='Round 2', project='test')
    assert cli.cmd_publish_version(args) == 0
    before = (directory / 'current.meta.json').read_bytes()
    assert cli.cmd_publish_version(args) == 2
    assert 'immutable; use v3' in capsys.readouterr().err
    assert (directory / 'current.meta.json').read_bytes() == before
    assert _http(httpd, 'GET', '/current.meta.json')[1]['current'] == 'v2'
    meta = json.loads(before)
    assert [h['version'] for h in meta['history']] == ['v1', 'v2']
    assert meta['history'][-1]['sections'] == 1 and meta['history'][-1]['screenshots'] == 0


def test_missing_version_file_is_refused(tmp_path, capsys):
    assert cli.cmd_publish_version(argparse.Namespace(
        slug_dir=str(tmp_path), version='v9', label=None, project=None)) == 2
    assert 'versions/v9.html not found' in capsys.readouterr().err
