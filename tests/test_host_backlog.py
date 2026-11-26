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


def sample(mac, idle, minutes_ago=0.0, memory=60, cores=10, all_cores=10):
    """One Mac as `mac-admit --json` prints it."""
    at = (NOW - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return {"target": mac, "cores": cores, "all_cores": all_cores,
            "sample": {"cpu_idle_percent": idle, "memory_free_percent": memory, "observed_at": at}}


def runs(observations, state=None, census=lambda macs: {}):
    """Feed successive mac-admit outputs through pressure(); returns each run's problems and the last state."""
    state, seen = state or {}, []
    for observed in observations:
        got, state = hb.pressure({o["target"]: hb.reading(o) for o in observed}, state, NOW, census)
        seen.append(got)
    return seen, state


def test_reading_keeps_the_measured_figures_and_the_failure_kind():
    assert hb.reading(sample("M1Max", 20.4)) == {"kind": "measured", "idle": 20.4, "memory": 60.0, "hot": False,
                                                 "at": NOW.isoformat()}
    assert hb.reading(sample("M1Max", 50, cores=6))["hot"] is True
    for slow in ("ssh_host_or_probe_timeout:M1Max16", "host_probe_failed:M1Max16"):
        assert hb.reading({"target": "M1Max16", "error": slow})["kind"] == "slow"
    assert hb.reading(sample("M5Max", float("nan")))["kind"] == "slow"
    assert hb.reading({"target": "M5Max", "error": "ssh_host_offline_or_asleep:M5Max"}) == {"kind": "asleep"}
    assert hb.reading({"target": "M5Max", "error": "ssh_login_refused:M5Max"})["kind"] == "unreachable"


def test_families_sum_cpu_by_command_and_count_simulators_as_one():
    ps = ("  320.0 /Library/Developer/CoreSimulator/Volumes/iOS/Runtimes/iOS 26.simruntime/RuntimeRoot/SpringBoard\n"
          "  330.0 /Library/Developer/CoreSimulator/Volumes/iOS/Runtimes/iOS 26.simruntime/RuntimeRoot/backboardd\n"
          "  107.0 /usr/sbin/fseventsd\n   10.0 /usr/libexec/secd\n  garbage\n")
    assert hb.families(ps) == "iOS simulators about 6.5 cores (2 processes), fseventsd about 1.1 cores (1 process)"


def test_the_clock_uses_the_sample_times_and_the_measured_idle():
    asked = []

    def census(macs):
        asked.extend(macs)
        return {mac: "rustc about 3.0 cores (3 processes)" for mac in macs}
    # Sampled 30.5, 20.5, 10.5 and 0.5 min ago: 30 min apart by the Mac's clock, though the runs spanned 30.5.
    seen, _ = runs([[sample("M1Max16", 5, minutes_ago=m)] for m in (30.5, 20.5, 10.5, 0.5)], census=census)
    assert seen[:3] == [{}, {}, {}] and asked == ["M1Max16"]
    assert seen[3] == {"mac:M1Max16": "The M1Max16 has been over 80% busy for 30 min (now CPU 95% busy, memory 40% "
                                      "used); using the most CPU: rustc about 3.0 cores (3 processes)"}
    seen, _ = runs([[sample("M1Max16", 5, minutes_ago=m)] for m in (29.5, 20, 10, 0.5)])
    assert seen[3] == {}  # 29 min by the sample times
    seen, _ = runs([[sample("M1Max", 20.4, minutes_ago=m)] for m in (40, 30, 20, 10, 0)])
    assert seen[-1] == {}  # 79.6% busy is under the line even though mac-admit prints it as 20% idle
    seen, _ = runs([[sample("M1Max", 60, memory=15, cores=6, minutes_ago=m)] for m in (30, 20, 10, 0)])
    assert "memory 85% used, running hot" in seen[-1]["mac:M1Max"]


def test_failed_probes_never_read_as_measured_load():
    slow = {"target": "M1Max16", "error": "ssh_host_or_probe_timeout:M1Max16"}
    asked = []
    seen, state = runs([[slow]] * 4, census=lambda macs: asked.extend(macs) or {})
    assert seen == [{}] * 4 and state["M1Max16"]["checks"] == 4 and state["M1Max16"]["busy"] == 0
    # A slow sample has no sample time of its own, so it counts at the run's time; spread over 30 min:
    state = {"M1Max16": {"since": ago(30), "last": ago(10), "checks": 3, "busy": 0}}
    seen, _ = runs([[slow]], state=state, census=lambda macs: asked.extend(macs) or {})
    assert seen[0] == {"mac:M1Max16": "The M1Max16 has not answered its load check for 30 min"} and asked == []
    mixed = {"M1Max16": {"since": ago(30), "last": ago(10), "checks": 3, "busy": 1}}
    seen, _ = runs([[sample("M1Max16", 1)]], state=mixed)
    assert seen[0]["mac:M1Max16"].startswith("The M1Max16 has been over 80% busy or too busy to answer for 30 min "
                                             "(measured busy in 2 of 4 checks; now CPU 99% busy")


def test_asleep_restarts_the_clock_and_a_refused_login_is_reported_and_keeps_it():
    state = {mac: {"since": ago(40), "last": ago(10), "checks": 4, "busy": 4} for mac in ("M5Max", "M1Max16")}
    got, following = hb.pressure({"M5Max": {"kind": "asleep"},
                                  "M1Max16": hb.reading({"target": "M1Max16", "error": "ssh_login_refused:M1Max16"})},
                                 state, NOW, lambda macs: {})
    assert got == {"mac:M1Max16": "The host check cannot sample the M1Max16: its SSH login was refused"}
    assert following == {"M1Max16": state["M1Max16"]}
    # A record older than two runs restarts the clock rather than alerting on one sample.
    seen, _ = runs([[sample("M5Max", 0)]], state={"M5Max": {"since": ago(300), "last": ago(200), "checks": 9, "busy": 9}})
    assert seen == [{}]


def test_unusable_state_restarts_only_what_it_held(tmp_path):
    path = tmp_path / "pressure.json"
    path.write_text("[]")
    assert hb.load_state(path) == {}
    good = {"since": ago(20), "last": ago(10), "checks": 2, "busy": 2}
    path.write_text(json.dumps({"M1Max": good, "M5Max": {"since": "yesterday"}, "M1Max16": [],
                                "X": {**good, "busy": 5}, "Y": {**good, "last": "2026-11-26T08:00:00"}}))
    assert hb.load_state(path) == {"M1Max": good}


def test_a_failed_mac_check_keeps_the_queue_report_and_the_clocks(tmp_path, monkeypatch):
    clocks = json.dumps({"M1Max": {"since": ago(20), "last": ago(10), "checks": 2, "busy": 2}})
    monkeypatch.setattr(hb, "PRESSURE", tmp_path / "pressure.json")
    hb.PRESSURE.write_text(clocks)
    monkeypatch.setattr(hb, "MAC_ADMIT", tmp_path / "missing-mac-admit")
    monkeypatch.setattr(hb, "queues", lambda now: {"send:reviews/a": "waiting"})
    got = hb.collect(NOW)
    assert got["send:reviews/a"] == "waiting" and got["macs:unreadable"].startswith("The host check could not sample")
    assert hb.PRESSURE.read_text() == clocks
    monkeypatch.setattr(hb, "sample_macs", lambda: [sample("M1Max", 5)])
    monkeypatch.setattr(hb, "census", lambda macs: {})
    assert hb.collect(NOW) == {"send:reviews/a": "waiting"}  # 20 min of a 30 min run so far
    assert json.loads(hb.PRESSURE.read_text())["M1Max"]["checks"] == 3
    assert [p.name for p in tmp_path.iterdir()] == ["pressure.json"]  # written whole, no partial left
