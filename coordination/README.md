# Coordination contract

Runtime ownership is intentionally separate from Git ownership.

- A workstream declares its project, scope, repository or artifact paths, and agent session id.
- One annotation page has one active session owner.
- Schema/content agents do not edit the Agent Annotate runtime.
- Annotation agents do not alter schema meaning while repairing presentation or delivery.
- Cross-workstream requests are sent as immutable events and acknowledged by event id.
- A takeover must be explicit and preserves the page server, comments, and event cursor.

Live assignments belong in the project's runtime state and are not committed to
this public repository. `annotate sessions`, `annotate connect`, and `annotate
disconnect` are the first Codex-facing controls.

