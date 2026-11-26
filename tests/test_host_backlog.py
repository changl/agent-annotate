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
        msg("f3", 30, thread_id="m3"),                                 # the worker's own follow-up: not an answer
    ]
    got = hb.orca_mail(mail, {"ctx_live": "run_x"}, {"run_x": "Rebex"}, NOW)
    assert sorted(got) == ["question:m3", "unread:m1"]
    assert "Rebex" in got["question:m3"]


def test_workers_flag_only_those_asking_for_action():
    workers = [{"dispatchId": "ctx_a", "runId": "run_x", "projection": {"attention": {"requiresAction": True,
                                                                                      "categories": ["permission"]}}},
               {"dispatchId": "ctx_b", "runId": "run_x", "projection": {"attention": {"requiresAction": False}}}]
    assert hb.orca_workers(workers, {"run_x": "FLD"}) == {"worker:ctx_a": 'An Orca worker in "FLD" is stuck: permission'}


def test_reading_takes_the_sample_and_tells_slow_from_asleep():
    # Live mac-admit line, 2026-11-26: the reason and the after-starts figures count a reservation, not load.
    assert hb.reading("wait M1Max: cpu idle 12% < 20% (1 recent starts reserved) (cpu idle 52%, memory free 82%, "
                      "disk free 96 GB, 10 cores; after 1 recent starts: cpu idle 12%, memory free 76%)"
                      ) == {"idle": 52.0, "memory": 82.0, "hot": False}
    assert hb.reading("admit M1Max: cpu idle 59%, memory free 82%, disk free 98 GB, "
                      "8 of 10 cores (macOS switched the rest off: too hot), room 1.9 cores")["hot"] is True
    assert hb.reading("stop M1Max16: ssh_host_or_probe_timeout:M1Max16")["idle"] is None
    assert hb.reading("wait M1Max16: its load sample failed (host_probe_failed:M1Max16)")["idle"] is None
    assert hb.reading("stop M5Max: ssh_host_offline_or_asleep:M5Max") is None
    assert hb.reading("") is None


def test_families_sum_cpu_by_command_and_count_simulators_as_one():
    ps = ("  320.0 /Library/Developer/CoreSimulator/Volumes/iOS/Runtimes/iOS 26.simruntime/RuntimeRoot/SpringBoard\n"
          "  330.0 /Library/Developer/CoreSimulator/Volumes/iOS/Runtimes/iOS 26.simruntime/RuntimeRoot/backboardd\n"
          "  107.0 /usr/sbin/fseventsd\n   10.0 /usr/libexec/secd\n  garbage\n")
    assert hb.families(ps) == "iOS simulators about 6.5 cores (2 processes), fseventsd about 1.1 cores (1 process)"


def test_a_mac_is_reported_after_30_busy_minutes_and_a_gap_restarts_its_clock():
    busy, fine = {"idle": 5.0, "memory": 60.0, "hot": False}, {"idle": 50.0, "memory": 60.0, "hot": False}
    asked = []

    def census(mac):
        asked.append(mac)
        return "fseventsd about 1.1 cores (1 process)"
    state = {"M1Max16": {"since": ago(40), "last": ago(10)},  # busy since 40 min, seen 10 min ago
             "M5Max": {"since": ago(300), "last": ago(200)},  # an old run: asleep since
             "M1Max": {"since": ago(40), "last": ago(10)}}
    got, following = hb.pressure({"M1Max16": busy, "M5Max": busy, "M1Max": fine}, state, NOW, census)
    assert list(got) == ["mac:M1Max16"] and asked == ["M1Max16"]
    assert got["mac:M1Max16"].startswith("The M1Max16 has been over 80% busy for 40 min (CPU 95% busy")
    assert following == {"M1Max16": {"since": ago(40), "last": ago(0)}, "M5Max": {"since": ago(0), "last": ago(0)}}
    slow = {"idle": None, "memory": None, "hot": False}
    got, _ = hb.pressure({"M1Max16": slow, "M5Max": None}, state, NOW, lambda mac: "")
    assert got == {"mac:M1Max16": "The M1Max16 has been over 80% busy for 40 min (too busy to answer its load check)"}
    full_memory = {"idle": 60.0, "memory": 15.0, "hot": True}
    got, _ = hb.pressure({"M1Max": full_memory}, state, NOW, lambda mac: "")
    assert "memory 85% used, running hot" in got["mac:M1Max"]
