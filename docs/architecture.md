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

The detailed contract is [runtime architecture](../src/agent_annotate/skills/claude/references/architecture.md).
