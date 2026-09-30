import io
import json
import os
import subprocess
import sys
import time

import pytest

from agent_annotate.providers import codex_app_server


class RecordingInput(io.StringIO):
    def close(self):
        if not self.closed:
            self.written = super().getvalue()
        super().close()

    def getvalue(self):
        return self.written if self.closed else super().getvalue()


class FakeProcess:
    def __init__(self, responses, *, hold_pipes=False, ignore_terminate=False):
        self.writers = []
        self.stdin = RecordingInput()
        self.stdout = self.pipe(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in responses), hold_pipes
        )
        self.stderr = self.pipe("", hold_pipes)
        self.returncode = None
        self.ignore_terminate = ignore_terminate
        self.terminated = False
        self.killed = False
        self.waits = []

    def pipe(self, text, held):
        reader, writer = os.pipe()
        os.write(writer, text.encode())
        if held:
            self.writers.append(writer)
        else:
            os.close(writer)
        return os.fdopen(reader, "r")

    def close_writers(self):
        for writer in self.writers:
            os.close(writer)
        self.writers.clear()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        if not self.ignore_terminate:
            self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.returncode is None:
            raise subprocess.TimeoutExpired("inert fixture", timeout)
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
    assert written[0]["params"]["clientInfo"]["version"] == codex_app_server.__version__
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


def inert_server(monkeypatch, script):
    """Replace only the app-server process with a local stdlib Python fixture."""
    real_popen = subprocess.Popen
    processes = []

    def start(*_args, **kwargs):
        process = real_popen(
            [sys.executable, "-u", "-c", script],
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            **kwargs,
        )
        processes.append(process)
        return process

    monkeypatch.setattr(codex_app_server.subprocess, "Popen", start)
    return processes


def assert_released(process):
    assert process.poll() is not None
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))


def test_constructor_failure_reaps_process_and_closes_pipes(monkeypatch):
    process = FakeProcess([{"id": 1, "error": {"message": "fixture initialize failure"}}])
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(codex_app_server.AppServerError, match="fixture initialize failure"):
        codex_app_server.CodexAppServerClient()
    assert process.terminated
    assert process.waits == [2]
    assert_released(process)


@pytest.mark.parametrize("fail_at", [0, 1])
def test_reader_start_failure_also_releases_subprocess(monkeypatch, fail_at):
    process = FakeProcess([])
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)

    start = codex_app_server.threading.Thread.start
    started = 0

    def fail_start(thread):
        nonlocal started
        index = started
        started += 1
        if index == fail_at:
            raise RuntimeError("fixture thread start failure")
        return start(thread)

    monkeypatch.setattr(codex_app_server.threading.Thread, "start", fail_start)
    with pytest.raises(RuntimeError, match="fixture thread start failure"):
        codex_app_server.CodexAppServerClient()
    assert_released(process)


def test_initialized_notification_failure_releases_subprocess(monkeypatch):
    process = FakeProcess([{"id": 1, "result": {}}])
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)
    flush = process.stdin.flush
    flushes = 0

    def fail_notification_flush():
        nonlocal flushes
        flushes += 1
        if flushes == 2:
            raise BrokenPipeError("fixture initialized failure")
        return flush()

    monkeypatch.setattr(process.stdin, "flush", fail_notification_flush)
    with pytest.raises(BrokenPipeError, match="fixture initialized failure"):
        codex_app_server.CodexAppServerClient()
    assert_released(process)


def test_initialization_timeout_releases_inert_process(monkeypatch):
    processes = inert_server(monkeypatch, "import time; time.sleep(60)")
    started = time.monotonic()
    with pytest.raises(codex_app_server.AppServerError, match="timed out"):
        codex_app_server.CodexAppServerClient(request_timeout=0.05)
    assert time.monotonic() - started < 2
    assert_released(processes[0])


