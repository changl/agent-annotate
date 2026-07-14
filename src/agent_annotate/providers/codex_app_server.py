"""Codex app-server adapter.

The adapter starts a short-lived local app-server client. Codex thread history
is durable, so a delivery can target an existing thread without sharing the
other UI process's stdin. An active turn is steered when its id is known;
otherwise a new turn is started in the selected thread.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from contextlib import AbstractContextManager
from typing import Any

from .base import DeliveryResult


class AppServerError(RuntimeError):
    pass


class CodexAppServerClient(AbstractContextManager["CodexAppServerClient"]):
    def __init__(self, executable: str = "codex", request_timeout: float = 30) -> None:
        self._next_id = 1
        self._request_timeout = request_timeout
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._backlog: list[dict[str, Any]] = []
        self._proc = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "agent_annotate",
                    "title": "Agent Annotate",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _write(self, message: dict[str, Any]) -> None:
        if not self._proc.stdin:
            raise AppServerError("app-server stdin is unavailable")
        self._proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self._proc.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"method": method, "params": params})

    def _read_stdout(self) -> None:
        if not self._proc.stdout:
            self._messages.put({"__eof__": True})
            return
        for line in self._proc.stdout:
            try:
                self._messages.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._messages.put({"__eof__": True})

    def _take_matching(self, predicate, timeout: float) -> dict[str, Any]:
        for index, message in enumerate(self._backlog):
            if predicate(message):
                return self._backlog.pop(index)

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AppServerError("timed out waiting for app-server")
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise AppServerError("timed out waiting for app-server") from exc
            if message.get("__eof__"):
                stderr = self._proc.stderr.read() if self._proc.stderr else ""
                raise AppServerError(f"app-server stopped unexpectedly: {stderr.strip()}")
            if predicate(message):
                return message
            self._backlog.append(message)

    def request(
        self, method: str, params: dict[str, Any], timeout: float | None = None
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write({"method": method, "id": request_id, "params": params})
        message = self._take_matching(
            lambda item: item.get("id") == request_id,
            timeout if timeout is not None else self._request_timeout,
        )
        if "error" in message:
            raise AppServerError(f"{method}: {message['error']}")
        return message.get("result", {})

    def wait_for_turn(self, turn_id: str, timeout: float) -> dict[str, Any]:
        message = self._take_matching(
            lambda item: item.get("method") == "turn/completed"
            and item.get("params", {}).get("turn", {}).get("id") == turn_id,
            timeout,
        )
        turn = message.get("params", {}).get("turn", {})
        status = turn.get("status", "unknown")
        if status not in ("completed", "success"):
            raise AppServerError(f"turn {turn_id} completed with status {status}")
        return turn

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()


class CodexAppServerAdapter:
    provider_name = "codex-app-server"

    def __init__(self, executable: str = "codex", turn_timeout: float = 3600) -> None:
        self.executable = executable
        self.turn_timeout = turn_timeout

    def list_sessions(self, *, cwd: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "limit": 100,
            "sortKey": "recency_at",
            "sortDirection": "desc",
        }
        if cwd:
            params["cwd"] = cwd
        with CodexAppServerClient(self.executable) as client:
            return client.request("thread/list", params).get("data", [])

    def heartbeat(self, session_id: str) -> bool:
        try:
            with CodexAppServerClient(self.executable) as client:
                client.request("thread/read", {"threadId": session_id, "includeTurns": False})
            return True
        except (OSError, AppServerError):
            return False

    def deliver(self, session_id: str, message: str) -> DeliveryResult:
        input_items = [{"type": "text", "text": message}]
        with CodexAppServerClient(self.executable) as client:
            thread = client.request("thread/resume", {"threadId": session_id}).get("thread", {})
            turns = thread.get("turns", [])
            active = next((turn for turn in reversed(turns) if turn.get("status") == "inProgress"), None)
            if active:
                client.request(
                    "turn/steer",
                    {
                        "threadId": session_id,
                        "expectedTurnId": active["id"],
                        "input": input_items,
                    },
                )
                turn_id = active["id"]
            else:
                result = client.request(
                    "turn/start", {"threadId": session_id, "input": input_items}
                )
                turn_id = result.get("turn", {}).get("id", "unknown")
            turn = client.wait_for_turn(turn_id, self.turn_timeout)
            detail = f"completed turn {turn_id} ({turn.get('status', 'unknown')})"
        return DeliveryResult(True, self.provider_name, session_id, detail)
