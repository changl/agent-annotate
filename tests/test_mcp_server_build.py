import asyncio

import pytest

pytest.importorskip("mcp")

from agent_annotate.mcp_server import build_server  # noqa: E402


def test_supported_sdk_builds_all_existing_tool_schemas():
    server=build_server()
    tools=asyncio.run(server.list_tools())
    assert {tool.name for tool in tools}=={
        "list_pages", "find_workspace","list_comments","reply_to_comment","mark_addressed",
        "list_codex_sessions","connect_codex_page","disconnect_page",
        "list_cards", "read_inbox", "mark_finding_fixed"}
