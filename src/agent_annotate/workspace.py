"""Find one project page across sessions and worktrees."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .urls import mounted_url, page_url

OWNER_FIELDS = ("owner_session", "owner_agent", "owner_label", "owner_claimed_at", "owner_target")


def project_key(path: Path) -> str | None:
    directory = path if path.is_dir() else path.parent
    while not directory.exists() and directory != directory.parent:
        directory = directory.parent
    try:
        common = subprocess.run(["git", "-C", str(directory), "rev-parse", "--git-common-dir"],
                                capture_output=True, text=True, timeout=3)
        if common.returncode:
            return None
        origin = subprocess.run(["git", "-C", str(directory), "config", "--get", "remote.origin.url"],
                                capture_output=True, text=True, timeout=3).stdout.strip()
        if origin.startswith(("https://", "ssh://", "http://")):
            parts = urlsplit(origin)
            if parts.hostname:
                return "git:" + parts.hostname.lower() + "/" + parts.path.strip("/").removesuffix(".git")
        elif "@" in origin and ":" in origin:
            host, repo = origin.split("@", 1)[1].split(":", 1)
            return "git:" + host.lower() + "/" + repo.strip("/").removesuffix(".git")
        return "local:" + str((directory / common.stdout.strip()).resolve())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _within(value, root) -> bool:
    try:
        Path(value).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError, TypeError):
        return False


def _record_key(record: dict) -> str | None:
    if record.get("workspace_key"):
        return record["workspace_key"]
    for field in ("workspace_root", "slug_dir"):
        if record.get(field) and (key := project_key(Path(record[field]))):
            return key
    worktree = (record.get("owner_target") or {}).get("worktree", "")
    if isinstance(worktree, str) and "::" in worktree:
        return project_key(Path(worktree.split("::", 1)[1]))
    return None


def candidates(path: Path, project: str | None = None, *, caller: Path | None = None) -> list[tuple[str, str, dict]]:
    from .cli import _registry_entries
    key = project_key(path) or (project_key(caller) if caller is not None else None)
    entries = [(name, slug, record, _record_key(record)) for name, slug, record in _registry_entries()
               if not record.get("standalone") and not record.get("exception")]
    roots = [r["workspace_root"] for _, _, r, record_key in entries if r.get("workspace_root") and (
             _within(path, r["workspace_root"]) or (caller is not None and _within(caller, r["workspace_root"]))
             or (key and key == record_key))]
    found = []
    for name, slug, record, record_key in entries:
        # A generic legacy registry label is not a repository identity.
        label_match = (not roots and project and name == project and not (key and record_key and key != record_key)
                       and not (key and name == "reviews"))
        if label_match or (key and key == record_key) or any(_within(record.get("slug_dir"), root) for root in roots):
            found.append((name, slug, record))
    return found


def duplicate_page(path: Path, project: str | None = None, *, caller: Path | None = None) -> dict | None:
    entries = candidates(path, project, caller=caller if caller is not None else Path.cwd())
    if any(Path(r["slug_dir"]).resolve() == path.resolve() for _, _, r in entries):
        return None
    for _, _, record in sorted(entries, key=lambda item: not item[2].get("workspace_primary")):
        if Path(record["slug_dir"]).resolve() != path.resolve():
            return record
    return None


def exception_reason(args) -> str | None:
    """An explicit exception, with the legacy standalone spelling preserved."""
    reason = getattr(args, "exception", None)
    if reason is not None:
        if not reason.strip():
            raise ValueError('--exception requires a nonempty reason')
        return reason.strip()
    return "standalone" if getattr(args, "standalone", False) else None


def duplicate_message(record: dict) -> str:
    return (f"ERROR: project page already exists: {record.get('slug') or Path(record['slug_dir']).name}\n"
            f"  Directory: {record['slug_dir']}\n  URL: {page_url(record)}\n"
            'Post into a category of this page: Review, Library, Findings, or Plans.\n'
            'A second page requires --exception "REASON".')


def _url_identity(url) -> tuple | None:
    try:
        parts = urlsplit(url)
        if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment):
            return None
        return (parts.scheme, parts.hostname.lower(), parts.port or (443 if parts.scheme == "https" else 80),
                parts.path.rstrip("/") or "/")
    except (TypeError, ValueError):
        return None


def _record_url(record: dict) -> str | None:
    if record.get("transport_error"):
        return None
    return mounted_url(record.get("public_url") or record.get("url") or record.get("local_url"),
                       record.get("public_base_path"))


def _shared_scope(primary: dict, child: dict) -> bool:
    key = primary.get("workspace_key")
    if key and key == child.get("workspace_key"):
        return True
    root = primary.get("workspace_root")
    return bool(root and _within(primary.get("slug_dir"), root) and _within(child.get("slug_dir"), root))


def workspace_tab_records(primary: dict) -> list[tuple[str, str, dict]]:
    """Exact registered, same-origin tabs inside the declared workspace; no keys or writes."""
    from .cli import _registry_entries
    from .project_state import load_project
    origin = _url_identity(_record_url(primary))
    if not origin or not primary.get("slug_dir"):
        return []
    try:
        tabs = load_project(primary["slug_dir"]).get("tabs", [])
    except (OSError, ValueError):
        return []
    entries = _registry_entries()
    primary_names = {primary.get("slug")} - {None}
    primary_names.update(name for project, slug, record in entries
                         if record.get("slug_dir") == primary.get("slug_dir")
                         for name in (slug, f"{project}/{slug}"))
    result = {}
    for tab in tabs:
        identity = _url_identity(tab.get("url"))
        if not identity or identity[:3] != origin[:3]:
            continue
        matches = [(p, s, r) for p, s, r in entries if _url_identity(_record_url(r)) == identity]
        if len(matches) != 1:
            continue
        project, slug, child = matches[0]
        if (child.get("standalone") or child.get("workspace_primary")
                or not _shared_scope(primary, child)
                or Path(child["slug_dir"]).resolve() == Path(primary["slug_dir"]).resolve()):
            continue
        result[(project, slug)] = (project, slug, child)
    # Explicit exception links do not require a manually declared project tab.
    # They remain independent owners (workspace_owner_record excludes them).
    for project, slug, child in entries:
        exception = child.get("exception")
        if not isinstance(exception, dict) or not _url_identity(_record_url(child)):
            continue
        parent = exception.get("parent_slug")
        if (parent in primary_names and _shared_scope(primary, child)
                and Path(child["slug_dir"]).resolve() != Path(primary["slug_dir"]).resolve()):
            result[(project, slug)] = (project, slug, child)
    return list(result.values())


def workspace_owner_record(record: dict) -> dict:
    """Listed tabs share their single canonical page's current durable owner."""
    from .cli import _registry_entries
    if record.get("standalone") or record.get("exception") or record.get("workspace_primary") or not record.get("slug_dir"):
        return record
    identity = _url_identity(_record_url(record))
    if not identity:
        return record
    parents = []
    for project, slug, primary in _registry_entries():
        origin = _url_identity(_record_url(primary))
        if not primary.get("workspace_primary") or not origin or origin[:3] != identity[:3] or not _shared_scope(primary, record):
            continue
        if any(Path(child["slug_dir"]).resolve() == Path(record["slug_dir"]).resolve()
               for _, _, child in workspace_tab_records(primary)):
            parents.append((project, slug, primary))
    if len(parents) != 1:
        return record
    project, slug, primary = parents[0]
    return {**record, **{key: primary.get(key) for key in OWNER_FIELDS},
            "workspace_owner": {"project": project, "slug": slug, "url": _record_url(primary)}}


