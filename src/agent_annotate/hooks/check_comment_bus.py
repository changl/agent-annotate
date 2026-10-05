#!/usr/bin/env python3
"""UserPromptSubmit notices for submitted rounds and immediate feedback.

Deferred decision clicks stay silent until Finish review or Send now. Each
owner gets one concise notice per page; reviewer prose remains in the inbox.
Hook cursors are per session and never consume the independent inbox cursor.
Bare-script and module invocation use the same roots. A prompt is never blocked.
A session's first prompt also gets one line when installed pieces differ from
the installed release (version_guard; module invocation only).
ANNOTATE_HOOK_DRY_RUN=1 writes nothing; ANNOTATE_HOOK_ALL=1 is diagnostic only.
"""

import json
import os
import select
import shutil
import signal
import sys
import time

HOME = os.path.expanduser("~")

try:
    from agent_annotate import paths as _paths
except ImportError:  # exec'd as a bare script by check-comment-bus.sh
    _paths = None

if _paths is not None:
    BUS_ROOT = str(_paths.BUS_ROOT)
    STATE = str(_paths.STATE_DIR)
else:
    BUS_ROOT = os.environ.get("ANNOTATE_BUS_ROOT") or os.path.join(
        HOME, ".claude", "annotate-bus")
    STATE = (os.environ.get("ANNOTATE_STATE_DIR") or os.environ.get("ANNOTATE_STATE_ROOT")
             or os.path.join(HOME, ".claude", "annotate-state", "state"))

# The cursor `inbox --unread` owns. Read here, NEVER written here.
INBOX_OFFSET_ROOT = os.path.join(STATE, "bus-offsets")
# The cursor this hook owns.
HOOK_OFFSET_ROOT = os.path.join(STATE, "hook-offsets")
LOCK_ROOT = os.path.join(STATE, "hook-locks")
LOG_FILE = os.path.join(STATE, "logs", "check-comment-bus.log")

DRY_RUN = os.environ.get("ANNOTATE_HOOK_DRY_RUN") == "1"

STALE_LOCK_SECONDS = 60
# The notice is prepended to a prompt, so it is charged to every turn. A page
# with twenty verdicts must not spend two kilobytes of context saying so; the
# ids are there to be acted on, and `inbox --unread` has the rest.
MAX_VERDICTS = 6

# Events that are machinery, not a reviewer saying something.
BOOKKEEPING_EVENTS = {
    "round_received",
    # D7: `annotate close` archiving stale unanswered cards. Nobody decided
    # anything, so it must not read as reviewer activity.
    "page_closed",
    "seen_updated",
    "comments_seeded",
    "decision_requested",
    "page_published",
    "page_publish_failed",
    "version_published",
    "notice_emitted",
    "inbox_read",
    "bulk_overwrite",
    "page_claimed",
    "monitor_armed",
    "monitor_exited",
    # The reviewer cleared their pending verdicts without sending. Nothing was
    # decided and no push follows, so there is nothing for a session to act on.
    "round_discarded",
}

_lock_dir = None


def _quiet_exit(code=0):
    sys.exit(code)


def _release_lock():
    if _lock_dir:
        try:
            os.rmdir(_lock_dir)
        except OSError:
            pass


def _on_signal(signum, frame):
    _release_lock()
    os._exit(0)


