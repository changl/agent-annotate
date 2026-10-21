"""Page-owned display names; routes and revision titles are separate identities."""

from __future__ import annotations

import json
import re
import unicodedata
from html import unescape
from pathlib import Path


def validate_name(value: str) -> str:
    if not isinstance(value, str) or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("page name must be plain text without control characters")
    value = " ".join(value.split())
    if not value or len(value) > 160 or "<" in value or ">" in value:
        raise ValueError("page name must be 1–160 plain-text characters")
    return value


def _name(value) -> str | None:
    try:
        return validate_name(value)
    except ValueError:
        return None


def page_name(record: dict | Path | str, *, fallback: str = "Untitled page") -> str:
    """Resolve without writing, including legacy pages that have no saved name."""
    if not isinstance(record, dict):
        record = {"slug_dir": str(record)}
    directory = record.get("slug_dir")
    if directory:
        from .cli import _read_meta
        meta = _read_meta(Path(directory))
        name = _name(meta.get("name")) if isinstance(meta, dict) else None
        if name:
            return name
    name = _name(record.get("title"))
    if name:
        return name
    if directory:
        directory = Path(directory)
        from .cli import _registry_entries
        for _, _, registered in _registry_entries():
            if registered.get("slug_dir") == str(directory):
                name = _name(registered.get("title"))
                if name:
                    return name
        versions = sorted((p for p in (directory / "versions").glob("v*.html")
                           if re.fullmatch(r"v\d+", p.stem)), key=lambda p: int(p.stem[1:]))
        for path in [*versions, directory / "current.html"]:
            try:
                with path.open(encoding="utf-8") as source:
                    head = source.read(65536)
            except (OSError, UnicodeError):
                continue
            title = re.search(r"<title\b[^>]*>(.*?)</title\s*>", head, re.I | re.S)
            name = _name(unescape(title[1]).strip()) if title else None
            if name:
                return name
    return _name(fallback) or "Untitled page"


def set_page_name(directory: Path, title: str | None = None, *, initial_name: str | None = None) -> str:
    """Freeze the initial name; only an explicit title can change it later."""
    from .cli import _write_meta_locked
    name = validate_name(title) if title is not None else initial_name or page_name(directory)

    def update(meta):
        if title is not None or not _name(meta.get("name")):
            meta["name"] = name
    _write_meta_locked(directory, update)
    return page_name(directory)


def reference_record(url: str, entries: list) -> tuple | None:
    """Match a registered route exactly, ignoring only private review fragments."""
    from .urls import redact_review_key
    from .workspace import _record_url, _url_identity
    identity = _url_identity(redact_review_key(url))
    matches = [item for item in entries if identity and
               _url_identity(_record_url(item[2])) == identity]
    # Duplicate registrations of one directory still have one name.
    if matches and len({item[2].get("slug_dir") for item in matches}) == 1:
        return matches[0]
    return None


def project_payload(directory: Path | str, data: dict | None = None) -> dict:
    """Resolved project view, keeping legacy tab labels as derived aliases."""
    from .cli import _registry_entries
    from .project_state import load_project
    data = load_project(directory) if data is None else data
    entries = _registry_entries()
    data["name"] = page_name(directory)
    for tab in data.get("tabs", []):
        if not tab.get("url"):
            continue
        target = reference_record(tab["url"], entries)
        if target:
            _, slug, record = target
            tab.update(slug=slug, name=page_name(record))
        else:
            tab["name"] = tab.get("label") or "Untitled page"
        tab["label"] = tab["name"]
    # A simple collection for clients merging the legacy tab/link surfaces.
    from .project_state import linked_pages
    primary = next((r for _, _, r in entries if r.get("slug_dir") == str(directory)), None)
    data["related_pages"] = [{k: value for k, value in page.items() if k != "title"}
                             for page in linked_pages(primary)] if primary else []
    return data


