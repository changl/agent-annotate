import copy
from types import SimpleNamespace

import pytest

from agent_annotate import cli, deployment, transports


@pytest.mark.parametrize('old_mount', [None, '/shared-name'])
@pytest.mark.parametrize('route_fails', [False, True])
def test_migration_scopes_mount_preserves_owner_and_restores_on_route_failure(tmp_path, monkeypatch, old_mount, route_fails):
    directory = tmp_path / 'workspace'
    directory.mkdir()
    record = {'slug_dir': str(directory), 'port': 8800, 'pid': 100, 'transport': 'local',
              'url': 'http://localhost:8800/', 'public_base_path': old_mount,
              'owner_session': 'original-owner', 'owner_target': {'terminal': 'original-terminal'}}
    original = copy.deepcopy(record)
    cli._save_state_for_project('project', {'slugs': {'workspace': record}})
    def restart(project, slug, python, *, mount=None):
        state = cli._load_state_for_project(project)
        state['slugs'][slug].update(pid=state['slugs'][slug]['pid'] + 1, public_base_path=mount)
        cli._save_state_for_project(project, state)
    def publish(slug, port, **opts):
        assert slug == 'annotate/project/workspace'
        assert port == 8800
        if route_fails:
            raise RuntimeError('route unavailable')
        return {'url': 'https://host.ts.net/annotate/project/workspace/', 'details': {'transport': 'funnel'}}
    monkeypatch.setattr(deployment, 'restart_record', restart)
    monkeypatch.setattr(transports, 'load', lambda name: SimpleNamespace(publish=publish))
    monkeypatch.setattr(cli, '_api', lambda *a: (200, {'version': 'old'}))
    monkeypatch.setattr(cli, '_run_gate', lambda *a: None)
    monkeypatch.setattr(cli, '_print_publish', lambda *a, **kw: 0)
    result = cli._publish_already_running('project', 'workspace', directory, record,
                                         SimpleNamespace(transport='funnel', no_verify=False))
    current = cli._load_state_for_project('project')['slugs']['workspace']
    assert current['owner_session'] == original['owner_session']
    assert current['owner_target'] == original['owner_target']
    assert current['port'] == original['port']
    if route_fails:
        assert result == 1 and current['transport'] == 'local'
        assert current['public_base_path'] == (old_mount or '')
    else:
        assert result == 0 and current['transport'] == 'funnel'
        assert current['public_base_path'] == '/annotate/project/workspace'
        assert current['legacy_routes'][0]['public_base_path'] == old_mount