def _invocation() -> str:
    """How the notice tells the session to read its inbox.

    `annotate` only when the name on PATH really is this package (the uv
    entry point or the shim `install-shim` writes); otherwise the interpreter
    module form. A bare `annotate` that resolves to libgd's image tool is a
    lost turn.
    """
    found = shutil.which("annotate")
    if found:
        try:
            with open(found, "r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(4096)
            if "agent_annotate" in head or "agent-annotate shim" in head:
                return "annotate"
        except OSError:
            pass
    return "%s -m agent_annotate.cli" % (sys.executable or "python3")


def _version_notice(session_id: str):
    """One line, once per session, when the launcher, a skill, the Codex plugin
    or a live page differs from the installed release. Local files only; the
    bare-script path (no package) stays silent."""
    if _paths is None:
        return None
    try:
        from agent_annotate.version_guard import session_notice
        return session_notice(session_id, dry_run=DRY_RUN)
    except Exception:
        return None


def _safe_component(value: str) -> str:
    out = "".join(ch if (ch.isalnum() or ch in "._-") else "-" for ch in (value or ""))
    return out.strip("-") or "unknown"


def _read_stdin_payload() -> dict:
    """Claude Code hands hooks a JSON object on stdin. Never block on it."""
    try:
        if sys.stdin is None or sys.stdin.closed or sys.stdin.isatty():
            return {}
    except (ValueError, OSError):
        return {}
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.5)
        if not ready:
            return {}
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _session_id(payload: dict) -> str:
    for candidate in (
        payload.get("session_id"),
        os.environ.get("CLAUDE_CODE_SESSION_ID"),
        os.environ.get("CODEX_THREAD_ID"),
        os.environ.get("CLAUDE_SESSION_ID"),
    ):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return "unknown"


def _read_offset(path) -> int:
    try:
        with open(path, "rb") as fh:
            raw = fh.read(64).strip()
    except OSError:
        return 0
    if not raw or not raw.isdigit():
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _read_offset_or(path, seed: int) -> int:
    """A cursor this session has never held is SEEDED, not zeroed.

    Every page that exists today was scanned by the v2.18 hook, which advanced
    one shared cursor per slug on every prompt from any session. That value is
    therefore "everything up to about now" for every live page. Starting each
    session's new cursor at 0 instead would replay every page's entire history
    into every one of the ~13 live sessions on their next prompt — a storm, on
    the turn this ships.
    """
    if os.path.exists(path):
        return _read_offset(path)
    return seed


def _write_offset(path, value: int) -> None:
    if DRY_RUN:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("%d\n" % value)
        os.replace(tmp, path)
    except OSError:
        pass


