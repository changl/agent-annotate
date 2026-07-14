"""Codex app-server adapter.

The adapter starts a short-lived local app-server client. Codex thread history
is durable, so a delivery can target an existing thread without sharing the
other UI process's stdin. An active turn is steered when its id is known;
otherwise a new turn is started in the selected thread.
"""

from __future__ import annotations

import json
import subprocess
from contextlib import AbstractContextManager
from typing import Any

from .base import DeliveryResult


class AppServerError(RuntimeError):
    pass


class CodexAppServerClient(AbstractContextManager["CodexAppServerClient"]):
    def __init__(self, executable: str = "codex") -> None:
        self._next_id = 1
        self._proc = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
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

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write({"method": method, "id": request_id, "params": params})
        if not self._proc.stdout:
            raise AppServerError("app-server stdout is unavailable")
        for line in self._proc.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise AppServerError(f"{method}: {message['error']}")
            return message.get("result", {})
        stderr = self._proc.stderr.read() if self._proc.stderr else ""
        raise AppServerError(f"app-server stopped while waiting for {method}: {stderr.strip()}")

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()


class CodexAppServerAdapter:
    provider_name = "codex-app-server"

    def __init__(self, executable: str = "codex") -> None:
        self.executable = executable

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
                detail = f"steered active turn {active['id']}"
            else:
                result = client.request(
                    "turn/start", {"threadId": session_id, "input": input_items}
                )
                turn_id = result.get("turn", {}).get("id", "unknown")
                detail = f"started turn {turn_id}"
        return DeliveryResult(True, self.provider_name, session_id, detail)
