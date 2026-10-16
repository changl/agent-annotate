# Architecture

One project page serves Review, Library, Findings, and Plans from the same page directory and comment store. CLI and MCP use the same storage and category rules as HTTP; no category needs another project page.

| Storage | Behavior |
| --- | --- |
| `comments.json` schema 2 | Optional category/doc/finding/fixed fields; old copy anchors default to Library, other comments to Review |
| `copy.json` schema 1 | Library groups and block metadata; immutable revisions; browser proposals wait for shared Send |
| `categories.json` | Optional findings set IDs and labels |
| `plans/<id>/meta.json` and `versions/vN.html` | Independent plan streams with title, current version and labeled history |
| Registry exception | Reason and parent_slug; main page discovers Linked pages; separate ownership |

`categories.py` validates storage, computes category counts, records fixes with proof, and publishes plans. `pagegen.py` supplies Markdown rendering and anchors. `cli.py` provides finding, plan, library/copy, ask and filtered reads; `mcp_server.py` provides the corresponding fix and read tools. `workspace.py` enforces canonical reuse and exposes linked exceptions. The HTTP server owns identity checks and shared round delivery.

Every new file/field is optional. Plans do not activate Review versions; fixes never confirm for reviewers. A reopen moves the previous fix into history and becomes round-pending. Shared Send persists cross-category answers and Library edits before waking the current owner.


## Runtime details


One installed Python package serves shared UI assets, versioned project content, persistent project data, and reviewer feedback. Skills contain instructions, not server code. Claude Code and Codex use the same CLI and state.

| Component | Responsibility |
| --- | --- |
| `pagegen.py` | Markdown, anchors, staged review versions |
| `project_state.py` | Validated persistent progress, links, tabs; atomic/no-op updates |
| `sync_server.py` | HTTP, identity boundary, comment store, fsynced event bus |
| `web/` | Shared daisyUI shell, themes, controls, content adapter |
| `workspace.py` | Discover/select the canonical page; explicit exception links with recorded reasons |
| `categories.py` | Category defaults/counts, findings proof and fix history, independent plan versions |
| `copy_state.py` | Library groups, block metadata and immutable revisions |
| `cli.py`, `mcp_server.py` | Agent category commands and tools |
| `delivery.py` | One durable Orca wake-up per submitted round |
| `transports/` | Local, tailnet, and configured public routing |
| `deployment.py`, `updates.py` | Explicit/operator-managed runtime rollout and rollback |
| `skillgen.py` | Explicit skill installation/sync, preserving custom edits |

Page ownership is durable. Publishing/claiming captures the caller's Orca terminal and provider process; delivery validates the current owner under the claim lock. A successor claims the existing page. No normal project session needs a monitor. Optional legacy monitors and Codex app-server adapters remain separate compatibility paths.

State roots remain the configured registry, event bus, and project directories. Updates preserve owners, routes, ports, feedback, and history; they do not install skills. Runtime checksums detect byte mismatch, not publisher identity. Public reviewer authentication is an explicit transport boundary; private tailnet access does not prove outside access.

Feedback stays append-audited. A new version withdraws agent questions not asked again; reviewer comments and submitted answers remain audited. Reviewer replies reopen resolved items. Accepted terminal input and inbox acknowledgment are distinct from project completion.

Every category lives in the same page directory. Optional comment category/doc/finding/fixed fields preserve schema 2; old copy anchors default to Library, other comments to Review. Optional categories.json stores findings sets. Plans use plans/<id>/meta.json and versions/vN.html independently of current.meta.json. Library remains copy.json schema 1 with optional groups/block fields. Shared submitted rounds carry categories and Library edits; exceptions live in registry metadata and retain separate owners.
