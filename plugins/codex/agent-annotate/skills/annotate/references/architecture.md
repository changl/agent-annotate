# Runtime architecture

One installed Python package serves shared UI assets, versioned project content, persistent project data, and reviewer feedback. Skills contain instructions, not server code. Claude Code and Codex use the same CLI and state.

| Component | Responsibility |
| --- | --- |
| `pagegen.py` | Markdown, anchors, staged review versions |
| `project_state.py` | Validated persistent progress, links, tabs; atomic/no-op updates |
| `sync_server.py` | HTTP, identity boundary, comment store, fsynced event bus |
| `web/` | Shared daisyUI shell, themes, controls, content adapter |
| `workspace.py` | Discover/select the canonical project page; prevent duplicate workspace creation |
| `delivery.py` | One durable Orca wake-up per submitted round |
| `transports/` | Local, tailnet, and configured public routing |
| `deployment.py`, `updates.py` | Explicit/operator-managed runtime rollout and rollback |
| `skillgen.py` | Explicit skill installation/sync, preserving custom edits |

Page ownership is durable. Publishing/claiming captures the caller's Orca terminal and provider process; delivery validates the current owner under the claim lock. A successor claims the existing page. No normal project session needs a monitor. Optional legacy monitors and Codex app-server adapters remain separate compatibility paths.

State roots remain the configured registry, event bus, and project directories. Updates preserve owners, routes, ports, feedback, and history; they do not install skills. Runtime checksums detect byte mismatch, not publisher identity. Public reviewer authentication is an explicit transport boundary; private tailnet access does not prove outside access.

Feedback stays append-audited. Previous open items must resolve at a real later-version anchor or carry forward before review activation. Reviewer replies reopen resolved items. Accepted terminal input and inbox acknowledgment are distinct from project completion.
