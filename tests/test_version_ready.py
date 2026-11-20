"""A review round is visible once, only after its page and cards are ready."""
import argparse
import http.client
import http.server
import json
import threading

import pytest

from agent_annotate import cli, pagegen, sync_server
from agent_annotate.paths import WEB_DIR
from agent_annotate.review_versions import fingerprint, read_draft


def _page(tmp_path):
    directory = tmp_path / 'review'
    (directory / 'versions').mkdir(parents=True)
    (directory / 'versions/v1.html').write_text('<p data-anchor-id="s:old">Old</p>')
    (directory / 'current.html').symlink_to('versions/v1.html')
    (directory / 'current.meta.json').write_text(json.dumps({
        'current': 'v1', 'history': [{'version': 'v1', 'label': 'Old'}]}))
    (directory / 'comments.json').write_text(json.dumps({
        'schema_version': 2, 'anchors': {}, 'archived': {}}))
    return directory


def test_failing_card_never_makes_version_current(tmp_path, monkeypatch):
    directory = _page(tmp_path)
    source = tmp_path / 'page.md'
    source.write_text('---\ntitle: Next\n---\n\n## Evidence\n\nReady.\n\n```cards\n' + json.dumps([{'anchor_id': 'd:q1', 'number': 1, 'decision_request': {'prompt': 'Ship?', 'context': 'Ready', 'recommendation': 'yes', 'options': [{'id': 'yes', 'label': 'Yes', 'consequence': 'Ship'}, {'id': 'no', 'label': 'No', 'consequence': 'Wait'}], 'evidence': [{'anchor': 's:evidence', 'label': 'Proof'}]}}]) + '\n```\n')
    monkeypatch.setattr(cli, '_slug_project', lambda *a: ('test', 'review'))
    monkeypatch.setattr('agent_annotate.workspace.duplicate_page', lambda *a: None)
    monkeypatch.setattr(pagegen, '_call_publish', lambda *a: 0)
    monkeypatch.setattr(pagegen, '_call_ask', lambda *a: 2)
    args = argparse.Namespace(slug_dir=str(directory), from_file=str(source),
        version='v2', label='Next', project='test', publish=True, ask=True)
    assert pagegen.cmd_new(args) == 2
    assert cli._read_meta(directory)['current'] == 'v1'
    assert [h['version'] for h in cli._read_meta(directory)['history']] == ['v1']
    assert (directory / 'current.html').resolve().name == 'v1.html'


def test_republish_of_shown_version_is_refused(tmp_path, capsys):
    directory = _page(tmp_path)
    assert cli.cmd_publish_version(argparse.Namespace(
        slug_dir=str(directory), version='v1', label='Changed', project='test')) != 0
    assert 'v2' in capsys.readouterr().err
    assert cli._read_meta(directory)['history'][0]['label'] == 'Old'


def test_fix_flag_is_staged_for_the_ready_transaction(tmp_path):
    directory = _page(tmp_path)
    source = tmp_path / 'page.md'
    source.write_text('---\ntitle: Follow-up\n---\n\n## Fix\n\nCorrected.\n')
    result = pagegen.generate(source, directory, 'v2', fixes='v1')
    assert result['fixes'] == 'v1'



@pytest.fixture
def round_server(tmp_path):
    directory = _page(tmp_path)
    handler = sync_server.make_handler(artifact_dir=directory, public_base_path='',
        slug='review', bus_dir=tmp_path / 'bus', skill_dir=WEB_DIR)
    for port in range(18750, 18800):
        try:
            httpd = http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)
            break
        except OSError:
            continue
    else:
        pytest.fail('no sandbox port available')
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield directory, httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(2)


