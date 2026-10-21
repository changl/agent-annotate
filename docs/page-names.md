# Page names

A page owns one canonical display name in `current.meta.json.name`. `annotate new DIR --from page.md --title "Assessment"` sets it; `annotate publish DIR --title "Assessment and evidence"` explicitly renames it. Without `--title`, first creation/publication freezes the initial document title. Later Markdown `title`, version `--label`, and Plan titles describe their documents or revisions and do not rename the page. Use sentence case while preserving proper nouns/acronyms. Spell the project **Agent Annotate** in human prose; `agent-annotate` is its package/repository identifier. `project.json.title` remains project branding, separate from the page name.

New page directories use lowercase ASCII kebab-case derived from the initial name (`Assessment and evidence` → `assessment-and-evidence`); choose an explicit meaningful ASCII slug when the name does not transliterate. Persistent workspaces have no date suffix; deliberately separate dated reports/events may use `-YYYYMMDD`, matching the report/creation date. Existing directory names and URLs stay stable after renames. Keep `page.md`, `source/vN.md`, and `versions/vN.html` as source and revision files.

Readers use the saved name, a legacy registry title, the earliest available document title, then `Untitled page`; reads never write metadata. Slugs occur in URLs, paths, identity fields and executable CLI arguments, not as display names. Names are normalized plain text, 1–160 characters, with control characters/markup rejected.

Reference tabs link by URL and ID. Registered targets supply their own names; parent-authored legacy labels are ignored. New references may omit `label`; external links and native tabs retain authored labels. Project API `related_pages` exposes `{slug, name, url, reason?}`. Existing `tabs[].label` and `linked_pages[].title` remain compatibility aliases of the same name while clients migrate. Project/meta APIs, workspace JSON/text, session-start, MCP, and CLI receipts share the resolver. The header and browser tab title prefer project branding (`project.json.title`), falling back to the canonical page name; switching document revisions never changes that fallback. Plan titles and revision labels remain independent.

## Existing-page migration

Operator-only `annotate names` appears under `annotate help --all`. Supply an explicit map; there is no implicit scan-and-rename operation:

```json
{"reviews/assessment-20260917": "Assessment", "reviews/operations-20260929": "Operations"}
```

```sh
annotate names --from names.json --dry-run --json
annotate names --from names.json --apply --json
```

The dry run reports old/proposed names, changed files and unresolved unlabeled links without creating files, locks or backups. Review the output before separately authorizing `--apply`. Applying validates the whole map, locks page metadata/project files, creates exact-byte backups and existence/hash manifests under the configured registry's `name-backups/` directory (outside served page directories), then atomically replaces changed files. Registered reference labels are removed from stored project data and remain derived in API responses. Unresolved unlabeled references block apply. Rerunning the same map produces zero changes/backups; names, routes, owners, revision history and content are preserved except for the explicit name change. For rollback, restore manifest-listed bytes under the same locks, removing a file only if the manifest says it did not previously exist; do not restore unrelated runtime metadata from an old backup after newer activity.
