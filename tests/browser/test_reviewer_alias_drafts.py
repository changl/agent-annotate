import json

import pytest
from test_workspace_intent import _browser, _page


@pytest.mark.parametrize('mapped', [False, True])
def test_reviewer_can_finish_own_legacy_draft_and_other_reviewers_cannot(tmp_path, monkeypatch, mapped):
    config = tmp_path / 'projects.toml'
    text = '[defaults]\ntransport = "local"\n'
    if mapped:
        text += '\n[defaults.reviewer_aliases]\n"reviewer@example.com" = ["previous@example.com"]\n'
    config.write_text(text)
    monkeypatch.setenv('ANNOTATE_PROJECTS_TOML', str(config))
    directory = _page(tmp_path)
    path = directory / 'comments.json'
    store = json.loads(path.read_text())
    card = store['anchors']['d:q11'][0]
    card['text'] = card['decision_request']['prompt']
    card['decision'] = {'verdict': 'accept', 'by': 'previous@example.com', 'round_pending': True,
                        'ts': '2026-10-02T10:00:00Z', 'text': 'Keep this explanation.'}
    path.write_text(json.dumps(store))
    original = path.read_bytes()
    with _browser(tmp_path, directory) as (page, base):
        if not mapped:
            page.locator('[data-filter="waiting"]').click()
        assert page.locator('.citem-txt').is_hidden(), 'The question prompt should appear only once'
        frame = page.frame_locator('#content-frame')
        assert frame.locator('.annotate-decision-text').count() == 0
        finish = page.locator('#round-finish-btn')
        assert finish.is_visible() is mapped
        assert path.read_bytes() == original
        if mapped:
            assert page.locator('#round-pending-n').inner_text() == '1'
            finish.click()
            page.locator('#round-submit-btn').click()
            for _ in range(50):
                saved = json.loads(path.read_text())['anchors']['d:q11'][0]
                if not saved['decision'].get('round_pending'):
                    break
                page.wait_for_timeout(100)
            assert not saved['decision'].get('round_pending')
            assert saved['decision']['by'] == 'previous@example.com'
            assert saved['decision']['text'] == 'Keep this explanation.'
            assert saved['flagged_by'] == 'reviewer@example.com'
