import io
import json

from agent_annotate.providers import codex_app_server


class FakeProcess:
    def __init__(self, responses):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in responses))
        self.stderr = io.StringIO()
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode


def test_app_server_client_initializes_and_lists_threads(monkeypatch):
    process = FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "test"}},
            {"id": 2, "result": {"data": [{"id": "thread-1"}]}},
        ]
    )
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)

    with codex_app_server.CodexAppServerClient() as client:
        result = client.request("thread/list", {"limit": 1})

    assert result["data"][0]["id"] == "thread-1"
    written = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert written[0]["method"] == "initialize"
    assert written[1]["method"] == "initialized"
    assert written[2]["method"] == "thread/list"


def test_delivery_resumes_durable_thread_before_starting_turn(monkeypatch):
    process = FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "test"}},
            {"id": 2, "result": {"thread": {"id": "thread-1", "turns": []}}},
            {"id": 3, "result": {"turn": {"id": "turn-1"}}},
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "turn-1", "status": "completed"}},
            },
        ]
    )
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)

    result = codex_app_server.CodexAppServerAdapter().deliver("thread-1", "Coordinate work")

    assert result.delivered is True
    assert result.detail == "completed turn turn-1 (completed)"
    written = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert written[2] == {"method": "thread/resume", "id": 2, "params": {"threadId": "thread-1"}}
    assert written[3]["method"] == "turn/start"