def cmd_names(args) -> int:
    """Explicit migration map; dry runs do not create locks, backups or state."""
    import contextlib
    import datetime
    import hashlib
    import os

    from .cli import STATE_DIR, _flock, _registry_entries
    from .consolidate import refuse_if_moved
    from .project_state import load_project
    from .sync_server import _locked_store

    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate migration field: {key}")
            result[key] = value
        return result

    try:
        mapping = json.loads(Path(args.from_file).read_text(encoding="utf-8"), object_pairs_hook=unique_fields)
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("names file must map explicit PROJECT/SLUG identities to names")
        entries = _registry_entries()
        selected = {}
        for ref, value in mapping.items():
            matches = [(p, s, r) for p, s, r in entries if ref == f"{p}/{s}"]
            if len(matches) != 1:
                raise ValueError(f"no unique registered page for {ref!r}")
            record = matches[0][2]
            location = record.get("slug_dir")
            if not isinstance(location, str) or not Path(location).is_absolute() or not Path(location).is_dir():
                raise ValueError(f"registered page directory must exist and be absolute: {ref}")
            directory = Path(location).resolve()
            refuse_if_moved(directory)
            name = validate_name(value)
            if directory in selected:
                raise ValueError("names file must contain each page directory only once")
            selected[directory] = (ref, name, record)
        with contextlib.ExitStack() as locks:
            if args.apply:
                for directory in sorted(selected):
                    # Archive/consolidation and server stamp writes take this
                    # store lock before metadata locks; keep the same order.
                    locks.enter_context(_locked_store(directory))
                    for filename in ("current.meta.json", "project.json"):
                        locks.enter_context(_flock(directory / (filename + ".lock")))
            changes, pages, unresolved = [], [], []
            for directory, (ref, name, record) in selected.items():
                refuse_if_moved(directory)
                files = []
                for filename in ("current.meta.json", "project.json"):
                    path = directory / filename
                    if path.is_symlink():
                        raise ValueError(f"refusing symlinked metadata: {path}")
                    original = path.read_bytes() if path.exists() else None
                    data = json.loads(original) if original is not None else {}
                    if not isinstance(data, dict):
                        raise ValueError(f"metadata must be an object: {path}")
                    before = json.dumps(data, sort_keys=True)
                    if filename == "current.meta.json":
                        data["name"] = name
                    elif original is not None:
                        load_project(directory)  # validate before changing legacy references
                        for tab in data.get("tabs", []):
                            if not tab.get("url"):
                                continue
                            target = reference_record(tab["url"], entries)
                            if target:
                                tab.pop("label", None)
                            elif not tab.get("label"):
                                unresolved.append({"page": ref, "tab": tab["id"], "url": tab["url"]})
                    if json.dumps(data, sort_keys=True) != before:
                        encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
                        changes.append((path, original, encoded))
                        files.append(str(path))
                pages.append({"slug": ref, "name": name, "previous_name": page_name(record), "files": files})
            if args.apply and unresolved:
                raise ValueError("unresolved unlabeled references; fix the migration input first")
            backups = []
            if args.apply and changes:
                stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                for directory in selected:
                    local = [(p, old, new) for p, old, new in changes if p.parent == directory]
                    if not local:
                        continue
                    backup = STATE_DIR / "name-backups" / stamp / hashlib.sha256(str(directory).encode()).hexdigest()[:16]
                    backup.mkdir(parents=True, mode=0o700)
                    manifest = []
                    for path, original, _ in local:
                        if original is not None:
                            (backup / path.name).write_bytes(original)
                        manifest.append({"file": path.name, "existed": original is not None,
                                         "path": str(path),
                                         "sha256": hashlib.sha256(original).hexdigest() if original is not None else None})
                    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                    backups.append(str(backup))
                for path, original, encoded in changes:
                    if (path.read_bytes() if path.exists() else None) != original:
                        raise ValueError(f"metadata changed during migration: {path}; backups retained")
                    temporary = path.with_name(path.name + ".names.tmp")
                    try:
                        temporary.write_bytes(encoded)
                        os.replace(temporary, path)
                    finally:
                        temporary.unlink(missing_ok=True)
            result = {"dry_run": not args.apply, "pages": pages, "unresolved": unresolved,
                      "changed_files": len(changes), "backups": backups}
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                for page in pages:
                    print(f"{page['previous_name']} → {page['name']}: {len(page['files'])} files")
                print(f"{len(changes)} files; {len(unresolved)} unresolved references")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: names: {exc}")
        return 2
