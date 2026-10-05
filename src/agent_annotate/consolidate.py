"""Merge several pages of one project into one page, keeping every record.

Each source page goes to one tab of a new target page:

    review    the Review document (exactly one source): versions, sources,
              assets, rounds and comments, unchanged
    plans     an independently versioned plan with every version and comment
    findings  every decision card becomes a finding in a set named after the
              page; other comments stay on their finding
    library   copy.json blocks with their comments; a page without blocks
              gets one Library item that links its original document

Every comment keeps its id, author, times, text, replies, verdicts, decision
history and status; only its tab fields (category, doc, finding, anchor_id
for Findings and Library) change, and `moved_from` records its page. A
comment without a stored number gets the number its page showed. Reviewer
read state, submitted rounds and the Review document's seen stamps move too.

A source page is never deleted. It gets a `consolidated.json` marker: its
server then refuses writes, redirects its address to the matching tab and
serves the old page read-only with `?archived=1`. The marker lives in the
page directory, so this holds through `publish`, `revive` and restarts.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

TABS = ("review", "library", "findings", "plans")
MARKER = "consolidated.json"      # in each source page directory
MANIFEST = "consolidation.json"   # in the target page directory
_SOURCE = re.compile(r"(?P<ref>[^:\s]+):(?P<tab>[a-z]+)(?:=(?P<id>[a-z0-9][a-z0-9-]{0,63}))?\Z")
# The files a server or the CLI writes while a page is live. They are hashed
# when read and again after the target is written; a change aborts the run.
_MUTABLE = ("comments.json", "read-state.json", "seen.json", "current.meta.json", "rounds.ndjson",
            "copy.json", "categories.json", "project.json")
# Fields consolidation may set on a comment. Every other field is compared
# byte for byte between source and target.
_TAB_FIELDS = ("category", "doc", "finding", "anchor_id", "number", "moved_from")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_source(value: str) -> tuple[str, str, str | None]:
    """`PROJECT/SLUG:TAB` or `PROJECT/SLUG:TAB=ID` (the plan or findings set id)."""
    match = _SOURCE.fullmatch(value or "")
    if not match or match["tab"] not in TABS:
        raise ValueError(f"--from {value!r}: use PROJECT/SLUG:TAB with TAB one of {', '.join(TABS)} "
                         "(optional =ID for a plan, findings set or Library item)")
    if match["id"] and match["tab"] == "review":
        raise ValueError(f"--from {value!r}: the Review document takes no id")
    return match["ref"], match["tab"], match["id"]


def marker(page_dir: Path | str) -> dict | None:
    """The page's consolidation marker, or None. A damaged marker still
    freezes the page: it reads as moved with no known target."""
    path = Path(page_dir) / MARKER
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"error": "invalid marker"}
    except (OSError, ValueError):
        return {"error": "invalid marker"}


def tab_fragment(moved: dict, query: str = "") -> str:
    """The target address fragment for a moved page: its tab, plan or set,
    and the version a `?v=vN` link asked for."""
    tab = moved.get("tab") if moved.get("tab") in TABS else "review"
    params = [("view", tab)]
    if tab == "plans" and moved.get("id"):
        params.append(("plan", moved["id"]))
    if tab == "findings" and moved.get("id"):
        params.append(("set", moved["id"]))
    version = (urllib.parse.parse_qs(query).get("v") or [""])[0]
    if tab in ("review", "plans") and re.fullmatch(r"v[0-9]{1,10}", version):
        params.append(("v", version))
    return urllib.parse.urlencode(params)


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _hashes(page_dir: Path) -> dict:
    return {name: _sha(page_dir / name) for name in _MUTABLE}


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _title(page_dir: Path, meta: dict, fallback: str) -> str:
    current = meta.get("current")
    try:
        text = (page_dir / "versions" / f"{current}.html").read_text(encoding="utf-8", errors="replace")
        found = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        if found:
            title = " ".join(html.unescape(found[1]).split())
            if title:
                return title[:200]
    except (OSError, TypeError):
        pass
    return fallback[:200]


def _all_comments(store: dict):
    """(bucket, anchor, comment) over live and archived comments."""
    for bucket in ("anchors", "archived"):
        groups = store.get(bucket) or {}
        if isinstance(groups, list):  # a legacy archived list
            for comment in groups:
                if isinstance(comment, dict):
                    yield bucket, comment.get("anchor_id") or "", comment
            continue
        for anchor, items in groups.items():
            for comment in items if isinstance(items, list) else []:
                if isinstance(comment, dict):
                    yield bucket, anchor, comment


def comment_counts(comments) -> dict:
    """What a reviewer sees of a set of comments, as numbers."""
    result = dict.fromkeys(("comments", "cards", "verdicts", "earlier_verdicts", "replies", "open"), 0)
    for comment in comments:
        result["comments"] += 1
        result["cards"] += isinstance(comment.get("decision_request"), dict)
        result["verdicts"] += bool(isinstance(comment.get("decision"), dict) and comment["decision"].get("verdict"))
        history = comment.get("decision_history")
        result["earlier_verdicts"] += len(history) if isinstance(history, list) else 0
        replies = comment.get("replies")
        result["replies"] += len(replies) if isinstance(replies, list) else 0
        result["open"] += comment.get("status", "open") == "open"
    return result


def _clip(text: str, maximum: int = 200) -> str:
    text = " ".join(str(text or "").split()) or "Finding"
    return text if len(text) <= maximum else text[: maximum - 1] + "…"


def _archived_url(record: dict) -> str | None:
    from .urls import mounted_url
    if record.get("transport_error"):
        return None
    url = mounted_url(record.get("public_url") or record.get("url") or record.get("local_url"),
                      record.get("public_base_path"))
    if not url or not url.lower().startswith(("http://", "https://")):
        return None
    return url.split("#", 1)[0].split("?", 1)[0] + "?archived=1"


class Source:
    def __init__(self, project: str, slug: str, record: dict, tab: str, ident: str | None, target_slug: str):
        self.project, self.slug, self.record, self.tab = project, slug, record, tab
        self.dir = Path(record["slug_dir"]).resolve()
        default = slug[len(target_slug) + 1:] if slug.startswith(target_slug + "-") else slug
        self.ident = ident or (re.sub(r"[^a-z0-9-]", "-", default.lower()).strip("-")[:64] or "page")
        self.name = f"{project}/{slug}"


def _check_source(source: Source, target_dir: Path) -> list[str]:
    """Refuse what this command cannot place without losing it."""
    problems = []
    directory = source.dir
    if not (directory / "comments.json").is_file() or not (directory / "current.meta.json").is_file():
        problems.append(f"{source.name}: not a page directory (comments.json and current.meta.json required)")
        return problems
    moved = marker(directory)
    # This run freezes its sources before it reads them; a marker for this
    # same target (also one left by an interrupted run) is not a conflict.
    if moved and (moved.get("target") or {}).get("slug_dir") != str(Path(target_dir).resolve()):
        problems.append(f"{source.name}: already consolidated ({MARKER} exists)")
    if source.tab != "review":
        if (directory / "plans").is_dir() and any((directory / "plans").iterdir()):
            problems.append(f"{source.name}: has its own plans; make it the Review source or move its plans first")
        if source.tab != "library" and (directory / "copy.json").is_file():
            problems.append(f"{source.name}: has Library blocks; consolidate it into library")
        try:
            sets = _read_json(directory / "categories.json", {}).get("findings_sets") or []
        except (OSError, ValueError):
            sets = ["unreadable"]
        if sets:
            problems.append(f"{source.name}: has its own findings sets; make it the Review source")
        store = _read_json(directory / "comments.json", {})
        for _bucket, anchor, comment in _all_comments(store):
            category = comment.get("category")
            library_block = source.tab == "library" and str(comment.get("anchor_id") or anchor).startswith("copy:")
            if category not in (None, "review") and not (library_block and category in (None, "library")):
                problems.append(f"{source.name}: comment {comment.get('id')} is already in {category}; "
                                "make this page the Review source")
                break
    return problems


def build(target_dir: Path, target: tuple[str, str], sources: list[Source], *, now: str | None = None) -> dict:
    """Read every source and assemble the target in memory. No writes."""
    from .categories import load_categories, validate_plan_id
    from .cli import _item_numbers
    from .copy_state import load_copy, validate_copy
    from .extract import build_content_document, has_canvas_sentinels
    from .paths import BUS_ARCHIVE_ROOT
    from .project_state import load_project, validate_project
    from .review_history import review_history
    from .sync_server import _coerce_v2

    now = now or _now()
    reviews = [s for s in sources if s.tab == "review"]
    if len(reviews) != 1:
        raise ValueError("exactly one source must be the Review document (PROJECT/SLUG:review); "
                         "import other documents with :plans")
    names = [s.name for s in sources]
    if len(set(names)) != len(names) or len({s.dir for s in sources}) != len(sources):
        raise ValueError("each source page may be named once")
    idents = [(s.tab, s.ident) for s in sources if s.tab != "review"]
    if len(set(idents)) != len(idents):
        raise ValueError("two sources map to the same plan, findings set or Library item; give one an =ID")
    for source in sources:
        if source.tab != "review":
            validate_plan_id(source.ident)
        if Path(target_dir).resolve() == source.dir:
            raise ValueError("the target must be a new page directory")
    problems = [problem for source in sources for problem in _check_source(source, target_dir)]
    if problems:
        raise ValueError("cannot consolidate:\n  " + "\n  ".join(problems))

    primary = reviews[0]
    store = {"schema_version": 2, "anchors": {}, "archived": {}}
    read_state: dict = {}
    rounds: list[dict] = []
    plans: dict = {}
    findings_sets = list(load_categories(primary.dir)["findings_sets"])
    copy = load_copy(primary.dir)
    project = load_project(primary.dir)
    assets: dict = {}
    seen_ids: dict = {}
    per_source = {}
    origins: dict = {}
    hashes = {}

    for source in sources:
        hashes[source.name] = _hashes(source.dir)
        raw = _read_json(source.dir / "comments.json", {})
        source_store = _coerce_v2(raw)
        meta = _read_json(source.dir / "current.meta.json", {})
        title = _title(source.dir, meta, source.slug)
        numbers = _item_numbers(source_store)
        archived_url = _archived_url(source.record)
        originals = []
        on_pointer = 0  # Library: comments without a copy block of their own
        for bucket, anchor, original in _all_comments(source_store):
            identifier = original.get("id")
            if not identifier:
                raise ValueError(f"{source.name}: a comment has no id")
            if identifier in seen_ids:
                raise ValueError(f"comment id {identifier} is in both {seen_ids[identifier]} and {source.name}")
            seen_ids[identifier] = source.name
            originals.append(original)
            comment = json.loads(json.dumps(original))
            if not (isinstance(comment.get("number"), int) and not isinstance(comment.get("number"), bool)
                    and comment["number"] > 0) and numbers.get(identifier):
                comment["number"] = numbers[identifier]
            anchor = comment.get("anchor_id") or anchor
            if source.tab != "review":
                comment["moved_from"] = source.name
            if source.tab == "plans":
                comment.update(category="plans", doc="plan:" + source.ident)
            elif source.tab == "findings":
                comment["category"] = "findings"
                anchor = f"{source.ident}:{anchor}"
                if isinstance(comment.get("decision_request"), dict):
                    prompt = comment["decision_request"].get("prompt") or comment.get("text")
                    comment["finding"] = {"set": source.ident, "title": _clip(prompt)}
            elif source.tab == "library":
                comment["category"] = "library"
                if not str(anchor).startswith("copy:"):
                    anchor = "copy:" + source.ident
                    on_pointer += 1
            comment["anchor_id"] = anchor
            store[bucket].setdefault(anchor, []).append(comment)
            origins[identifier] = (source, original)

        for author, entries in (_read_json(source.dir / "read-state.json", {}) or {}).items():
            if not isinstance(entries, dict):
                continue
            mine = read_state.setdefault(author, {})
            for key, value in entries.items():
                if key in mine and mine[key] != value:
                    raise ValueError(f"read state for {author} {key} differs between pages")
                mine[key] = value

        bus = Path(source.record["bus_file"]) if source.record.get("bus_file") else None
        history = review_history(source.dir, bus, BUS_ARCHIVE_ROOT)
        for item in history["rounds"]:
            moved = {**item, "id": f"{source.name}:{item['id']}", "page": source.name}
            if source.tab == "plans":
                moved["doc"] = "plan:" + source.ident
            rounds.append(moved)

        versions = [entry for entry in meta.get("history", []) if isinstance(entry, dict)
                    and re.fullmatch(r"v[0-9]{1,10}", str(entry.get("version", "")))]
        if source.tab == "plans":
            documents = {}
            for entry in versions:
                # What the page's own server showed: content/ first, else the
                # baked version through the same extraction.
                content = source.dir / "content" / f"{entry['version']}.html"
                path = content if content.is_file() else source.dir / "versions" / f"{entry['version']}.html"
                if not path.is_file():
                    raise ValueError(f"{source.name}: version {entry['version']} has no file")
                text = path.read_text(encoding="utf-8", errors="replace")
                documents[entry["version"]] = (build_content_document(text, title=source.slug)
                                               if path != content and has_canvas_sentinels(text) else text)
            plans[source.ident] = {"meta": {"title": title, "current": meta.get("current"),
                                            "history": [{key: entry[key] for key in ("version", "ts", "label") if key in entry}
                                                        for entry in versions],
                                            "moved_from": source.name},
                                   "versions": documents}
            for path in sorted((source.dir / "assets").glob("*")) if (source.dir / "assets").is_dir() else []:
                if path.is_file() and not path.is_symlink():
                    body = path.read_bytes()
                    if path.name in assets and assets[path.name] != body:
                        raise ValueError(f"asset {path.name} differs between pages")
                    assets[path.name] = body
        elif source.tab == "findings":
            intro = f"Moved from {source.name} on {now[:10]}."
            if archived_url:
                intro += f" The original page, read-only: {archived_url}"
            entry = {"id": source.ident, "label": title, "intro": intro}
            if versions and versions[0].get("ts"):
                entry["created_at"] = versions[0]["ts"]
            findings_sets.append(entry)
        elif source.tab == "library":
            own = load_copy(source.dir)
            known = {block["id"] for block in copy["blocks"]}
            for block in own["blocks"]:
                if block["id"] in known:
                    raise ValueError(f"Library item {block['id']} exists in two pages; rename one first")
                copy["blocks"].append(block)
                known.add(block["id"])
            groups = {group["id"] for group in copy.get("groups", [])}
            for group in own.get("groups", []):
                if group["id"] not in groups:
                    copy.setdefault("groups", []).append(group)
            if not own["blocks"] or on_pointer:
                if source.ident in known:
                    raise ValueError(f"Library item {source.ident} already exists; give the page an =ID")
                text = (f"Moved here from {source.name} on {now[:10]} with its {len(originals)} comments; "
                        "History keeps every submitted round.\n")
                ops = [{"insert": text}]
                if archived_url:
                    ops += [{"insert": "The original page, read-only: "},
                            {"insert": archived_url, "attributes": {"link": archived_url}}, {"insert": "\n"}]
                if not any(group["id"] == "earlier-pages" for group in copy.get("groups", [])):
                    copy.setdefault("groups", []).append({"id": "earlier-pages", "label": "Earlier pages"})
                copy["blocks"].append({"id": source.ident, "title": title, "current": "moved",
                                       "group": "earlier-pages", "where": source.name, "status": "done",
                                       "revisions": [{"id": "moved", "created_at": now,
                                                      "author": {"id": "agent:annotate", "name": "Annotate"},
                                                      "status": "approved", "delta": {"ops": ops}}]})
        per_source[source.name] = {"tab": source.tab, "id": None if source.tab == "review" else source.ident,
                                   "title": title, "versions": len(versions), "rounds": len(history["rounds"]),
                                   "read_state": sum(len(v) for v in (_read_json(source.dir / "read-state.json", {}) or {}).values()
                                                     if isinstance(v, dict)),
                                   **comment_counts(originals)}

    links = [{"label": f"{s.name} → {s.tab.title()}", "url": url,
              "description": "The page before consolidation, read-only."}
             for s in sources if (url := _archived_url(s.record))]
    if links and not any(module.get("id") == "earlier-pages" for module in project["modules"]):
        candidate = {**project, "modules": [*project["modules"],
                     {"id": "earlier-pages", "title": "Earlier pages (read-only)", "kind": "links", "items": links[:50]}]}
        try:
            project = validate_project(candidate)
        except ValueError:
            pass  # A full project panel keeps its own modules; the links are also in the manifest.
    project.pop("updated_at", None)

    copy = validate_copy(copy) if copy["blocks"] else None
    rounds.sort(key=lambda item: str(item.get("ts") or ""))
    categories_by_id = {}
    for _bucket, _anchor, comment in _all_comments(store):
        categories_by_id[comment["id"]] = comment
    from .categories import comment_category
    for item in rounds:
        for answer in item.get("answers") or []:
            comment = categories_by_id.get(answer.get("comment_id"))
            if comment:
                answer["category"] = comment_category(comment)
                if answer.get("number") is None and comment.get("number"):
                    answer["number"] = comment["number"]
    return {"target": {"project": target[0], "slug": target[1], "dir": str(Path(target_dir).resolve())},
            "primary": primary, "sources": sources, "store": store, "read_state": read_state,
            "rounds": rounds, "plans": plans, "findings_sets": findings_sets, "copy": copy,
            "project": project, "assets": assets, "per_source": per_source, "origins": origins,
            "hashes": hashes, "at": now}


def tab_counts(store: dict) -> dict:
    from .categories import comment_category
    grouped: dict = {tab: [] for tab in TABS}
    for _bucket, _anchor, comment in _all_comments(store):
        grouped[comment_category(comment)].append(comment)
    return {tab: comment_counts(items) for tab, items in grouped.items()}


def _ignore(directory, names):
    return [name for name in names if name.startswith(".") or name.endswith(".lock") or name == MARKER]


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_target(result: dict) -> Path:
    """Write the target beside its final path, then move it into place."""
    final = Path(result["target"]["dir"])
    if final.exists():
        raise ValueError(f"target directory already exists: {final}")
    staging = final.with_name(f".{final.name}.consolidating-{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)
    primary = result["primary"]
    try:
        shutil.copytree(primary.dir, staging, symlinks=True, ignore=_ignore)
        for name in ("rounds.ndjson",):
            (staging / name).unlink(missing_ok=True)
        _write_json(staging / "comments.json", result["store"])
        _write_json(staging / "read-state.json", result["read_state"])
        with (staging / "rounds.ndjson").open("w", encoding="utf-8") as stream:
            for item in result["rounds"]:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        if result["findings_sets"]:
            _write_json(staging / "categories.json", {"schema_version": 1, "findings_sets": result["findings_sets"]})
        if result["copy"]:
            _write_json(staging / "copy.json", result["copy"])
        if result["project"]["modules"] or result["project"].get("title") or (primary.dir / "project.json").exists():
            _write_json(staging / "project.json", result["project"])
        for plan_id, plan in result["plans"].items():
            for version, text in plan["versions"].items():
                path = staging / "plans" / plan_id / "versions" / f"{version}.html"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            _write_json(staging / "plans" / plan_id / "meta.json", plan["meta"])
        for name, body in result["assets"].items():
            path = staging / "assets" / name
            if path.exists() and path.read_bytes() != body:
                raise ValueError(f"asset {name} differs between the Review page and a plan")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        _write_json(staging / MANIFEST, manifest(result))
        os.rename(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final


def manifest(result: dict) -> dict:
    return {"schema_version": 1, "at": result["at"], "target": result["target"],
            "sources": [{"page": s.name, "dir": str(s.dir), "tab": s.tab,
                         **({"id": s.ident} if s.tab != "review" else {}),
                         "archived_url": _archived_url(s.record)} for s in result["sources"]],
            "counts": result["per_source"], "tabs": tab_counts(result["store"])}


def verify(result: dict) -> list[str]:
    """Re-read the written target and compare it with what each source held."""
    from .categories import list_plans, load_categories
    from .copy_state import load_copy
    problems = []
    final = Path(result["target"]["dir"])
    store = _read_json(final / "comments.json", {})
    written = {comment["id"]: comment for _b, _a, comment in _all_comments(store)}
    for identifier, (source, original) in result["origins"].items():
        moved = written.get(identifier)
        if moved is None:
            problems.append(f"{source.name}: comment {identifier} is missing")
            continue
        for key in set(original) | set(moved):
            if key in _TAB_FIELDS:
                continue
            if original.get(key) != moved.get(key):
                problems.append(f"{source.name}: comment {identifier} field {key} changed")
        if original.get("number") not in (None, moved.get("number")):
            problems.append(f"{source.name}: comment {identifier} number changed")
    if len(written) != len(result["origins"]):
        problems.append(f"target holds {len(written)} comments; the sources held {len(result['origins'])}")
    read_state = _read_json(final / "read-state.json", {})
    for source in result["sources"]:
        for author, entries in (_read_json(source.dir / "read-state.json", {}) or {}).items():
            for key, value in (entries or {}).items() if isinstance(entries, dict) else []:
                if (read_state.get(author) or {}).get(key) != value:
                    problems.append(f"{source.name}: read state {author} {key} not kept")
        if source.tab in ("review", "plans"):
            meta = _read_json(source.dir / "current.meta.json", {})
            for entry in meta.get("history", []):
                version = entry.get("version")
                origin = source.dir / "versions" / f"{version}.html"
                if source.tab == "review":
                    copied = final / "versions" / f"{version}.html"
                    if _sha(origin) != _sha(copied):
                        problems.append(f"{source.name}: version {version} differs")
                elif not (final / "plans" / source.ident / "versions" / f"{version}.html").is_file():
                    problems.append(f"{source.name}: plan version {version} missing")
        if result["hashes"][source.name] != _hashes(source.dir):
            problems.append(f"{source.name}: changed while it was being consolidated")
    rounds = {json.loads(line)["id"] for line in (final / "rounds.ndjson").read_text(encoding="utf-8").splitlines() if line.strip()}
    if rounds != {item["id"] for item in result["rounds"]}:
        problems.append("rounds were not all written")
    plans = {plan["id"] for plan in list_plans(final)}
    if plans != set(result["plans"]) | {p["id"] for p in list_plans(result["primary"].dir)}:
        problems.append("plans were not all written")
    sets = {entry["id"] for entry in load_categories(final)["findings_sets"]}
    if sets != {entry["id"] for entry in result["findings_sets"]}:
        problems.append("findings sets were not all written")
    if result["copy"] and len(load_copy(final)["blocks"]) != len(result["copy"]["blocks"]):
        problems.append("Library items were not all written")
    return problems


def mark(source: Source, result: dict) -> None:
    body = {"schema_version": 1, "moved_at": result["at"], "page": source.name, "tab": source.tab,
            **({"id": source.ident} if source.tab != "review" else {}),
            "target": {"project": result["target"]["project"], "slug": result["target"]["slug"],
                       "slug_dir": result["target"]["dir"]}}
    path = source.dir / MARKER
    temporary = path.with_name(f".{MARKER}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def unmark(source: Source) -> None:
    (source.dir / MARKER).unlink(missing_ok=True)


def report(result: dict) -> dict:
    return {"target": result["target"], "sources": result["per_source"], "tabs": tab_counts(result["store"]),
            "rounds": len(result["rounds"]), "plans": sorted(result["plans"]),
            "findings_sets": [entry["id"] for entry in result["findings_sets"]],
            "library_items": len(result["copy"]["blocks"]) if result["copy"] else 0,
            "read_state": sum(len(v) for v in result["read_state"].values() if isinstance(v, dict))}
