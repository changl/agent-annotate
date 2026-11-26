import datetime
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("host_backlog", Path(__file__).parents[1] / "scripts" / "host_backlog.py")
hb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hb)

NOW = datetime.datetime(2026, 11, 26, 8, 0, tzinfo=datetime.UTC)


def ago(minutes):
    return (NOW - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_a_send_waits_until_a_later_send_is_read():
    journals = {
        "rebex/rebex": [{"state": "started", "created_at": ago(3000)}, {"state": "acknowledged", "created_at": ago(60)}],
        "reviews/a": [{"state": "acknowledged", "created_at": ago(90)}, {"state": "pending", "created_at": ago(45)},
                      {"state": "accepted", "created_at": ago(40)}],
        "reviews/b": [{"state": "started", "created_at": ago(10)}],
        "reviews/c": [{"state": "superseded", "created_at": ago(500)}],
    }
    assert list(hb.sends(journals, NOW)) == ["send:reviews/a"]
    assert "45 min" in hb.sends(journals, NOW)["send:reviews/a"]


def test_mail_flags_unread_coordinator_mail_and_open_questions_from_running_workers():
    def msg(i, minutes, **kw):
        return {"id": i, "created_at": ago(minutes), "run_id": "run_x", "read": 1, "type": "status",
                "to_handle": "run:run_x", "thread_id": None, **kw}
    mail = [
        msg("m1", 50, read=0),                                       # unread, old
        msg("m2", 5, read=0),                                        # unread, fresh
        msg("m3", 40, type="question", thread_id="m3", payload=json.dumps({"dispatchId": "ctx_live"})),
        msg("m4", 40, type="question", thread_id="m4", payload=json.dumps({"dispatchId": "ctx_gone"})),
        msg("m5", 40, type="question", thread_id="m5", payload=json.dumps({"dispatchId": "ctx_live"})),
        msg("r5", 35, to_handle="dispatch:ctx_live", thread_id="m5"),  # the answer to m5
    ]
    got = hb.orca_mail(mail, {"ctx_live": "run_x"}, {"run_x": "Rebex"}, NOW)
    assert sorted(got) == ["question:m3", "unread:m1"]
    assert "Rebex" in got["question:m3"]


def test_workers_flag_only_those_asking_for_action():
    workers = [{"dispatchId": "ctx_a", "runId": "run_x", "projection": {"attention": {"requiresAction": True,
                                                                                      "categories": ["permission"]}}},
               {"dispatchId": "ctx_b", "runId": "run_x", "projection": {"attention": {"requiresAction": False}}}]
    assert hb.orca_workers(workers, {"run_x": "FLD"}) == {"worker:ctx_a": 'An Orca worker in "FLD" is stuck: permission'}