def _http(server, method, path, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    conn.request(method, path, body=json.dumps(body) if body is not None else None,
        headers={'X-Annotate-Agent': 'agent:test', 'Content-Type': 'application/json'})
    response = conn.getresponse()
    status, raw = response.status, response.read()
    conn.close()
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def _stage_round(directory, tmp_path, fixes=None, cards=None):
    source = tmp_path / 'round.md'
    source.write_text('---\ntitle: Round\n---\n\n## Evidence\n\nReady.\n\n```cards\n' + json.dumps([_card()] if cards is None else cards) + '\n```\n')
    result = pagegen.generate(source, directory, 'v2', fixes=fixes)
    draft = read_draft(directory, 'v2')
    draft.update(verified=True, fingerprint=fingerprint(directory, 'v2'))
    sync_server._atomic_write_json(directory / '.review-drafts/v2.json', draft)
    return result, draft


def _ready(httpd, draft, items):
    return _http(httpd, 'POST', '/api/comments/batch', {
        'items': items, 'idempotency': 'anchor',
        'publish_version': {'version': 'v2', 'preview': draft['preview']}})


def _card(number=1):
    return {'anchor_id': f'd:q{number}', 'version': 'v2', 'number': number, 'text': 'Ship?',
        'decision_request': {'prompt': 'Ship?', 'context': 'Ready', 'recommendation': 'yes',
            'options': [{'id': 'yes', 'label': 'Yes', 'consequence': 'Ship'},
                        {'id': 'no', 'label': 'No', 'consequence': 'Wait'}],
            'evidence': [{'anchor': 's:evidence', 'label': 'Proof'}]}}


def test_ready_fix_round_trips_in_metadata_api(round_server, tmp_path):
    directory, httpd = round_server
    meta = cli._read_meta(directory)
    meta['owner'] = {'owner_session': 'coordinator'}
    (directory / 'current.meta.json').write_text(json.dumps(meta))
    _, draft = _stage_round(directory, tmp_path, fixes='v1')
    assert _ready(httpd, draft, [_card()])[0] == 200
    status, meta = _http(httpd, 'GET', '/current.meta.json')
    assert status == 200
    assert meta['current'] == 'v2'
    assert meta['history'][-1]['fixes'] == 'v1'
    events = [json.loads(line) for line in (tmp_path / 'bus/review.ndjson').read_text().splitlines()]
    assert [e['owner_session'] for e in events if e['event'] == 'version_published'] == ['coordinator']
    assert not any(k in meta['history'][-1] for k in ('preview', 'verified', 'fingerprint'))
    assert _http(httpd, 'GET', '/comments.json')[1]['anchors']['d:q1'][0]['version'] == 'v2'
    assert _ready(httpd, draft, [_card()])[0] == 409


def test_reissued_number_carries_private_notes_without_moving_a_pending_choice(round_server, tmp_path):
    directory, httpd = round_server
    prior = dict(_card(), id="prior", version="v1", author="agent:test", status="open",
                 decision={"verdict": "select", "option_id": "yes", "text": "Yes", "by": "reviewer@example.com",
                           "ts": "2026-11-10T01:00:00Z", "round_pending": True, "evidence": {"version": "v1"}},
                 replies=[{"author": author, "ts": "2026-11-10T01:00:00Z", "text": text, "sent_at": None}
                          for author, text in [("reviewer@example.com", "☑ Selected: Yes"),
                                               ("reviewer@example.com", "PRIVATE first note"),
                                               ("other@example.com", "PRIVATE second note")]])
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"d:q1": [prior]}, "archived": {}}))
    _, draft = _stage_round(directory, tmp_path)
    assert _ready(httpd, draft, [_card()])[0] == 200
    stored = json.loads((directory / "comments.json").read_text())["anchors"]["d:q1"]
    old, fresh = stored
    assert old["decision"] == prior["decision"]
    assert old["replies"] == prior["replies"][:1]
    assert fresh["replies"] == prior["replies"][1:]
    assert not fresh.get("decision")
    assert "PRIVATE" not in json.dumps(_http(httpd, "GET", "/api/comments")[1])


