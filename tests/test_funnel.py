import copy
from types import SimpleNamespace

import pytest

from agent_annotate.transports import funnel


def test_publish_adds_one_path_and_keeps_every_existing_handler(monkeypatch):
    state = {"TCP": {"443": {"HTTPS": True}}, "AllowFunnel": {"host.ts.net:443": True},
             "Web": {"host.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:9999"}}}}}
    before = copy.deepcopy(state)
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: copy.deepcopy(state))
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "host.ts.net")
    commands = []
    def run(command):
        commands.append(command)
        state["Web"]["host.ts.net:443"]["Handlers"]["/annotate/project/workspace"] = {"Proxy": command[-1]}
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(funnel.ts, "_run", run)
    result = funnel.publish("annotate/project/workspace", 8800)
    assert result["url"] == "https://host.ts.net/annotate/project/workspace/"
    assert state["Web"]["host.ts.net:443"]["Handlers"]["/"] == before["Web"]["host.ts.net:443"]["Handlers"]["/"]
    assert commands[0][-2:] == ["--set-path=/annotate/project/workspace", "http://127.0.0.1:8800/annotate/project/workspace"]
    funnel.publish("annotate/project/workspace", 8800)
    assert len(commands) == 1


def test_refuses_to_expose_private_ports_or_replace_foreign_paths(monkeypatch):
    state = {"TCP": {str(p): {"HTTPS": True} for p in (443, 8443, 10000)}}
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: state)
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "host.ts.net")
    monkeypatch.setattr(funnel.ts, "_run", lambda *args: pytest.fail("unsafe mutation"))
    with pytest.raises(RuntimeError, match="private services"):
        funnel.publish("page", 8800)
    state.update(AllowFunnel={"host.ts.net:443": True}, Web={"host.ts.net:443": {"Handlers": {"/page": {"Proxy": "http://127.0.0.1:9999/page"}}}})
    with pytest.raises(RuntimeError, match="another origin"):
        funnel.publish("page", 8800)


def test_teardown_requires_exact_path_and_origin(monkeypatch):
    state = {"Web": {"host.ts.net:443": {"Handlers": {"/page": {"Proxy": "http://127.0.0.1:9999/page"}}}}}
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: state)
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "host.ts.net")
    monkeypatch.setattr(funnel.ts, "_run", lambda *args: pytest.fail("unsafe teardown"))
    with pytest.raises(RuntimeError, match="another origin"):
        funnel.unpublish("page", https_port=443, port=8800)


def test_teardown_refuses_stale_hostname_before_touching_current_foreign_handler(monkeypatch):
    state = {"Web": {
        "old.ts.net:443": {"Handlers": {"/page": {"Proxy": "http://127.0.0.1:8800/page"}}},
        "new.ts.net:443": {"Handlers": {"/page": {"Proxy": "http://127.0.0.1:9999/page"}}},
    }}
    before = copy.deepcopy(state)
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: copy.deepcopy(state))
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "new.ts.net")
    monkeypatch.setattr(funnel.ts, "_run", lambda *args: pytest.fail("stale hostname must not mutate any route"))
    with pytest.raises(RuntimeError, match="hostname changed; no route changed"):
        funnel.unpublish("page", hostname="old.ts.net", https_port=443, port=8800)
    assert state == before


def test_teardown_of_absent_path_is_safe_and_accepted_by_cli(monkeypatch):
    state = {"Web": {"host.ts.net:443": {"Handlers": {
        "/other": {"Proxy": "http://127.0.0.1:9999/other"}}}}}
    before = copy.deepcopy(state)
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: state)
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "host.ts.net")
    monkeypatch.setattr(funnel.ts, "_run", lambda *args: pytest.fail("unnecessary teardown"))
    result = funnel.unpublish("page", https_port=443, port=8800)
    assert result["ok"] is True
    assert result["details"]["action"] == "noop"
    assert result["details"]["reason"].startswith("no serve mapping")
    assert state == before


