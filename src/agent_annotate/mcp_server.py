"""MCP tools over the same Agent Annotate runtime used by the CLI."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from . import cli
from .paths import MONITOR_ROOT


def _record(slug: str) -> dict[str, Any]:
    record = cli._find_record(slug)
    if not record:
        raise ValueError(f"No published Agent Annotate page named {slug!r}")
    return record


def _comment_rows(slug: str, include_archived: bool = False) -> list[dict[str, Any]]:
    record = _record(slug)
    store_path = Path(record["slug_dir"]) / "comments.json"
    if not store_path.exists():
        return []
    store = json.loads(store_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for anchor_id, comments in store.get("anchors", {}).items():
        for comment in comments:
            rows.append({"anchor_id": anchor_id, **comment})
    if include_archived:
        for anchor_id, comments in store.get("archived", {}).items():
            for comment in comments:
                rows.append({"anchor_id": anchor_id, **comment})
    return rows


def _api_request(slug: str, method: str, path: str, body: dict[str, Any], author: str) -> Any:
    record = _record(slug)
    base = record["local_url"].rstrip("/")
    public_base_path = record.get("public_base_path") or ""
    request = urllib.request.Request(
        f"{base}{public_base_path}{path}",
        method=method,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Cf-Access-Authenticated-User-Email": author,
            # Every event this request emits is attributed to this session.
            "X-Annotate-Session": cli._session_id(),
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is not installed. Install with `uv tool install 'agent-annotate[mcp]'`."
        ) from exc

    server = FastMCP("agent-annotate")

    @server.tool()
    def list_pages() -> list[dict[str, Any]]:
        """List published annotation pages and their current owner lease."""

        pages = []
        for state_file in cli._all_state_files():
            state = json.loads(state_file.read_text(encoding="utf-8"))
            for slug, record in state.get("slugs", {}).items():
                lease_path = MONITOR_ROOT / state["project"] / slug / "owner.json"
                lease = None
                if lease_path.exists():
                    try:
                        lease = json.loads(lease_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        pass
                pages.append({**record, "owner": lease})
        return pages

    @server.tool()
    def list_comments(slug: str, include_archived: bool = False) -> list[dict[str, Any]]:
        """List comments and exact anchors for one annotation page."""

        return _comment_rows(slug, include_archived=include_archived)

    @server.tool()
    def reply_to_comment(slug: str, comment_id: str, text: str, author: str = "agent:codex") -> Any:
        """Reply to one user comment without changing its confirmation state."""

        return _api_request(
            slug,
            "POST",
            f"/api/comments/{comment_id}/reply",
            {"author": author, "text": text},
            author,
        )

    @server.tool()
    def mark_addressed(
        slug: str,
        comment_id: str,
        response_text: str,
        author: str = "agent:codex",
    ) -> Any:
        """Mark one comment addressed by the agent; never user-confirm or archive it."""

        return _api_request(
            slug,
            "PUT",
            f"/api/comments/{comment_id}",
            {"status": "addressed_by_agent", "response_text": response_text},
            author,
        )

    @server.tool()
    def list_codex_sessions(cwd: str | None = None) -> list[dict[str, Any]]:
        """List Codex threads available for explicit page ownership."""

        from .providers.codex_app_server import CodexAppServerAdapter

        return CodexAppServerAdapter().list_sessions(cwd=cwd)

    @server.tool()
    def connect_codex_page(slug: str, thread_id: str, takeover: bool = False) -> str:
        """Connect a page's push events to an explicitly selected Codex thread."""

        rc = cli.cmd_connect(SimpleNamespace(slug=slug, thread=thread_id, takeover=takeover))
        if rc:
            raise RuntimeError(f"Could not connect {slug!r}; annotate connect exited {rc}")
        return f"Connected {slug} to {thread_id}"

    @server.tool()
    def disconnect_page(slug: str) -> str:
        """Release a page owner while leaving the review server running."""

        rc = cli.cmd_disconnect(SimpleNamespace(slug=slug))
        if rc:
            raise RuntimeError(f"Could not disconnect {slug!r}; annotate disconnect exited {rc}")
        return f"Disconnected {slug}"

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()

