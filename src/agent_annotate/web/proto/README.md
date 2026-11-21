# Prototype UI: module contract

Served only for a page whose `current.meta.json` has `"ui": "proto"`. Files: `web/proto/<area>.js|.css`, `proto_data/<area>.py`, `tests/proto/`. Areas: `questions`, `reference`, `running` (Running and Analytics tabs), `history`, `links`; the frame owns `frame`. Touch only your own files.

**Register a tab.** `frame.js` loads `proto/<area>.css` and `proto/<area>.js` when present, then routes. In your JS:

```js
Proto.tab({key: 'questions',                     // questions|reference|running|analytics|history|links
  label: 'Questions',                            // optional: overrides the default label
  chip: async ctx => ({text: '3', tone: 'red'}), // optional; tone red|amber|green or none; null hides it
  render: async (el, ctx, anchor) => { el.innerHTML = '...'; }});
```

`render` owns `el` (`<main>`, class `area-<area> tab-<key>`), is called each time the tab opens, and gets the `anchor` from `#<tab>/<anchor>`. Call `ctx.refreshChips()` after a change. A chip of `{empty: true}` dims the tab and reads "nothing yet"; tones also take `blue` and `orange`.

**Added in round 10 (frame):**
- `Proto.send({count: ctx => n, open: ctx => {...}})`: the questions area registers Send. The frame draws the top-bar Send ("Send N", primary once N > 0) and the phone's floating Send, and calls `open` on a click. Call `ctx.refreshTop()` after an answer changes N. ⌘↵ stays with the questions area. Its optional `wrote(path)` hears every write `ctx.api` makes, on any tab.
- `Proto.queue({items: ctx => [{key, group, html, go(), remove(), note?}], sent: ctx => {}})`: the one Send queue (round 12 fix6). Anything a tab says "goes with your next Send" (task status and comments, Tell the agent, Reference reopens, copy-library choices and notes, kept-document notes) is listed by its source. Questions' Send sheet shows each item under its `group`, counts it, and calls `remove()` on Remove or Discard all. `remove` may be async and returns an undo function or null. After a Send, the frame calls every source's `sent`. `note` names the comment id an item stands for, so Questions does not list that note a second time. The frame repaints only the Send buttons after any click, keystroke or write, so the count follows on every tab. Areas read the queue with `ctx.queued()`; Questions calls `ctx.queueSent()`.
- `Proto.bar({render: (el, ctx) => {...}})`: one top-bar slot beside the version (Running's worker squares).
- `ctx.remember('folds'|'tab'|'drafts')`: the settings switches; keep folds or drafts across reloads only when true.
- Settings also set `prefs.get('optsFirst')` (and `body.opts-first`) and `prefs.get('zoomDef', 75)`, the width full-size pictures open at.
- Home (`#home`) reads `proto/data/frame.json`. On this project's row it shows `running.json`'s `workers: [{name, state}]` and `jobs: [{name, failing}]` when present.
- Use `.p-primary` for question context; textareas and text inputs are already 16 px at 100% (`--fs-primary`).

**Added in round 12 (frame; all backward compatible):**
- `render(el)` now gets a fresh box inside `<main>` (`div.p-view`, same `area-<area> tab-<key>` classes, `display:contents`). A render that finishes after the tab changed paints into a detached box, so it never lands on another tab.
- `Proto.bar` is ignored (kept so a call does no harm): the frame draws the worker squares from `running.json` (`workers` by Mac, `jobs`, `board`) for the project on screen, with the overview on hover and focus.
- Keys: Questions owns F, A, 1–9, C and Esc on its tab. From any other tab (or Home) the frame opens Questions on F or A, waits for `.qcard[data-q]`, then dispatches the same key on `body`. On other tabs Esc clicks `#p-main [role=dialog] [data-esc]` or `[data-sendclose]`.
- With Unsent answers off, prefs keys `q:drafts`, `q:general`, `q:newnote`, `tst`, `tcm:*`, `draft:*` stay in memory only, and stored ones are dropped at load. A new draft key must join `DRAFT` in `frame.js`.
- With Folds on, any `<details>` in `#p-main` keeps its open state by tab and summary text, and so does any `button[data-sfold="<id>"]` with `aria-expanded` (a click on it, or on `[data-secall]`, is saved; the frame presses it once on the next load).
- `frame.json` gains `code` (fld, rebex, annotate, ...), project `code` and `owner` (`{agent, at, alive}`), and `lastSend` (`{ts, delivery, n}`).
- Routes: `#project/<key>/<tab>` shows another project; any `[data-go="<tab>/<anchor>"]` in the frame jumps there.

**Added in round 12, second pass (frame):**
- Read-only copies: `copy.sh` copies Rebex's and Agent Annotate's pages to `reviews/proto-<key>` (scrubbed, no owner, no store). This server serves each under `proto/p/<key>/` with its own folder, so `ctx.base`, `api` and `data` already point at the copy. Only GETs reach the server for a copy: `api()` hands every write on a copy to `P.copyWrite`, which Questions answers in memory, so a reload shows the copy as it was. A copy's header shows the same Send and Beads as FastLane Drive's; its Send is simulated and reaches no agent.
- `frame.json` projects: one row a project. A prototype page stands in for its project's row; `href` is `""` for this page, `proto/p/<key>/` for a copy, absent for a project shown as a summary. `url` is the project's real page, without its key. `copyOf` names the project when this page is a copy.
- Prefs on a copy are kept per copy (`annotate-proto:p/<key>:...`), except Settings (`theme`, `fs`, `rem`, `optsFirst`, `zoomDef`).
- Phone: the frame folds into its menu up to 900 px (`ctx.phone`), not 600. From 601 to 900 your desk layout sits under a 44 px header: the frame re-pins `.qbar` and `.ajump` to `top:44px` and shows `.ph-only`. A new pinned bar should do the same.
- Jumps and skip links scroll their target clear of the frame and of any pinned bar of yours (`scrollClear`).
- History's ← → are handled by the frame while `#history/<version>` is open: they call `ctx.go('history', <older or newer>)`.

**ctx**
- `base`: the page's URL, ending in `/`. Use relative paths.
- `data(area, fresh)`: promise of `GET proto/data/<area>.json`, cached until Reload or `fresh`.
- `api(path, body, method)`: today's API helper (GET without body, POST with one). Shortcuts: `api.meta() comments() project() history() board() identity() capabilities() delivery() categories() seen() readState() copy()`. Answers, notes and Send use today's endpoints (`api/comments`, `api/rounds/submit`, ...); they save in this copy and the server is sandboxed so nothing is delivered.
- `prefs.get(k, d)` / `prefs.set(k, v)`: localStorage under `annotate-proto:`, the theme included, so nothing set here reaches an ordinary page on the same origin.
- `icon(name, label)`: same as `Proto.icon`; the set is `Proto.ICONS` in `icons.js`. Add a glyph there only, never inline.
- `go(tab, anchor)`: switch tab and scroll to the element with that id.
- `toast(msg, {undo})`: a toast with an Undo link that runs `undo()`.
- `inert(msg, undo)`: see below. `phone`: true at 900 px and under. `esc(s)`: HTML escape.

**Data module.** `src/agent_annotate/proto_data/<area>.py` defines `build(page_dir: Path) -> dict` (JSON-safe). No module means `{}`. Read the page dir; read other systems read-only (`bd ... --readonly`, Orca worker list, Windmill job list). Never write outside the page dir. Errors return 500 with the message.

**Inert actions.** Anything that would reach an agent, Orca, Windmill or the board (rerun, message a worker, change a bead): do not call it. Update the UI as if done, then `ctx.inert('Rerun started', undoFn)`: a toast with Undo and a "prototype: not sent" marker. Put `Proto.inertMark()` beside such controls.

**Look.** Tokens in `tokens.css`: colours, `--fs-*` type scale, one colour per state via `.st-done|progress|waiting|blocked|failed|none` (with `.dot`, `.chip`). Shared bits in `frame.css`: `.btn .chip .chipb .badge .ib .mut .small`.
