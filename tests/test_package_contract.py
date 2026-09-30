"""Release identity and provider source precedence must agree across components."""

import json
import tomllib
from pathlib import Path

from agent_annotate import __version__


def test_release_identity_matches_package_and_codex_manifest():
    root = Path(__file__).resolve().parents[1]
    package = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    plugin = json.loads((root / "plugins/codex/agent-annotate/.codex-plugin/plugin.json").read_text())
    assert package["version"] == __version__ == plugin["version"]


def test_codex_mcp_uses_installed_runtime_instead_of_an_independent_git_source():
    root = Path(__file__).resolve().parents[1]
    server = json.loads((root / "plugins/codex/agent-annotate/.mcp.json").read_text())["mcpServers"]["agent-annotate"]
    assert server == {"command": "annotate", "args": ["mcp"]}