def owner_data(record: dict) -> dict | None:
    """The durable recorded owner, including captured terminal display names."""
    record = workspace_owner_record(record)
    if not record.get("owner_session"):
        return None
    return {"owner_session": record["owner_session"], "owner_agent": record.get("owner_agent"),
            "owner_label": record.get("owner_label"), "claimed_at": record.get("owner_claimed_at"),
            "target": record.get("owner_target")}


def workspace_data(path: Path, project: str | None = None) -> dict:
    """Discover the canonical page without claiming, publishing, or writing state."""
    entries = candidates(path, project)
    primary = [item for item in entries if item[2].get("workspace_primary")]
    selected = primary[0] if len(primary) == 1 else entries[0] if len(entries) == 1 else None

    def page(item):
        name, slug, record = item
        return {"slug": f"{name}/{slug}", "directory": record["slug_dir"], "url": page_url(record),
                "owner": owner_data(record)}

    return {"workspace": page(selected) if selected else None, "pages": [page(item) for item in entries]}


def cmd_workspace(args) -> int:
    from .cli import (
        _flock,
        _load_state_for_project,
        _resolve_scoped_slug,
        _save_state_for_project,
        _state_lock_path,
    )
    if args.select:
        selected = _resolve_scoped_slug(args.select, args.project)
        if not selected:
            return 2
        project, slug, record = selected
        entries = candidates(Path.cwd(), project)
        root = Path(args.root).expanduser().resolve() if getattr(args, "root", None) else None
        if root:
            from .cli import _registry_entries
            if not root.is_dir() or not _within(record["slug_dir"], root):
                raise ValueError("workspace root must contain the selected page")
            entries.extend((p, s, r) for p, s, r in _registry_entries()
                           if not r.get("standalone") and not r.get("exception") and _within(r.get("slug_dir"), root))
        entries = list({(p, s): (p, s, r) for p, s, r in [*entries, selected]}.values())
        for name in sorted({p for p, _, _ in entries}):
            with _flock(_state_lock_path(name)):
                state = _load_state_for_project(name)
                for p, s, _ in entries:
                    if p == name and s in state["slugs"]:
                        state["slugs"][s]["workspace_primary"] = (p, s) == (project, slug)
                        if (p, s) == (project, slug):
                            state["slugs"][s]["workspace_key"] = project_key(Path.cwd())
                            if root:
                                state["slugs"][s]["workspace_root"] = str(root)
                            state["slugs"][s]["standalone"] = False
                            state["slugs"][s].pop("exception", None)
                _save_state_for_project(name, state)
        data = workspace_data(root or Path.cwd(), project)
    else:
        data = workspace_data(Path.cwd(), args.project)
    selected = data["workspace"]
    if args.json:
        print(json.dumps(data))
    elif selected:
        print(f"  Workspace: {selected['slug']}\n  Directory: {selected['directory']}\n  URL:       {selected['url']}")
    elif data["pages"]:
        print("Select the main page once: annotate workspace --select PROJECT/SLUG")
        for item in data["pages"]:
            print(f"  {item['slug']}  {item['url']}")
    else:
        print("No project page. Create one workspace with an explicit project name.")
    return 0
