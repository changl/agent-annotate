# Rebex server fixture

Use this branch's `.venv/bin/python` (or the merged product worktree's venv).
All runtime paths are isolated under `/private/tmp/annotate-product-server/`.
The builder refuses to overwrite an existing page; choose a fresh state dir
for a rebuild. The completed fixture is at `/private/tmp/annotate-product-server/fixture`.

```sh
.venv/bin/python work/product/fixture/build_fixture.py --state /private/tmp/annotate-product-server/fixture
.venv/bin/python work/product/fixture/serve_fixture.py --port 8980 --state /private/tmp/annotate-product-server/fixture
```

The launcher runs main's server unchanged as separate subprocesses on 8980
(Rebex) and 8981 (Linked motion lab). Ctrl-C or SIGTERM stops both. Its preset
identity is `chang@leadory.com`, named `Chang (snapshot)`, as in the base harness.
Ports are checked before startup; no publish, monitor, Funnel or live-state operations run.

The build preserves every Review comment and copies all saved document versions.
It imports 99 Library items in 12 groups, 20 Findings in two sets, and six
Shopify plan documents through the new storage functions. Plan documents are
extracted from the baked HTML before publication. Publication timestamps are
fixture-build timestamps; labels and document order come from the archive.

The copy CLI accepts Delta JSON only. The minimal converter here preserves text,
bold/italic/underline/strike/code, safe links, headings 1–3, lists and blockquotes;
it omits embeds, scripts/styles and unsupported visual formatting. Archived Library
history comments preserve the source added/decision/response events, including
their original text/times in `target.seed_history`, instead of inventing copy revisions
from decision text. The source has one authored copy addition per item.

Library status mapping: held-back lines → `held` with their reason in `held_note`;
three policy drafts → `needs_you`; decided copy/approved articles → `done`.
The original source status wording is preserved on each history comment. The
shared Library question is an ordinary category comment linked by
`question_comment_id` from the affected blocks. It counts separately from blocks.
Library read-state keys are `copy:<block_id>` and the signature is the latest
revision id; use the existing `/api/read-state` route. Comment read-state follows
the existing shell signature. Category counts include unread items from declared author aliases.

Gap 1's fix, image and `example.com` link are **simulated UI examples** from final's
data. They do not claim any actual Rebex storefront fix. The exception page is a
copy of the archived motion page registered with its reason and `parent_slug: rebex`.
Nothing in the source archive is modified. No live Rebex URL is fetched.
