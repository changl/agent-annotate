"""Provider adapter contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    provider: str
    session_id: str
    detail: str


class AgentProviderAdapter(Protocol):
    """Minimal boundary between the durable runtime and an agent session."""

    provider_name: str

    def list_sessions(self, *, cwd: str | None = None) -> list[dict[str, Any]]: ...

    def deliver(self, session_id: str, message: str) -> DeliveryResult: ...

    def heartbeat(self, session_id: str) -> bool: ...

