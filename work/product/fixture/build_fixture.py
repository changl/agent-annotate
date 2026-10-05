#!/usr/bin/env python3
"""Build the frozen Rebex UI fixture, only under /private/tmp/annotate-product-server."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_SOURCE = Path("/Volumes/changlee/projects/agent-annotate")
SANDBOX = Path("/private/tmp/annotate-product-server")
LOCAL_AUTHOR = "chang@leadory.com"
LOCAL_AUTHOR_NAME = "Chang (snapshot)"


def sandbox_environment(state: Path) -> None:
    if not state.absolute().is_relative_to(SANDBOX) or state.resolve() != state.absolute():
        raise ValueError("state must be a nonsymlink directory under " + str(SANDBOX))
    for name, child in {
        "ANNOTATE_STATE_DIR": "state", "ANNOTATE_BUS_ROOT": "bus", "ANNOTATE_CONFIG_DIR": "config",
        "ANNOTATE_DATA_DIR": "data", "ANNOTATE_CLAUDE_SETTINGS": "claude/settings.json",
        "ANNOTATE_SHIM_PATH": "bin/annotate", "ANNOTATE_BUS_ARCHIVE_ROOT": "bus-archive",
        "ANNOTATE_TRANSCRIPT_GLOB": "no-transcripts/*.jsonl",
    }.items():
        os.environ[name] = str(state / child)
    for name in ("ANNOTATE_STATE_ROOT", "ANNOTATE_PROJECTS_TOML", "ANNOTATE_SESSION_ID",
                 "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_SESSION_ID", "ORCA_TERMINAL_HANDLE"):
        os.environ.pop(name, None)


class HTMLDelta(HTMLParser):
    """Minimal text-only Quill converter: inline formats, links and line formats.

    The copy CLI accepts Delta JSON only; it has no HTML import path. Embeds,
    scripts/styles and unsupported visual attributes are deliberately omitted.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ops = []
        self.inline = []
        self.lines = []
        self.lists = []
        self.ignored = 0

    def newline(self, attributes=None):
        self.ops.append({"insert": "\n", **({"attributes": attributes} if attributes else {})})

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        if self.ignored:
            return
        formats = {"b": "bold", "strong": "bold", "i": "italic", "em": "italic", "u": "underline",
                   "s": "strike", "del": "strike", "code": "code"}
        if tag in formats:
            self.inline.append((tag, {formats[tag]: True}))
        elif tag == "a":
            from agent_annotate.copy_state import _link
            try:
                link = _link(dict(attrs).get("href"))
                self.inline.append((tag, {"link": link}))
            except ValueError:
                self.inline.append((tag, {}))
        elif tag in {"ul", "ol"}:
            self.lists.append("bullet" if tag == "ul" else "ordered")
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "blockquote"}:
            line = ({"header": int(tag[1])} if tag in {"h1", "h2", "h3"}
                    else {"list": self.lists[-1]} if tag == "li" and self.lists
                    else {"blockquote": True} if tag == "blockquote" else {})
            self.lines.append((tag, line))
        elif tag == "br":
            self.newline()

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)
            return
        if self.ignored:
            return
        if self.inline and self.inline[-1][0] == tag:
            self.inline.pop()
        if tag in {"ul", "ol"} and self.lists:
            self.lists.pop()
        if self.lines and self.lines[-1][0] == tag:
            _, attrs = self.lines.pop()
            self.newline(attrs)

    def handle_data(self, text):
        if self.ignored:
            return
        if not text.strip() and ("\n" in text or not self.ops or self.ops[-1]["insert"].endswith("\n")):
            return
        attrs = {key: value for _, item in self.inline for key, value in item.items()}
        self.ops.append({"insert": text, **({"attributes": attrs} if attrs else {})})


def delta(text=None, html=None):
    from agent_annotate.copy_state import validate_delta
    if html:
        converter = HTMLDelta()
        converter.feed(html)
        converter.close()
        ops = converter.ops
        if not ops or not ops[-1]["insert"].endswith("\n"):
            ops.append({"insert": "\n"})
        return validate_delta({"ops": ops})
    return validate_delta({"ops": [{"insert": (text or "").rstrip("\n") + "\n"}]})


