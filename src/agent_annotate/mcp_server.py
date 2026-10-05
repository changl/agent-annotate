"""MCP tools over the same Agent Annotate runtime used by the CLI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from . import cli
from .paths import MONITOR_ROOT
from .urls import mounted_url, page_url
from .workspace import owner_data, workspace_data


def _record(slug: str) -> dict[str, Any]:
    resolved = cli._resolve_scoped_slug(slug)
    if not resolved:
        raise ValueError(f"No unique exact Agent Annotate page named {slug!r}; use project/slug")
    return resolved[2]


def _comment_rows(slug: str, include_archived: bool = False, category: str | None = None) -> list[dict[str, Any]]:
    category = cli._category(category)
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
    return [row for row in rows if cli._comment_category(row) == category] if category else rows


def _api_request(slug: str, method: str, path: str, body: dict[str, Any], author: str) -> Any:
    record = _record(slug)
    code, payload = cli._api(record, method, path, body, author, timeout=5)
    if code == 0:
        raise RuntimeError(str(payload))
    if not 200 <= code < 300:
        error = payload.get("error") if isinstance(payload, dict) else None
        raise RuntimeError(f"local annotate API returned HTTP {code}" + (f": {error}" if isinstance(error, str) else ""))
    return payload


def build_server():
    try:
        try:
            from mcp.server.mcpserver import MCPServer
        except ImportError:
            from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is not installed. Install with `uv tool install 'agent-annotate[mcp]'`."
        ) from exc

    server = MCPServer("agent-annotate")

    @server.tool()
    def list_pages() -> list[dict[str, Any]]:
        """List existing pages, share URLs, and durable owners with recorded terminal names.

        Reuse one project workspace. Legacy monitor metadata is separate from page ownership.
        """

        pages = []
        for project, slug, record in cli._registry_entries():
            lease_path = MONITOR_ROOT / project / slug / "owner.json"
            lease = None
            if lease_path.exists():
                try:
                    lease = json.loads(lease_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            url = page_url(record)
            pages.append({**record, "project": project, "slug": slug, "url": url,
                          "public_url": url if record.get("transport") == "funnel" else
                          mounted_url(record.get("public_url"), record.get("public_base_path")),
                          "owner": owner_data(record), "legacy_monitor": lease})
        return pages

    @server.tool()
    def find_workspace(cwd: str | None = None, project: str | None = None) -> dict[str, Any]:
        """Find and reuse one project page across sessions/worktrees. Funnel is the default share URL.

        Pass the project worktree as cwd. Progress-only updates use annotate project without
        feedback rounds; create no extra page, monitor, or maintenance task. Discovery is read-only.
        """
        return workspace_data(Path(cwd).expanduser().resolve() if cwd else Path.cwd(), project)

    @server.tool()
    def list_comments(slug: str, include_archived: bool = False, category: str | None = None) -> list[dict[str, Any]]:
        """Read comments and explanations on the reused page; act on submitted rounds, not draft clicks."""

        return _comment_rows(slug, include_archived=include_archived, category=category)

    @server.tool()
    def list_cards(slug: str, category: str | None = None) -> list[dict[str, Any]]:
        """Read decision cards, including finding fix proof; optionally filter a category."""
        category = cli._category(category)
        cards = cli._decision_cards(cli._load_store(_record(slug)))
        return [card for card in cards if card["category"] == category] if category else cards

    @server.tool()
    def read_inbox(slug: str, category: str | None = None) -> dict[str, Any]:
        """Read visible inbox events without advancing any cursor; optionally filter a category."""
        category = cli._category(category)
        record = _record(slug)
        bus = Path(record.get("bus_file") or (cli.BUS_ROOT / record["project"] / f"{record['slug']}.ndjson"))
        events = []
        if bus.exists():
            for line in bus.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and cli._inbox_visible(event, cli._session_id()):
                    events.append(event)
        store = cli._load_store(record)
        if category:
            events = cli._category_events(events, store, category)
        texts = cli._comment_texts(store)
        for event in events:
            note = (texts.get(event.get("comment_id")) or ("", ""))[1]
            if event.get("decision") and note and "decision_text" not in event:
                event["decision_text"] = note
        cards = cli._decision_cards(store)
        if category:
            cards = [card for card in cards if card["category"] == category]
        return {"slug": slug, "events": events, "event_count": len(events),
                "card_count": len(cards), "decisions": cli._verdict_counts(cards),
                **({"category": category} if category else {})}

    @server.tool()
    def mark_finding_fixed(slug: str, number_or_id: int | str, proof: list[str], note: str = "",
                           author: str = "agent:codex") -> dict[str, Any]:
        """Mark a finding fixed only with proof URLs or files inside the server cwd (10 MiB limit)."""
        return cli.fix_finding(_record(slug), number_or_id, proof, note, cli._resolve_author(author))

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
        """Legacy non-Orca integration: list Codex threads for an explicitly requested monitor connection."""

        from .providers.codex_app_server import CodexAppServerAdapter

        return CodexAppServerAdapter().list_sessions(cwd=cwd)

    @server.tool()
    def connect_codex_page(slug: str, thread_id: str, takeover: bool = False) -> str:
        """Legacy non-Orca integration: start a monitor for an explicitly selected Codex thread.

        This sets monitor delivery, not durable page ownership. Orca submitted-round delivery
        is server-owned and needs no monitor; successors use annotate claim on the existing page.
        """

        rc = cli.cmd_connect(SimpleNamespace(slug=slug, thread=thread_id, takeover=takeover))
        if rc:
            raise RuntimeError(f"Could not connect {slug!r}; annotate connect exited {rc}")
        return f"Legacy monitor connected: {slug} to {thread_id}; durable page ownership unchanged"

    @server.tool()
    def disconnect_page(slug: str) -> str:
        """Stop the legacy monitor; retain durable page ownership, server, URL, and reviewer feedback."""

        rc = cli.cmd_disconnect(SimpleNamespace(slug=slug))
        if rc:
            raise RuntimeError(f"Could not disconnect {slug!r}; annotate disconnect exited {rc}")
        return f"Legacy monitor disconnected: {slug}; durable page ownership unchanged"

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
