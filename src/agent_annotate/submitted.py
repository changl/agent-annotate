"""The agent's view stops at the reviewer's last explicit Send."""

from copy import deepcopy


def human(author) -> bool:
    return bool(author) and not str(author).startswith("agent:")


def draft_event(event: dict) -> bool:
    name = str(event.get("event") or "")
    return bool(event.get("deferred") or (human(event.get("author") or event.get("by"))
                and (name.startswith("comment_") or name == "finding_reopened")))


def comment_view(comment: dict) -> dict | None:
    if "agent_snapshot" in comment:
        snapshot = deepcopy(comment["agent_snapshot"])
        if not isinstance(snapshot, dict):
            return None
        # Agent replies/proof may arrive while a reviewer is still drafting.
        for key in ("response_text", "resolved_in_version", "resolution_anchor_id"):
            if key in comment:
                snapshot[key] = deepcopy(comment[key])
        fixed = comment.get("fixed")
        if isinstance(fixed, dict) and fixed != snapshot.get("fixed") and str(fixed.get("by", "")).startswith("agent:"):
            for key in ("fixed", "fixed_history", "status"):
                if key in comment:
                    snapshot[key] = deepcopy(comment[key])
        replies = snapshot.get("replies") or []
        for reply in comment.get("replies") or []:
            if isinstance(reply, dict) and not human(reply.get("author")) and reply not in replies:
                replies.append(deepcopy(reply))
                snapshot["replies"] = replies
        return snapshot
    c = deepcopy(comment)
    decision = c.get("decision") if isinstance(c.get("decision"), dict) else {}
    pending = decision.get("round_pending") or decision.get("discarded")
    history = [d for d in c.get("decision_history") or []
               if isinstance(d, dict) and not d.get("round_pending") and not d.get("discarded")]
    if pending:
        c["decision"] = history[-1] if history else None
        c["status"] = "user_confirmed" if (c["decision"] or {}).get("verdict") == "accept" else "open"
    if "decision_history" in c:
        c["decision_history"] = history
    replies = [r for r in c.get("replies") or []
                    if isinstance(r, dict) and (not human(r.get("author")) or (
                        (bool(r.get("sent_at")) if "sent_at" in r else r.get("ts", "") <= c.get("flagged_at", ""))
                        and not (pending and r.get("ts") == decision.get("ts"))))]
    if "replies" in c:
        c["replies"] = replies
    if c.get("round_pending"):
        c.pop("round_pending", None)
        c["reopened"] = [r for r in c.get("reopened") or [] if isinstance(r, dict) and r.get("ts", "") <= c.get("flagged_at", "")]
        if c.get("fixed_history"):
            c["fixed"] = c["fixed_history"][-1]
            c["status"] = "addressed_by_agent"
    c.pop("answer_later", None)
    # Old stores have no snapshot; fail closed for unsent reviewer comments.
    if human(c.get("author")) and not c.get("flagged_for_session"):
        return None
    return c


def remember(comment: dict, author: str) -> None:
    if human(author) and "agent_snapshot" not in comment:
        comment["agent_snapshot"] = comment_view(comment)


def commit(comment: dict, delivery_id: str) -> None:
    comment.pop("agent_snapshot", None)
    comment["delivery_id"] = delivery_id
    decision = comment.get("decision") if isinstance(comment.get("decision"), dict) else {}
    if decision.get("round_pending"):
        decision["delivery_id"] = delivery_id
    for reply in comment.get("replies") or []:
        if isinstance(reply, dict) and human(reply.get("author")) and "sent_at" in reply and not reply["sent_at"]:
            reply["delivery_id"] = delivery_id
    if comment.get("round_pending") and comment.get("reopened"):
        comment["reopened"][-1]["delivery_id"] = delivery_id


def store_view(store: dict) -> dict:
    result = {**store, "anchors": {}, "archived": [] if isinstance(store.get("archived"), list) else {}}
    for area in ("anchors", "archived"):
        groups = store.get(area) or {}
        for anchor, comments in (groups.items() if isinstance(groups, dict) else [("", groups)]):
            single = isinstance(comments, dict)
            for comment in ([comments] if single else comments if isinstance(comments, list) else []):
                if isinstance(comment, dict) and (visible := comment_view(comment)) is not None:
                    bucket = ("archived" if visible.get("status") == "archived" else "anchors") if "agent_snapshot" in comment else area
                    if isinstance(result[bucket], list):
                        result[bucket].append(visible)
                    else:
                        key = (visible.get("anchor_id") if "agent_snapshot" in comment else anchor) or visible.get("anchor_id") or ""
                        if single and bucket == "archived":
                            result[bucket][key] = visible
                        else:
                            result[bucket].setdefault(key, []).append(visible)
    return result


def copy_view(document: dict) -> dict:
    document = deepcopy(document)
    for block in document.get("blocks", []):
        block["revisions"] = [r for r in block["revisions"] if not r.get("round_pending")]
    return document
