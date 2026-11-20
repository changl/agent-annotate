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
- `Proto.send({count: ctx => n, open: ctx => {...}})`: the questions area registers Send. The frame draws the top-bar Send ("Send N", primary once N > 0) and the phone's floating Send, and calls `open` on a click. Call `ctx.refreshTop()` after an answer changes N. ⌘↵ stays with the questions area.
- `Proto.bar({render: (el, ctx) => {...}})`: one top-bar slot beside the version (Running's worker squares).
- `ctx.remember('folds'|'tab'|'drafts')`: the settings switches; keep folds or drafts across reloads only when true.
- Settings also set `prefs.get('optsFirst')` (and `body.opts-first`) and `prefs.get('zoomDef', 75)`, the width full-size pictures open at.
- Home (`#home`) reads `proto/data/frame.json`. On this project's row it shows `running.json`'s `workers: [{name, state}]` and `jobs: [{name, failing}]` when present.
- Use `.p-primary` for question context; textareas and text inputs are already 16 px at 100% (`--fs-primary`).

**ctx**
- `base`: the page's URL, ending in `/`. Use relative paths.
- `data(area, fresh)`: promise of `GET proto/data/<area>.json`, cached until Reload or `fresh`.
- `api(path, body, method)`: today's API helper (GET without body, POST with one). Shortcuts: `api.meta() comments() project() history() board() identity() capabilities() delivery() categories() seen() readState() copy()`. Answers, notes and Send use today's endpoints (`api/comments`, `api/rounds/submit`, ...); they save in this copy and the server is sandboxed so nothing is delivered.
- `prefs.get(k, d)` / `prefs.set(k, v)`: localStorage under `annotate-proto:`, the theme included, so nothing set here reaches an ordinary page on the same origin.
- `icon(name, label)`: same as `Proto.icon`; the set is `Proto.ICONS` in `icons.js`. Add a glyph there only, never inline.
- `go(tab, anchor)`: switch tab and scroll to the element with that id.
- `toast(msg, {undo})`: a toast with an Undo link that runs `undo()`.
- `inert(msg, undo)`: see below. `phone`: true at 600 px and under. `esc(s)`: HTML escape.

**Data module.** `src/agent_annotate/proto_data/<area>.py` defines `build(page_dir: Path) -> dict` (JSON-safe). No module means `{}`. Read the page dir; read other systems read-only (`bd ... --readonly`, Orca worker list, Windmill job list). Never write outside the page dir. Errors return 500 with the message.

**Inert actions.** Anything that would reach an agent, Orca, Windmill or the board (rerun, message a worker, change a bead): do not call it. Update the UI as if done, then `ctx.inert('Rerun started', undoFn)`: a toast with Undo and a "prototype: not sent" marker. Put `Proto.inertMark()` beside such controls.

**Look.** Tokens in `tokens.css`: colours, `--fs-*` type scale, one colour per state via `.st-done|progress|waiting|blocked|failed|none` (with `.dot`, `.chip`). Shared bits in `frame.css`: `.btn .chip .chipb .badge .ib .mut .small`.