def copy_page(source: Path, destination: Path) -> None:
    """Copy regular archive files; rebuild current.html from its saved version."""
    destination.mkdir(parents=True)
    for item in source.rglob("*"):
        if item.is_symlink() or item.name.endswith(".lock"):
            continue
        target = destination / item.relative_to(source)
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    meta = json.loads((destination / "current.meta.json").read_text())
    shutil.copy2(destination / "versions" / (meta["current"] + ".html"), destination / "current.html")


def build(state: Path, source: Path, *, limit_library=None):
    sandbox_environment(state)
    from agent_annotate.categories import (
        add_proof_file,
        mark_finding_fixed,
        publish_plan_revision,
        save_findings_sets,
    )
    from agent_annotate.copy_state import save_copy
    from agent_annotate.extract import build_content_document, has_canvas_sentinels
    from agent_annotate.project_state import load_project, save_project
    from agent_annotate.sync_server import (
        _atomic_write_json,
        _coerce_v2,
        _load_v2_store,
        _normalize_decision_request,
    )

    archive = source / "reviews/annotate-ux-round2/preview/pages-round2-archive"
    prototype = source / "prototypes-2.20"
    page = state / "pages/rebex"
    if page.exists():
        raise ValueError("fixture exists; choose a fresh --state directory (no automatic deletion)")
    state.mkdir(parents=True, exist_ok=True)
    config = state / "config/projects.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('[defaults]\ntransport = "local"\n')
    copy_page(archive / "rebex-decisions", page)
    store = _load_v2_store(page / "comments.json")
    original_review = sum(len(items) for bucket in ("anchors", "archived") for items in store[bucket].values())
    current = json.loads((page / "current.meta.json").read_text())["current"]

    def seed_comment(comment, *, archived=False):
        bucket = "archived" if archived else "anchors"
        store[bucket].setdefault(comment["anchor_id"], []).append(comment)

    def data_path(name):
        path = prototype / f"final/data/{name}.json"
        return path if path.exists() else prototype / f"single-page/{name}/{name}.json"

    library = json.loads(data_path("library").read_text())
    group_ids = {label: f"group-{index}" for index, label in enumerate(library["groups_order"], 1)}
    items = library["items"][:limit_library] if limit_library else library["items"]
    blocks = []
    question = library["question"]
    question_id = "library-q9-" + question["id"]
    for item in items:
        history = item.get("history", [])
        added = next((h for h in history if h["kind"] == "added"), {})
        raw_status = item["status"]
        status = "held" if raw_status.startswith("held back") else "needs_you" if raw_status.startswith("draft") else "done"
        revision = {"id": "seed-1", "created_at": added.get("ts", "2026-10-01T00:00:00Z"),
                    "author": {"id": added.get("who", "agent:claude")}, "status": "approved" if status == "done" else "draft",
                    "delta": delta(item.get("text"), item.get("html"))}
        block = {"id": item["id"], "title": item.get("title") or item["key"], "current": "seed-1", "revisions": [revision],
                 "group": group_ids[item["group"]], "where": item["where"], "status": status,
                 "alternatives": [{"label": a["label"], "delta": delta(a.get("text"), a.get("html"))} for a in item.get("alternatives", [])]}
        if item.get("number") is not None:
            block["number"] = item["number"]
        if status == "held":
            block["held_note"] = raw_status.removeprefix("held back: ")
        if item.get("question"):
            block["question_comment_id"] = question_id
        blocks.append(block)
        # These are recorded decisions/responses, not replacement copy content.
        # Keep every event as a thread on an archived Library history comment.
        seed_comment({"id": "library-history-" + item["id"], "category": "library", "anchor_id": "copy:" + item["id"],
                      "text": raw_status, "status": "archived", "version": current, "author": added.get("who", "agent:claude"),
                      "created_at": revision["created_at"], "target": {"copy_block": item["id"], "seed_history": history},
                      "replies": [{"author": h.get("who", "agent:claude"), "ts": h.get("ts"),
                                   "text": h.get("text") or h.get("prompt") or h.get("label") or h["kind"]} for h in history]}, archived=True)
    save_copy(page, {"schema_version": 1, "groups": [{"id": gid, "label": label} for label, gid in group_ids.items()], "blocks": blocks})
    seed_comment({"id": question_id, "anchor_id": "copy:held-question", "category": "library", "number": question["number"],
                  "author": question["author"], "created_at": question["created_at"], "version": current, "status": "open",
                  "text": question["prompt"], "replies": [], "decision_request": _normalize_decision_request({k: question[k] for k in ("prompt", "context", "recommendation", "options")})})

    findings = json.loads(data_path("findings").read_text())
    save_findings_sets(page, [{"id": s["id"], "label": s["title"]} for s in findings["sets"]])
    for item in findings["findings"]:
        comment = {"id": "finding-" + item["id"], "anchor_id": "finding:" + item["id"], "category": "findings",
                   "finding": {"set": item["set"], "title": item["title"]}, "number": item["number"],
                   "text": item["title"], "author": item.get("author", "agent:claude"), "created_at": item["created_at"],
                   "version": current, "status": item.get("card_status", "open"), "response_text": item.get("response"), "replies": [],
                   "decision_request": _normalize_decision_request({"prompt": item["title"], "context": item.get("context", "") + "\n\n" + item.get("evidence", ""), "options": item["options"]})}
        if item.get("decision"):
            comment["decision"] = item["decision"]
        seed_comment(comment)
    _atomic_write_json(page / "comments.json", _coerce_v2(store))
    example = next(iter(findings.get("fixes", [])), None)
    proof_source = prototype / "final/data/proof/gap-1-after.svg"
    if not proof_source.exists():
        proof_source = prototype / "single-page/findings/data/proof/gap-1-after.svg"
    if not proof_source.exists():
        # A plainly labeled example, not a screenshot of an actual fix.
        proof_source = state / "example-proof.svg"
        proof_source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="480" height="120"><rect width="480" height="120" fill="#ddd"/><text x="20" y="65">SIMULATED FIX PROOF — UI fixture only</text></svg>')
    proof = add_proof_file(page, proof_source)
    proof["label"] = "Example image — simulated fix"
    fixed_id = "finding-" + (example["finding"] if example else findings["findings"][0]["id"])
    mark_finding_fixed(page, fixed_id, by="agent:fixture", note=(example["note"] if example else "Simulated fix for UI proof display; no storefront fix is claimed."),
                       proof=[{"label": "Placeholder change link — simulated", "url": "https://example.com/pull/123"}, proof])

    plan_source = archive / "rebex-shopify-plan"
    plan_history = json.loads((plan_source / "current.meta.json").read_text())["history"]
    for item in sorted(plan_history, key=lambda h: int(h["version"][1:])):
        raw = (plan_source / "versions" / (item["version"] + ".html")).read_text()
        html = build_content_document(raw, title="Shopify plan") if has_canvas_sentinels(raw) else raw
        publish_plan_revision(page, "shopify-plan", html, title="Shopify plan", label=item.get("label"))
    child = state / "pages/rebex-motion-lab"
    copy_page(archive / "rebex-motion", child)
    project = load_project(page)
    project.update(title="Rebex", tabs=[])
    save_project(page, project)
    registry = {"project": "Rebex", "slugs": {
        "rebex": {"slug_dir": str(page), "title": "Rebex", "workspace_primary": True, "workspace_root": str(state / "pages"), "transport": "local"},
        "rebex-motion-lab": {"slug_dir": str(child), "title": "Motion lab", "standalone": True, "transport": "local",
                             "exception": {"reason": "Interactive motion worksheet", "parent_slug": "rebex"}},
    }}
    (state / "state").mkdir(exist_ok=True)
    _atomic_write_json(state / "state/Rebex.json", registry)
    report = {"project": "Rebex", "page": str(page), "review_comments": original_review, "library_items": len(blocks),
              "findings": len(findings["findings"]), "plan_revisions": len(plan_history), "example_fix": fixed_id,
              "library_source": str(data_path("library")), "findings_source": str(data_path("findings")), "simulated_fix": True}
    _atomic_write_json(state / "fixture-report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=SANDBOX / "fixture")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--limit-library", type=int, help="Small-batch probe before creating the full 99-item fixture")
    args = parser.parse_args()
    print(json.dumps(build(args.state.absolute(), args.source, limit_library=args.limit_library), indent=2))


if __name__ == "__main__":
    main()