def test_teardown_removes_only_owned_path(monkeypatch):
    state = {"AllowFunnel": {"host.ts.net:443": True},
             "Web": {"host.ts.net:443": {"Handlers": {
                 "/page": {"Proxy": "http://127.0.0.1:8800/page"},
                 "/other": {"Proxy": "http://127.0.0.1:9999/other"}}}}}
    other = copy.deepcopy(state["Web"]["host.ts.net:443"]["Handlers"]["/other"])
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: copy.deepcopy(state))
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "host.ts.net")
    commands = []

    def run(command):
        commands.append(command)
        del state["Web"]["host.ts.net:443"]["Handlers"]["/page"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(funnel.ts, "_run", run)
    result = funnel.unpublish("page", https_port=443, port=8800)
    assert result["details"]["action"] == "removed"
    assert commands == [[funnel.ts._binary({}), "serve", "--https=443", "--set-path=/page", "off"]]
    assert state["Web"]["host.ts.net:443"]["Handlers"]["/other"] == other
    assert state["AllowFunnel"] == {"host.ts.net:443": True}


def test_republish_keeps_recorded_public_port_and_updates_only_owned_origin(monkeypatch):
    state = {"TCP": {"10000": {"HTTPS": True}},
             "AllowFunnel": {"host.ts.net:10000": True},
             "Web": {"host.ts.net:10000": {"Handlers": {
                 "/page": {"Proxy": "http://127.0.0.1:8800/page"},
                 "/other": {"Proxy": "http://127.0.0.1:9999/other"}}}}}
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: copy.deepcopy(state))
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "host.ts.net")
    commands = []

    def run(command):
        commands.append(command)
        state["Web"]["host.ts.net:10000"]["Handlers"]["/page"] = {"Proxy": command[-1]}
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(funnel.ts, "_run", run)
    previous = {"port": 8800, "details": {"transport": "funnel", "hostname": "host.ts.net",
                                         "https_port": 10000, "path": "/page"}}
    result = funnel.publish("page", 8801, previous=previous)
    assert result["url"] == "https://host.ts.net:10000/page/"
    assert len(commands) == 1 and "--https=10000" in commands[0]
    assert set(state["Web"]) == {"host.ts.net:10000"}
    assert state["Web"]["host.ts.net:10000"]["Handlers"]["/other"] == {"Proxy": "http://127.0.0.1:9999/other"}


def test_explicit_route_move_removes_old_owned_path_and_preserves_other_routes(monkeypatch):
    state = {"TCP": {"10000": {"HTTPS": True}},
             "AllowFunnel": {"host.ts.net:10000": True},
             "Web": {"host.ts.net:10000": {"Handlers": {
                 "/old-page": {"Proxy": "http://127.0.0.1:8800/old-page"},
                 "/other": {"Proxy": "http://127.0.0.1:9999/other"}}}}}
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: copy.deepcopy(state))
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "host.ts.net")

    def run(command):
        port = next(value.split("=", 1)[1] for value in command if value.startswith("--https="))
        path = next(value.split("=", 1)[1] for value in command if value.startswith("--set-path="))
        handlers = state.setdefault("Web", {}).setdefault(f"host.ts.net:{port}", {}).setdefault("Handlers", {})
        if command[-1] == "off":
            del handlers[path]
        else:
            handlers[path] = {"Proxy": command[-1]}
            state["AllowFunnel"][f"host.ts.net:{port}"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(funnel.ts, "_run", run)
    previous = {"port": 8800, "details": {"transport": "funnel", "hostname": "host.ts.net",
                                         "https_port": 10000, "path": "/old-page"}}
    result = funnel.publish("new-page", 8801, previous=previous, funnel_port=443)
    assert result["url"] == "https://host.ts.net/new-page/"
    assert state["Web"]["host.ts.net:443"]["Handlers"] == {"/new-page": {"Proxy": "http://127.0.0.1:8801/new-page"}}
    assert state["Web"]["host.ts.net:10000"]["Handlers"] == {"/other": {"Proxy": "http://127.0.0.1:9999/other"}}


@pytest.mark.parametrize("public,origin,error", [
    (True, "http://127.0.0.1:9999/page", "ownership changed"),
    (False, "http://127.0.0.1:8800/page", "private"),
])
def test_republish_refuses_changed_previous_ownership_or_private_port(monkeypatch, public, origin, error):
    state = {"TCP": {"10000": {"HTTPS": True}},
             "AllowFunnel": {"host.ts.net:10000": public},
             "Web": {"host.ts.net:10000": {"Handlers": {"/page": {"Proxy": origin}}}}}
    monkeypatch.setattr(funnel.ts, "_serve_state", lambda binary: state)
    monkeypatch.setattr(funnel.ts, "_hostname", lambda *args: "host.ts.net")
    monkeypatch.setattr(funnel.ts, "_run", lambda *args: pytest.fail("unsafe republish"))
    previous = {"port": 8800, "details": {"transport": "funnel", "hostname": "host.ts.net",
                                         "https_port": 10000, "path": "/page"}}
    with pytest.raises(RuntimeError, match=error):
        funnel.publish("page", 8801, previous=previous)
