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


def sample(mac, idle, minutes_ago=0.0, memory=60, cores=10, all_cores=10, load=1.0):
    """One Mac as `mac-admit --json` prints it."""
    at = (NOW - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return {"target": mac, "cores": cores, "all_cores": all_cores, "thresholds": {"max_load_per_core": 2.5},
            "sample": {"cpu_idle_percent": idle, "memory_free_percent": memory, "load_per_core": load,
                       "observed_at": at}}


def runs(observations, state=None, census=lambda macs: {}):
    """Feed successive mac-admit outputs through pressure(); returns each run's problems and the last state."""
    state, seen = state or {}, []
    for observed in observations:
        got, state = hb.pressure({o["target"]: hb.reading(o) for o in observed}, state, NOW, census,
                                 hb.load_limit(observed))
        seen.append(got)
    return seen, state


OVER = "over its limits (80% CPU or memory, load 2.5 per core)"


def test_reading_keeps_the_measured_figures_and_the_failure_kind():
    assert hb.reading(sample("M1Max", 20.4)) == {"kind": "measured", "idle": 20.4, "memory": 60.0, "load": 1.0,
                                                 "hot": False, "at": NOW.isoformat()}
    assert hb.reading(sample("M1Max", 50, cores=6))["hot"] is True
    assert hb.reading(sample("M1Max", 50, load=None))["load"] is None
    assert hb.reading(sample("M1Max", 50, load=float("nan")))["load"] is None
    for slow in ("ssh_host_or_probe_timeout:M1Max16", "host_probe_failed:M1Max16", "host_probe_timeout:M1Max",
                 "sample_unreadable:M1Max16"):
        assert hb.reading({"target": "M1Max16", "error": slow})["kind"] == "slow"
    assert hb.reading(sample("M5Max", float("nan")))["kind"] == "slow"
    assert hb.reading({"target": "M5Max", "error": "ssh_host_offline_or_asleep:M5Max"}) == {"kind": "asleep"}
    assert hb.reading({"target": "M5Max", "error": "ssh_login_refused:M5Max"})["kind"] == "unreachable"


def test_families_sum_cpu_by_command_and_count_simulators_as_one():
    ps = ("  320.0 /Library/Developer/CoreSimulator/Volumes/iOS/Runtimes/iOS 26.simruntime/RuntimeRoot/SpringBoard\n"
          "  330.0 /Library/Developer/CoreSimulator/Volumes/iOS/Runtimes/iOS 26.simruntime/RuntimeRoot/backboardd\n"
          "  107.0 /usr/sbin/fseventsd\n   10.0 /usr/libexec/secd\n  garbage\n")
    assert hb.families(ps) == "iOS simulators about 6.5 cores (2 processes), fseventsd about 1.1 cores (1 process)"


def test_load_per_core_makes_a_mac_busy_under_80_percent_cpu():
    # The M1Max16, 2026-11-27: about 75% CPU and 68% memory free, yet load 15.6 per core and swapping.
    seen, _ = runs([[sample("M1Max16", 25, minutes_ago=m, memory=68, load=15)] for m in (30, 20, 10, 0)])
    assert seen[:3] == [{}, {}, {}]
    assert seen[3] == {"busy:M1Max16": f"The M1Max16 has been {OVER} for 30 min (now CPU 75% busy, memory 32% used, "
                                       "load 15.0 per core)"}
    seen, _ = runs([[sample("M1Max16", 25, minutes_ago=m, memory=68, load=1)] for m in (30, 20, 10, 0)])
    assert seen[3] == {}


def test_the_load_limit_is_the_m1_max_admission_limit():
    loose = {**sample("M1Max16", 50), "thresholds": {"max_load_per_core": 1000}}  # its own config never refuses tests
    assert hb.load_limit([loose, {**sample("M1Max", 50), "thresholds": {"max_load_per_core": 4}}]) == 4
    assert hb.load_limit([loose, {"target": "M1Max", "error": "ssh_host_offline_or_asleep:M1Max"}]) == hb.LOAD_PER_CORE


def test_memory_users_pick_the_largest_commands():
    ps = (" 22964000 /System/Library/Frameworks/CoreServices.framework/Versions/A/Support/fseventsd\n"
          "  900000 /usr/libexec/secd\n 1500000 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n"
          " 1500000 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n  junk\n")
    assert hb.memory_users(ps) == "fseventsd 23.5 GB, Google Chrome 3.1 GB (2 processes)"


def test_census_names_cpu_and_memory_users_within_its_time(monkeypatch):
    asked = []

    def run(command, timeout):
        asked.append((command, timeout))
        return " 300.0 /usr/bin/rustc\n" if "pcpu=,comm=" in command else " 22964000 /usr/sbin/fseventsd\n"
    monkeypatch.setattr(hb, "_run", run)
    assert hb.census(["M1Max16", "Elsewhere"]) == {
        "M1Max16": "using the most CPU: rustc about 3.0 cores (1 process); the most memory: fseventsd 23.5 GB"}
    assert [command[-1] for command, _ in asked] == ["pcpu=,comm=", "rss=,comm="]
    assert all(command[:-3] == hb.PS["M1Max16"] and timeout <= hb.CENSUS_S for command, timeout in asked)


def test_the_clock_uses_the_sample_times_and_the_measured_idle():
    asked = []

    def census(macs):
        asked.extend(macs)
        return {mac: "using the most CPU: rustc about 3.0 cores (3 processes)" for mac in macs}
    # Sampled 30.5, 20.5, 10.5 and 0.5 min ago: 30 min apart by the Mac's clock, though the runs spanned 30.5.
    seen, _ = runs([[sample("M1Max16", 5, minutes_ago=m)] for m in (30.5, 20.5, 10.5, 0.5)], census=census)
    assert seen[:3] == [{}, {}, {}] and asked == ["M1Max16"]
    assert seen[3] == {"busy:M1Max16": f"The M1Max16 has been {OVER} for 30 min (now CPU 95% busy, memory 40% "
                                      "used, load 1.0 per core); using the most CPU: rustc about 3.0 cores (3 processes)"}
    seen, _ = runs([[sample("M1Max16", 5, minutes_ago=m)] for m in (29.5, 20, 10, 0.5)])
    assert seen[3] == {}  # 29 min by the sample times
    seen, _ = runs([[sample("M1Max", 20.4, minutes_ago=m)] for m in (40, 30, 20, 10, 0)])
    assert seen[-1] == {}  # 79.6% busy is under the line even though mac-admit prints it as 20% idle
    seen, _ = runs([[sample("M1Max", 60, memory=15, cores=6, minutes_ago=m)] for m in (30, 20, 10, 0)])
    assert "memory 85% used, load 1.0 per core, running hot" in seen[-1]["busy:M1Max"]


def test_failed_probes_never_read_as_measured_load():
    slow = {"target": "M1Max16", "error": "ssh_host_or_probe_timeout:M1Max16"}
    asked = []
    seen, state = runs([[slow]] * 4, census=lambda macs: asked.extend(macs) or {})
    assert seen == [{}] * 4 and state["M1Max16"]["checks"] == 4 and state["M1Max16"]["busy"] == 0
    # A slow sample has no sample time of its own, so it counts at the run's time; spread over 30 min:
    state = {"M1Max16": {"since": ago(30), "last": ago(10), "checks": 3, "busy": 0}}
    seen, _ = runs([[slow]], state=state, census=lambda macs: asked.extend(macs) or {})
    assert seen[0] == {"quiet:M1Max16": "The M1Max16 has not answered its load check for 30 min"} and asked == []
    mixed = {"M1Max16": {"since": ago(30), "last": ago(10), "checks": 3, "busy": 1}}
    seen, _ = runs([[sample("M1Max16", 1)]], state=mixed)
    assert seen[0]["busy:M1Max16"].startswith(f"The M1Max16 has been {OVER} whenever it answered for 30 min "
                                              "(busy in 2 of 4 checks, the others did not answer; now CPU 99% busy")


def test_a_refused_check_inside_a_busy_run_is_counted_not_hidden():
    refused = {"target": "M1Max16", "error": "ssh_login_refused:M1Max16"}
    seen, state = runs([[sample("M1Max16", 5, minutes_ago=30)], [sample("M1Max16", 5, minutes_ago=20)], [refused],
                        [sample("M1Max16", 5, minutes_ago=0)]])
    assert seen[2] == {"reach:M1Max16": "The host check cannot sample the M1Max16: its SSH login was refused"}
    assert seen[3] == {"busy:M1Max16": f"The M1Max16 has been {OVER} whenever it answered for 30 min (busy in "
                                       "3 of 4 checks, the others did not answer; now CPU 95% busy, memory 40% used, "
                                       "load 1.0 per core)"}
    # A long refusal outlasts the gap, so the next answer starts a new clock.
    seen, _ = runs([[refused]] * 5 + [[sample("M1Max16", 5)]],
                   state={"M1Max16": {"since": ago(60), "last": ago(50), "checks": 2, "busy": 2}})
    assert seen[-1] == {}


def test_asleep_restarts_the_clock_and_a_refused_login_is_reported_and_keeps_it():
    state = {mac: {"since": ago(40), "last": ago(10), "checks": 4, "busy": 4} for mac in ("M5Max", "M1Max16")}
    got, following = hb.pressure({"M5Max": {"kind": "asleep"},
                                  "M1Max16": hb.reading({"target": "M1Max16", "error": "ssh_login_refused:M1Max16"})},
                                 state, NOW, lambda macs: {})
    assert got == {"reach:M1Max16": "The host check cannot sample the M1Max16: its SSH login was refused"}
    assert following == {"M1Max16": {**state["M1Max16"], "checks": 5}}
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
    monkeypatch.setattr(hb, "queues", lambda now, end: {"send:reviews/a": "waiting"})
    got = hb.collect(NOW)
    assert got["send:reviews/a"] == "waiting" and got["macs:unreadable"].startswith("The host check could not sample")
    assert hb.PRESSURE.read_text() == clocks
    monkeypatch.setattr(hb, "sample_macs", lambda: [sample("M1Max", 5), sample("M5Max", 50), sample("M1Max16", 50)])
    monkeypatch.setattr(hb, "census", lambda macs: {})
    assert hb.collect(NOW) == {"send:reviews/a": "waiting"}  # 20 min of a 30 min run so far
    assert json.loads(hb.PRESSURE.read_text())["M1Max"]["checks"] == 3
    assert [p.name for p in tmp_path.iterdir()] == ["pressure.json"]  # written whole, no partial left


def test_a_mac_that_mac_admit_leaves_out_is_reported_and_keeps_its_clock(tmp_path, monkeypatch):
    monkeypatch.setattr(hb, "PRESSURE", tmp_path / "pressure.json")
    hb.PRESSURE.write_text(json.dumps({"M1Max16": {"since": ago(20), "last": ago(10), "checks": 2, "busy": 2}}))
    monkeypatch.setattr(hb, "queues", lambda now, end: {})
    monkeypatch.setattr(hb, "sample_macs", lambda: [sample("M1Max", 50), sample("M5Max", 50)])
    assert hb.collect(NOW) == {"reach:M1Max16": "The host check cannot sample the M1Max16: "
                                                "it is not in the wm-test config"}
    assert json.loads(hb.PRESSURE.read_text())["M1Max16"]["checks"] == 3


def test_orca_reads_stop_at_the_deadline_and_keep_what_they_read(tmp_path, monkeypatch):
    try:
        hb._orca(hb.time.monotonic(), "run-list")
        raise AssertionError("read past the deadline")
    except TimeoutError:
        pass
    monkeypatch.setattr(hb, "DELIVERIES", tmp_path)
    stuck = {"dispatchId": "ctx_a", "runId": "run_x", "projection": {"attention": {"requiresAction": True}}}
    answers = {"run-list": {"runs": [{"id": "run_x", "objective": "FLD"}]}, "worker-list": {"workers": [stuck]}}

    def orca(end, command, *rest):
        if command not in answers or "--cursor" in rest:
            raise TimeoutError("out of time")
        return answers[command]
    monkeypatch.setattr(hb, "_orca", orca)
    expected = {"worker:ctx_a": 'An Orca worker in "FLD" is stuck: needs action',
                "orca:unreadable": "The host check could not read Orca: TimeoutError"}
    assert hb.queues(NOW, 0) == expected  # the mail read ran out of time
    answers["worker-list"] = {"workers": [stuck], "page": {"nextCursor": "c2"}}
    assert hb.queues(NOW, 0) == expected  # the second page ran out of time