def test_stderr_flood_without_newlines_cannot_block_initialization(monkeypatch):
    processes = inert_server(
        monkeypatch,
        "import json, sys\n"
        "sys.stderr.buffer.write(b'x' * (1024 * 1024)); sys.stderr.buffer.flush()\n"
        "request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': request['id'], 'result': {}}), flush=True)\n"
        "for line in sys.stdin: pass\n",
    )
    with codex_app_server.CodexAppServerClient(request_timeout=3) as client:
        with client._stderr_lock:
            assert 0 < len(client._stderr_tail) <= 8192
    assert_released(processes[0])


def test_stdout_eof_does_not_wait_for_stderr_eof(monkeypatch):
    processes = inert_server(
        monkeypatch,
        "import json, os, sys, time\n"
        "request = json.loads(sys.stdin.readline())\n"
        "sys.stderr.write('fixture diagnostic without newline'); sys.stderr.flush()\n"
        "print(json.dumps({'id': request['id'], 'result': {}}), flush=True)\n"
        "os.close(1)\n"
        "time.sleep(60)\n",
    )
    with codex_app_server.CodexAppServerClient(request_timeout=3) as client:
        started = time.monotonic()
        with pytest.raises(codex_app_server.AppServerError, match="stopped unexpectedly"):
            client.request("fixture", {}, timeout=0.2)
        assert time.monotonic() - started < 1
    assert_released(processes[0])


def test_close_does_not_wait_for_inherited_pipe_eof_and_is_idempotent(monkeypatch):
    process = FakeProcess([{"id": 1, "result": {}}], hold_pipes=True)
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)
    try:
        client = codex_app_server.CodexAppServerClient()
        started = time.monotonic()
        client.close()
        client.close()
        assert time.monotonic() - started < 1
        assert all(not reader.is_alive() for reader in client._readers)
        assert process.waits == [2]
        assert_released(process)
    finally:
        process.close_writers()


def test_close_reaps_after_kill_escalation(monkeypatch):
    process = FakeProcess([{"id": 1, "result": {}}], ignore_terminate=True)
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)
    with codex_app_server.CodexAppServerClient():
        pass
    assert process.killed
    assert process.waits == [2, 2]
    assert_released(process)


def test_split_utf8_json_and_notification_are_preserved(monkeypatch):
    notification = {"method": "turn/completed", "params": {"turn": {"id": "turn-é", "status": "completed"}}}
    process = FakeProcess([notification, {"id": 1, "result": {"text": "é"}}])
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)
    read = codex_app_server.os.read
    monkeypatch.setattr(codex_app_server.os, "read", lambda fd, _size: read(fd, 1))
    with codex_app_server.CodexAppServerClient() as client:
        assert client.wait_for_turn("turn-é", timeout=1)["status"] == "completed"


def test_final_reply_without_newline_is_preserved(monkeypatch):
    processes = inert_server(
        monkeypatch,
        "import json, os, sys, time\n"
        "first = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': first['id'], 'result': {}}), flush=True)\n"
        "sys.stdin.readline()\n"
        "second = json.loads(sys.stdin.readline())\n"
        "sys.stdout.write(json.dumps({'id': second['id'], 'result': {'accepted': True}})); sys.stdout.flush()\n"
        "os.close(1)\n"
        "time.sleep(60)\n",
    )
    with codex_app_server.CodexAppServerClient(request_timeout=3) as client:
        assert client.request("fixture", {}, timeout=1) == {"accepted": True}
    assert_released(processes[0])


@pytest.mark.parametrize(
    "frame, message",
    [(b"not-json\n", "invalid JSON"), (b"[]\n", "must be an object"), (b"x" * 65, "exceeds size limit")],
)
def test_invalid_or_oversized_frames_fail_actionably_and_clean_up(monkeypatch, frame, message):
    process = FakeProcess([])
    process.stdout.close()
    process.stdout = process.pipe(frame.decode(), False)
    monkeypatch.setattr(codex_app_server.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(codex_app_server, "_STDOUT_FRAME_LIMIT", 64)
    with pytest.raises(codex_app_server.AppServerError, match=message):
        codex_app_server.CodexAppServerClient()
    assert_released(process)