def _answered_prior(round_pending=False, **request):
    card = _card()
    decision = {"id": "d1", "verdict": "select", "option_id": "yes", "text": "Yes", "by": "reviewer@example.com",
                "ts": "2026-11-10T01:00:00Z"}
    if round_pending:  # the unproxied test server's reviewer is "anonymous"
        decision.update(round_pending=True, by="anonymous")
    prior = dict(card, id="prior", version="v1", author="agent:test", status="open", decision=decision,
                 decision_request={**card["decision_request"], **request})
    if not round_pending:
        prior.update(flagged_for_session=True, flagged_at="2026-11-10T01:01:00Z", flagged_by="reviewer@example.com")
    return prior


def _publish_over(round_server, tmp_path, prior):
    directory, httpd = round_server
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"d:q1": [prior]}, "archived": {}}))
    _, draft = _stage_round(directory, tmp_path)
    assert _ready(httpd, draft, [_card()])[0] == 200
    return json.loads((directory / "comments.json").read_text())["anchors"]["d:q1"]


def _reviewer_post(httpd, path, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
    conn.request('POST', path, body=json.dumps(body or {}), headers={'Content-Type': 'application/json'})
    response = conn.getresponse()
    status, payload = response.status, json.loads(response.read())
    conn.close()
    return status, payload


@pytest.mark.parametrize("label", ["Proof", "Proof, 12 cards"])
def test_a_new_version_keeping_an_answered_number_keeps_the_answer(round_server, tmp_path, label):
    # agent-annotate-11r: FLD #39109 answered in v999 came back undecided in v1000.
    prior = _answered_prior(evidence=[{"anchor": "s:evidence", "label": label}])
    old, fresh = _publish_over(round_server, tmp_path, prior)
    assert fresh["version"] == "v2" and fresh["decision"] == prior["decision"]
    assert old["decision"] == prior["decision"]
    assert not sync_server._comment_needs_push(fresh)


@pytest.mark.parametrize("change", [
    {"prompt": "Ship last week's build?"},
    {"options": [{"id": "yes", "label": "Yes", "consequence": "Ship next month"},
                 {"id": "no", "label": "No", "consequence": "Wait"}]},
    {"consequences": {"accept": "Ship to production"}},
])
def test_a_new_version_asking_a_changed_question_under_the_number_asks_again(round_server, tmp_path, change):
    _, fresh = _publish_over(round_server, tmp_path, _answered_prior(**change))
    assert not fresh.get("decision")


def test_a_discarded_answer_is_not_carried_to_the_new_version(round_server, tmp_path):
    prior = _answered_prior()
    prior.pop("flagged_for_session")
    prior["agent_snapshot"] = {k: v for k, v in prior.items() if k != "decision"}
    _, fresh = _publish_over(round_server, tmp_path, prior)
    assert not fresh.get("decision")


def test_an_inherited_answer_is_visible_to_the_agent_past_unsent_notes():
    answered = _answered_prior()
    card = dict(_card(), id="new", version="v2", status="open",
                agent_snapshot={"id": "new", "status": "open", "decision": None, "replies": []},
                replies=[{"author": "reviewer@example.com", "ts": "2026-11-10T02:00:00Z", "text": "PRIVATE", "sent_at": None},
                         {"author": "reviewer@example.com", "ts": "2026-11-10T00:30:00Z", "text": "legacy note"}])
    assert sync_server._share_answer(answered, card)
    view = sync_server.comment_view(card)
    assert view["decision"] == answered["decision"] and "PRIVATE" not in json.dumps(view)
    assert sync_server._unsent_notes(card) == ["PRIVATE", "legacy note"]


def test_an_inherited_answer_goes_beneath_an_unsent_draft():
    answered = _answered_prior()
    draft = {"verdict": "comment", "text": "Maybe", "by": "reviewer@example.com", "ts": "2026-11-10T02:00:00Z",
             "round_pending": True}
    card = dict(_card(), id="new", version="v2", status="open", decision=dict(draft))
    assert sync_server._share_answer(answered, card)
    assert card["decision"] == draft
    assert sync_server.comment_view(card)["decision"] == answered["decision"]


def test_a_discarded_pick_on_the_newer_copy_still_takes_the_sent_answer():
    prior = _answered_prior(round_pending=True)
    newer = dict(_card(), id="new", version="v2", status="open", author="agent:test", origin_id="prior",
                 decision={"verdict": "select", "option_id": "no", "by": "anonymous", "ts": "2026-11-10T00:00:00Z"},
                 agent_snapshot={"id": "new", "status": "open", "decision": None})
    store = {"anchors": {"d:q1": [prior, newer]}}
    assert sync_server._unanswered_copies(store, prior) == [newer]


@pytest.mark.parametrize("send", ["/api/rounds/submit", "/api/comments/prior/push"])
def test_an_answer_sent_on_the_older_copy_answers_the_newer_one(round_server, tmp_path, send):
    # FLD #39118: picked in v1004, v1005 published before Send, then answered again.
    _, fresh = _publish_over(round_server, tmp_path, _answered_prior(round_pending=True))
    assert not fresh.get("decision")
    status, sent = _reviewer_post(round_server[1], send)
    assert status == 200 and sent.get("undecided_ids", []) == []
    old, fresh = json.loads((round_server[0] / "comments.json").read_text())["anchors"]["d:q1"]
    assert fresh["decision"] == old["decision"] and not fresh["decision"].get("round_pending")
    assert fresh["flagged_at"] == old["flagged_at"] and fresh["delivery_id"] == old["delivery_id"]


@pytest.mark.parametrize("with_id", [True, False])
def test_a_changed_answer_sent_on_the_older_copy_replaces_the_inherited_one(round_server, tmp_path, with_id):
    prior = _answered_prior()
    prior["decision"]["by"] = "anonymous"
    if not with_id:  # a reply-made answer has no id
        prior["decision"].pop("id")
    _, fresh = _publish_over(round_server, tmp_path, prior)
    assert fresh["decision"]["option_id"] == "yes"
    httpd = round_server[1]
    assert _reviewer_post(httpd, "/api/comments/prior/decision",
                          {"verdict": "select", "option_id": "no", "text": "No", "defer_push": True})[0] == 200
    assert _reviewer_post(httpd, "/api/rounds/submit")[0] == 200
    old, fresh = json.loads((round_server[0] / "comments.json").read_text())["anchors"]["d:q1"]
    assert old["decision"]["option_id"] == "no" and fresh["decision"] == old["decision"]


def test_an_answer_sent_on_the_newer_copy_leaves_the_older_one_alone(round_server, tmp_path):
    prior = _answered_prior()
    prior["decision"]["by"] = "anonymous"
    _, fresh = _publish_over(round_server, tmp_path, prior)
    httpd = round_server[1]
    assert _reviewer_post(httpd, f"/api/comments/{fresh['id']}/decision",
                          {"verdict": "select", "option_id": "no", "text": "No", "defer_push": True})[0] == 200
    assert _reviewer_post(httpd, "/api/rounds/submit")[0] == 200
    old, fresh = json.loads((round_server[0] / "comments.json").read_text())["anchors"]["d:q1"]
    assert old["decision"] == prior["decision"] and fresh["decision"]["option_id"] == "no"


@pytest.mark.parametrize("confirmed", [False, True])
def test_carrying_a_text_answer_keeps_already_sent_replies_from_the_same_second(confirmed):
    decision = {"verdict": "comment", "text": "PRIVATE", "round_pending": True,
                "by": "reviewer@example.com", "ts": "2026-11-10T01:00:00Z"}
    sent = {"author": decision["by"], "ts": decision["ts"], "text": "💬 Answer in words: PRIVATE",
            "sent_at": "2026-11-10T01:00:00Z"}
    pending = {**sent, "sent_at": None}
    prior = {"id": "old", "number": 1, "author": "agent:test", "decision": decision, "replies": [sent, pending]}
    if confirmed:
        prior["agent_snapshot"] = {"status": "user_confirmed", "decision": {"verdict": "accept"}}
    fresh = {"id": "new", "number": 1, "version": "v2", "author": "agent:test"}
    sync_server._carry_unsent_feedback(prior, fresh)
    assert prior["replies"] == [sent]
    if confirmed:
        assert prior["status"] == "user_confirmed" and prior["decision"] == {"verdict": "accept"}
    else:
        assert not prior.get("decision")
    assert fresh["replies"] == [pending]
    assert fresh["decision"] == decision
    assert "PRIVATE" not in json.dumps(fresh["agent_snapshot"])


def test_server_card_failure_keeps_previous_round_and_store(round_server, tmp_path):
    directory, httpd = round_server
    _, draft = _stage_round(directory, tmp_path, cards=[_card(), _card(2)])
    before = (directory / 'comments.json').read_bytes()
    broken = _card(2)
    broken['decision_request']['evidence'] = [{'anchor': 's:missing', 'label': 'Missing'}]
    assert _ready(httpd, draft, [_card(), broken])[0] == 400
    assert cli._read_meta(directory)['current'] == 'v1'
    assert (directory / 'comments.json').read_bytes() == before
    assert _http(httpd, 'GET', '/content?v=v2')[0] == 404
    assert _http(httpd, 'GET', '/versions/v2.html')[0] == 404
    (directory / 'content').mkdir()
    assert _http(httpd, 'GET', '/?v=v2')[0] == 404
    assert _http(httpd, 'GET', '/current.meta.json')[1]['history'] == [{'version': 'v1', 'label': 'Old'}]


def test_number_conflict_keeps_previous_round(round_server, tmp_path):
    directory, httpd = round_server
    _http(httpd, 'POST', '/api/comments', {'anchor_id': 's:old', 'text': 'Existing', 'number': 1})
    _, draft = _stage_round(directory, tmp_path)
    before = (directory / 'comments.json').read_bytes()
    assert _ready(httpd, draft, [_card()])[0] == 409
    assert (directory / 'comments.json').read_bytes() == before
    assert cli._read_meta(directory)['current'] == 'v1'


def test_checked_draft_cannot_change_before_commit(round_server, tmp_path):
    directory, httpd = round_server
    _, draft = _stage_round(directory, tmp_path)
    with (directory / 'versions/v2.html').open('a') as stream:
        stream.write('Changed after checking')
    assert _ready(httpd, draft, [])[0] == 409
    assert cli._read_meta(directory)['current'] == 'v1'


def test_unchecked_draft_cannot_be_committed(round_server, tmp_path):
    directory, httpd = round_server
    _, draft = _stage_round(directory, tmp_path)
    draft.pop('verified')
    sync_server._atomic_write_json(directory / '.review-drafts/v2.json', draft)
    assert _ready(httpd, draft, [])[0] == 409
    assert cli._read_meta(directory)['current'] == 'v1'


def test_generated_shown_page_cannot_be_rewritten(tmp_path):
    directory = _page(tmp_path)
    source = tmp_path / 'page.md'
    source.write_text('---\ntitle: Changed\n---\n\n## Changed\n\nOops.\n')
    before = (directory / 'versions/v1.html').read_bytes()
    with pytest.raises(pagegen.PageGenError, match='immutable; use v2'):
        pagegen.generate(source, directory, 'v1')
    assert (directory / 'versions/v1.html').read_bytes() == before


def test_a_ready_round_rejects_later_card_authoring(round_server, tmp_path, monkeypatch, capsys):
    directory, httpd = round_server
    _, draft = _stage_round(directory, tmp_path)
    assert _ready(httpd, draft, [_card()])[0] == 200
    before = (directory / 'comments.json').read_bytes()
    assert _http(httpd, 'POST', '/api/comments/batch', {'items': [_card()]})[0] == 409
    card = _http(httpd, 'GET', '/comments.json')[1]['anchors']['d:q1'][0]
    assert _http(httpd, 'PUT', '/api/comments/' + card['id'], {'text': 'Changed'})[0] == 409
    record = {'slug_dir': str(directory), 'port': httpd.server_port}
    monkeypatch.setattr(cli, '_resolve_scoped_slug', lambda *a: ('test', 'review', record))
    source = tmp_path / 'cards.json'
    source.write_text(json.dumps([_card()]))
    assert cli.cmd_ask(argparse.Namespace(slug='review', project='test', from_file=str(source),
        version='v2', author='agent:test', json=False)) == 2
    assert 'immutable; use v3' in capsys.readouterr().err
    assert (directory / 'comments.json').read_bytes() == before


@pytest.mark.parametrize("current_link", [True, False])
def test_a_failed_commit_rolls_back_the_cards_and_metadata(round_server, tmp_path, monkeypatch, current_link):
    from agent_annotate import review_versions
    directory, httpd = round_server
    _, draft = _stage_round(directory, tmp_path)
    if not current_link:
        current = directory / 'current.html'
        data = current.read_bytes()
        current.unlink()
        current.write_bytes(data)
    before = {name: (directory / name).read_bytes() for name in ('comments.json', 'current.meta.json', 'current.html')}
    def fail(*args):
        raise OSError('simulated metadata write failure')
    monkeypatch.setattr(review_versions, 'activate', fail)
    assert _ready(httpd, draft, [_card()])[0] == 500
    assert all((directory / name).read_bytes() == data for name, data in before.items())
    assert (directory / 'current.html').is_symlink() is current_link
    assert _http(httpd, 'GET', '/content?v=v2')[0] == 404


def test_a_round_cannot_omit_staged_cards(round_server, tmp_path):
    directory, httpd = round_server
    _, draft = _stage_round(directory, tmp_path)
    assert _ready(httpd, draft, [])[0] == 400
    assert cli._read_meta(directory)['current'] == 'v1'


def test_fix_option_is_available_on_the_one_command_path():
    args = cli.build_parser().parse_args(['new', '/tmp/draft', '--from', '/tmp/page.md',
        '--version', 'v2', '--publish', '--ask', '--fixes', 'v1'])
    assert args.fixes == 'v1' and args.publish and args.ask


def test_old_servers_are_refused_before_any_card_is_posted(round_server, tmp_path, monkeypatch, capsys):
    directory, _ = round_server
    _stage_round(directory, tmp_path)
    calls = []
    def api(record, method, path, body, author):
        calls.append((method, path))
        return 200, {'batch': True}
    monkeypatch.setattr(cli, '_api', api)
    assert cli._commit_review({'slug_dir': str(directory)}, 'v2', [_card()], 'agent:test') == 2
    assert calls == [('GET', '/api/capabilities')]
    assert 'no cards were posted' in capsys.readouterr().err
    assert cli._read_meta(directory)['current'] == 'v1'


def test_unpublished_review_items_are_hidden_from_api_and_badge_counts(round_server, tmp_path):
    directory, httpd = round_server
    _stage_round(directory, tmp_path)
    old = {**_card(9), 'id': 'old', 'version': 'v1', 'author': 'agent:test', 'status': 'open'}
    staged = {**_card(), 'id': 'staged', 'author': 'agent:test', 'status': 'open'}
    store = {'schema_version': 2, 'anchors': {'d:q9': [old], 'd:q1': [staged]}, 'archived': {}}
    (directory / 'comments.json').write_text(json.dumps(store))
    before = (directory / 'comments.json').read_bytes()
    for route in ('/comments.json', '/comments.json?view=poll'):
        body = _http(httpd, 'GET', route)[1]
        assert [c['id'] for items in body['anchors'].values() for c in items] == ['old']
    assert [c['id'] for c in _http(httpd, 'GET', '/api/comments')[1]] == ['old']
    categories = _http(httpd, 'GET', '/api/categories')[1]['categories']
    assert next(c for c in categories if c['id'] == 'review')['counts']['needs_you'] == 1
    assert (directory / 'comments.json').read_bytes() == before
    from agent_annotate.review_versions import activate
    activate(directory, 'v2')
    body = _http(httpd, 'GET', '/comments.json?view=poll')[1]
    assert {c['id'] for items in body['anchors'].values() for c in items} == {'old', 'staged'}


def test_an_interrupted_initial_round_is_hidden_without_published_metadata(tmp_path):
    from agent_annotate.review_versions import stage, visible_store
    stage(tmp_path, 'v1', 'Initial', None, {})
    item = {**_card(), 'version': 'v1'}
    plan = {**item, 'category': 'plans', 'doc': 'plan:rollout'}
    store = {'anchors': {'draft': [item], 'plan': [plan]}, 'archived': {}}
    result = visible_store(tmp_path, store, {})
    assert result['anchors']['draft'] == []
    assert result['anchors']['plan'] == [plan]
    assert store['anchors']['draft'] == [item]


def test_initial_page_root_waits_until_a_version_is_ready(round_server, tmp_path):
    directory, httpd = round_server
    (directory / 'current.html').unlink()
    (directory / 'current.meta.json').write_text('{}')
    _, draft = _stage_round(directory, tmp_path)
    (directory / 'content').mkdir()
    assert _http(httpd, 'GET', '/')[0] == 503
    assert _http(httpd, 'GET', '/?v=v2')[0] == 404
    assert _http(httpd, 'GET', '/__review_preview/v2/' + draft['preview'] + '/')[0] == 200


def test_completed_metadata_wins_over_a_leftover_draft_marker(round_server, tmp_path):
    directory, httpd = round_server
    _, draft = _stage_round(directory, tmp_path)
    assert _ready(httpd, draft, [_card()])[0] == 200
    sync_server._atomic_write_json(directory / '.review-drafts/v2.json', draft)
    assert _http(httpd, 'GET', '/?v=v2')[0] == 200
    assert _http(httpd, 'GET', '/content?v=v2')[0] == 200
    assert _http(httpd, 'GET', '/versions/v2.html')[0] == 200
    assert _http(httpd, 'GET', '/__review_preview/v2/' + draft['preview'] + '/')[0] == 404


def test_checks_cannot_recreate_a_draft_after_a_peer_has_published(round_server, tmp_path, monkeypatch):
    from agent_annotate.review_versions import draft_path
    from agent_annotate.verify import PASS, StageResult, VerifyReport
    directory, httpd = round_server
    _, draft = _stage_round(directory, tmp_path)
    def check(*args, **kwargs):
        assert _ready(httpd, draft, [_card()])[0] == 200
        return VerifyReport([StageResult('origin', 'http://localhost/', PASS, 'ok')])
    monkeypatch.setattr(cli, '_verify_published', check)
    with pytest.raises(ValueError, match='immutable; use v3'):
        cli._run_gate({'slug_dir': str(directory), 'port': httpd.server_port},
            argparse.Namespace(candidate_version='v2', verify_timeout=1))
    assert not draft_path(directory, 'v2').exists()
    assert _http(httpd, 'GET', '/content?v=v2')[0] == 200


def test_a_later_draft_cannot_replace_the_cards_of_the_round_being_published(tmp_path):
    directory = _page(tmp_path)
    first, _ = _stage_round(directory, tmp_path)
    source = tmp_path / 'later.md'
    later = _card()
    later['text'] = later['decision_request']['prompt'] = 'A later question?'
    source.write_text('---\ntitle: Later\n---\n\n## Evidence\n\nReady.\n\n```cards\n' + json.dumps([later]) + '\n```\n')
    pagegen.generate(source, directory, 'v3')
    assert json.loads(first['cards_json'].read_text())[0]['decision_request']['prompt'] == 'Ship?'
    assert json.loads((directory / 'cards.json').read_text())[0]['decision_request']['prompt'] == 'A later question?'
