# Commands

Use the installed package executable. The module fallback works only in its Python environment. `doctor` identifies the build and paths; `doctor --versions` exits 1 when the launcher, a skill, the Codex plugin or a live page differs from the installed release, and prints the fix commands. Slugs accept `PROJECT/SLUG`; use that form when names overlap. `COMMAND --help` is the authoritative flag reference.

| Task | Command |
| --- | --- |
| Find project page | `workspace --json` |
| Select existing main page | `workspace --select PROJECT/SLUG` |
| Create first page | `new DIR --from page.md --project NAME --publish` |
| Pose new feedback | Add `--ask` only when source has cards |
| Update progress | `project PROJECT/SLUG --from project.json` |
| Read/import Library | `library PROJECT/SLUG [--block ID | --from copy.json] --json` (`copy` is equivalent) |
| Findings questions | `ask PROJECT/SLUG --from cards.json --category findings --set design --json` |
| Fixed with proof | `finding PROJECT/SLUG --fixed 11 --proof proof.png --proof https://example.test/check --note "Verified" --json` |
| Publish plan revision | `plan PROJECT/SLUG rollout --from plan.md --title "Rollout" --label "Rehearsed" --json` |
| Explicit second page | `new DIR --from page.md --publish --exception "Orchestrator requested worksheet"` |
| Later review version | `new DIR --from page.md --version vN --publish --ask` |
| Read submitted feedback | `inbox PROJECT/SLUG --unread` once, unfiltered: that read acknowledges the delivered round. Then `cards PROJECT/SLUG`. `--category findings` narrows a later read and never acknowledges delivery |
| Handoff ownership | `claim PROJECT/SLUG` from successor session |
| Record response | `addressed PROJECT/SLUG ID --response TEXT` |
| Apply prior feedback | `resolve PROJECT/SLUG ID --in-version vN --anchor ANCHOR --response TEXT` |
| Preserve pending feedback | `carry PROJECT/SLUG ID --to-version vN --anchor ANCHOR --response TEXT` |
| Inspect delivery issue | `deliver PROJECT/SLUG --dry-run` |

No polling, monitors, repeated verification, usage reports, or upgrade checks during ordinary project work. First-page publish verifies rendering; a meaningful route or runtime failure may warrant a new check. Access login is reported as unverified, not a broken origin.

Tailscale Funnel is the default for every new page. It adds one exact path to an already-public or unused Funnel port, without exposing private services or resetting unrelated routes. Private share links grant external review access; the fragment key becomes a page-scoped secure cookie and is removed from the address bar. Use Copy link or the full CLI URL when sharing. Tailnet visitors retain their Tailscale identity.

Machine-local `projects.toml` uses `[defaults]` plus project overrides. Choose `transport = "funnel"`; Cloudflare transports remain legacy compatibility only. `URL:` is the canonical Funnel review link. A route failure must not print a localhost substitute. Explicit `--transport local` is for development.

Operator commands: `status`, `revive`, `retire --dry-run`, `close --dry-run`, `unpublish`, `update --check|--apply|--enable|--disable`, `report`, `fleet`, `eval`, `cost`. Cleanup and scheduling require their own authorization. `install-skill` and `sync-skills` are explicit user-managed operations, excluded from runtime updates.

Environment overrides: `ANNOTATE_CONFIG_DIR`, `ANNOTATE_PROJECTS_TOML`, `ANNOTATE_STATE_DIR`, `ANNOTATE_BUS_ROOT`, `ANNOTATE_DATA_DIR`, `ANNOTATE_CLAUDE_SETTINGS`, `ANNOTATE_SHIM_PATH`. Set before importing the package. Session identity comes from the provider session environment; inbox cursors are per session and independent of notices/delivery cursors.

`monitor`, `connect`, `disconnect`, `sessions`, `send`, `watch`, and `hook-check` support legacy or non-Orca integration. They are not required for server-owned Orca round delivery. Never claim unrelated pages or manually edit owner metadata.

Account migration: an operator can map a verified reviewer login to prior logins with `[PROJECT.reviewer_aliases]` and `"current@login" = ["previous@login"]`. This permits submitting that reviewer's saved drafts without rewriting authors; other reviewers retain separate drafts.

Categories are `review`, `library`, `findings`, `plans`. Omitted category means all categories when reading; old comments default to Review, or Library for `copy:` anchors. Findings cards can carry `category` and `set` in JSON; flags provide defaults. Fixes require at least one proof URL or file. Files must be png, jpg, jpeg, gif, webp, pdf, txt, md, log, json or csv; link anything else by HTTPS URL. They must resolve inside the caller cwd (for MCP, the MCP server's working directory) and fit the 10 MiB attachment limit; symlink escapes and hard links fail. They are copied into the page attachments directory; the page opens only images and PDF inline. Plans accept Markdown or HTML (at most 4 MiB), validate safe plan IDs, and append revisions without changing Review. MCP offers `mark_finding_fixed`, `list_cards`, and `read_inbox` with category filters; `list_comments` also accepts a category.