def _load_registry() -> dict:
    """{(project, slug): record} from state/<project>.json."""
    out = {}
    try:
        names = sorted(os.listdir(STATE))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(STATE, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        project = data.get("project") or name[: -len(".json")]
        slugs = data.get("slugs")
        if not isinstance(slugs, dict):
            continue
        for slug, record in slugs.items():
            if isinstance(record, dict):
                out[(project, slug)] = record
    return out


def _load_cards(slug_dir: str) -> dict:
    """Decision cards from comments.json, keyed by comment id.

    The store shape is {"schema_version":…, "anchors": {anchor_id: [comment,…]},
    "archived": […]} — NOT {"comments": …}, which is what every first-attempt
    parse in the transcripts reached for.
    """
    cards = {}
    if not slug_dir:
        return cards
    path = os.path.join(slug_dir, "comments.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            store = json.load(fh)
    except (OSError, ValueError):
        return cards
    anchors = store.get("anchors") if isinstance(store, dict) else None
    if not isinstance(anchors, dict):
        return cards
    for items in anchors.values():
        if not isinstance(items, list):
            continue
        for c in items:
            if not isinstance(c, dict) or not c.get("decision_request"):
                continue
            if c.get("status") in ("archived", "resolved_in_version"):
                continue
            decision = c.get("decision") if isinstance(c.get("decision"), dict) else None
            if not decision and c.get("status") == "addressed_by_agent":
                continue  # addressed or withdrawn by the agent: not a live question
            cards[c.get("id")] = {
                "anchor_id": c.get("anchor_id"),
                "verdict": (decision or {}).get("verdict"),
                "text": (decision or {}).get("text") or "",
                "pending": bool((decision or {}).get("round_pending")),
            }
    return cards


def _is_reviewer_event(ev: dict) -> bool:
    """A human said something. Not machinery, not this agent's own writes.

    The author test is the load-bearing half, and it is deliberately positive:
    an event with no author at all is something the system did to itself, so a
    new bookkeeping event added later cannot silently start inflating counts
    just because nobody remembered to list it above.
    """
    name = ev.get("event")
    if not name or name in BOOKKEEPING_EVENTS or ev.get("deferred"):
        return False
    if name == "session_push" and (ev.get("round") or ev.get("decision")
                                   or not (ev.get("comment_ids") or ev.get("comment_count"))):
        return False  # Submitted rounds and immediate verdicts have their own events.
    author = ev.get("author") or ev.get("by") or ""
    if not isinstance(author, str) or not author.strip():
        return False
    return not author.startswith("agent:")


def _bus_append(bus_path: str, slug: str, event: dict) -> None:
    if DRY_RUN:
        return
    payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "slug": slug}
    payload.update(event)
    try:
        with open(bus_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _slug_line(project: str, slug: str, count: int, events: list, cards: dict,
               round_submitted: bool) -> str:
    """One notice line: what happened, what is still open, how to read it."""
    verdict_bits = []
    seen = set()
    for ev in events:
        ids = [ev["comment_id"]] if ev.get("comment_id") else ev.get("comment_ids", [])
        if not isinstance(ids, list):
            continue
        for cid in ids:
            if not isinstance(cid, str) or cid in seen:
                continue
            verdict = ev.get("decision") or (cards.get(cid) or {}).get("verdict")
            if not verdict:
                continue
            seen.add(cid)
            verdict_bits.append("%s %s" % (cid, verdict))

    total_cards = len(cards)
    undecided_ids = [cid for cid, c in cards.items() if not c.get("verdict")]
    undecided = len(undecided_ids)

    parts = ["[annotate] %s/%s: %d reviewer event(s) since your last read"
             % (project, slug, count)]
    if verdict_bits:
        head = verdict_bits[:MAX_VERDICTS]
        more = len(verdict_bits) - len(head)
        parts.append(" — verdicts: " + ", ".join(head)
                     + (f", +{more} more" if more > 0 else ""))
    if total_cards:
        parts.append("; undecided: %d of %d cards" % (undecided, total_cards))
    parts.append(". Read: %s inbox %s/%s --unread" % (_invocation(), project, slug))
    line = "".join(parts)
    if round_submitted:
        line = "ROUND SUBMITTED: " + line

    return line


def _scan(session_id: str) -> list:
    lines = []
    try:
        projects = sorted(os.listdir(BUS_ROOT))
    except OSError:
        return lines

    registry = _load_registry()
    hook_all = os.environ.get("ANNOTATE_HOOK_ALL") == "1"
    sid_dir = _safe_component(session_id)

    # `find -maxdepth 2` in the original shell hook also matched a .ndjson
    # sitting directly in the bus root, labelled with the bus dir's own name.
    scan = [(os.path.basename(BUS_ROOT.rstrip(os.sep)), BUS_ROOT)]
    scan += [(p, os.path.join(BUS_ROOT, p)) for p in projects
             if os.path.isdir(os.path.join(BUS_ROOT, p))]

    for project, pdir in scan:
        try:
            names = sorted(os.listdir(pdir))
        except OSError:
            continue

        for name in names:
            if not name.endswith(".ndjson"):
                continue
            bus_path = os.path.join(pdir, name)
            try:
                st = os.stat(bus_path)
            except OSError:
                continue
            if not os.path.isfile(bus_path):
                continue
            slug = name[: -len(".ndjson")]

            record = registry.get((project, slug))
            if record is None and not hook_all:
                # Retired or unpublished: no server, so nothing new can
                # arrive, and with no owner on record its backlog would be
                # announced to every session that has never read it.
                continue
            record = record or {}
            owner = record.get("owner_session")
            if owner and owner != session_id and not hook_all:
                # Another session published this page. Staying silent here is
                # the whole point: its verdicts are not this session's work.
                continue

            hook_offset_file = os.path.join(
                HOOK_OFFSET_ROOT, sid_dir, project, slug + ".offset")
            inbox_offset_file = os.path.join(
                INBOX_OFFSET_ROOT, sid_dir, project, slug + ".offset")
            # The v2.18 shared cursor, used as the seed for a cursor this
            # session does not have yet. The owner is the one exception, and
            # only for the inbox cursor: it is seeded at 0 so that the session
            # that published the page can still read its whole backlog once
            # with `inbox --unread`. The owner's HOOK cursor is seeded from the
            # legacy value like everyone else's, so that backlog arrives when
            # it is asked for rather than as an unprompted wall of text.
            legacy = _read_offset(os.path.join(
                INBOX_OFFSET_ROOT, project, slug + ".offset"))
            owned_by_me = bool(owner) and owner == session_id
            start = max(_read_offset_or(hook_offset_file, legacy),
                        _read_offset_or(inbox_offset_file,
                                        0 if owned_by_me else legacy))
            size = st.st_size
            if size <= start:
                continue

            try:
                with open(bus_path, "rb") as fh:
                    fh.seek(start)
                    data = fh.read()
            except OSError:
                continue

            events = []
            announced_ids = set()
            round_submitted = False
            for raw in data.decode("utf-8", errors="replace").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(ev, dict):
                    continue
                if not _is_reviewer_event(ev):
                    continue
                if ev.get("event") == "round_submitted":
                    if not owned_by_me and not hook_all:
                        continue  # An ownerless review stays queued, not broadcast.
                    round_submitted = True
                elif ev.get("event") == "session_push":
                    pushed = ev.get("comment_ids", [])
                    if isinstance(pushed, list) and pushed and all(cid in announced_ids for cid in pushed):
                        continue  # The same non-deferred action already appears above.
                events.append(ev)
                if ev.get("comment_id"):
                    announced_ids.add(ev["comment_id"])

            if events:
                cards = _load_cards(record.get("slug_dir") or "")
                lines.append(_slug_line(project, slug, len(events), events,
                                        cards, round_submitted))
                _bus_append(bus_path, slug, {
                    "event": "notice_emitted",
                    "session_id": session_id,
                    "slug": slug,
                    "count": len(events),
                    "offset_from": start,
                    "offset_to": size,
                })
                try:
                    size = os.stat(bus_path).st_size
                except OSError:
                    pass

            _write_offset(hook_offset_file, size)

    return lines


def main():
    global _lock_dir

    payload = _read_stdin_payload()
    session_id = _session_id(payload)

    notice = _version_notice(session_id)
    if notice:
        sys.stdout.write(notice + "\n")

    if DRY_RUN:
        try:
            for line in _scan(session_id):
                sys.stdout.write(line + "\n")
        except Exception:
            pass
        _quiet_exit()

    for d in (HOOK_OFFSET_ROOT, LOCK_ROOT, os.path.dirname(LOG_FILE)):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass

    if not os.path.isdir(BUS_ROOT):
        _quiet_exit()

    # Single-flight, per session: two prompts in the same session must not scan
    # at once, but one session's scan must never silence another's.
    _lock_dir = os.path.join(LOCK_ROOT, _safe_component(session_id) + ".lock.d")
    try:
        age = time.time() - os.stat(_lock_dir).st_mtime
        if age > STALE_LOCK_SECONDS:
            os.rmdir(_lock_dir)
    except OSError:
        pass
    try:
        os.mkdir(_lock_dir)
    except OSError:
        _lock_dir = None
        _quiet_exit()

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass

    try:
        lines = _scan(session_id)
    except Exception:
        # Never block a prompt on a bug in here.
        lines = []
    finally:
        _release_lock()

    if lines:
        for line in lines:
            sys.stdout.write(line + "\n")
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if DRY_RUN:
            _quiet_exit()
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                for line in lines:
                    fh.write("[check-comment-bus] %s session=%s — %s\n"
                             % (stamp, session_id, line))
        except OSError:
            pass

    _quiet_exit()


if __name__ == "__main__":
    main()
