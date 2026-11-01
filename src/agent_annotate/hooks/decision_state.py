"""Decision-state rules shared by the CLI and the standalone prompt hook."""

VERDICT_COLUMNS = ("accept", "reject", "changes", "comment", "select")
ANSWER_VERDICTS = VERDICT_COLUMNS


def is_live_card(comment: dict) -> bool:
    decision = comment.get("decision") if isinstance(comment.get("decision"), dict) else {}
    return (isinstance(comment.get("decision_request"), dict)
            and comment.get("status") not in ("archived", "resolved_in_version")
            and not (comment.get("status") == "addressed_by_agent"
                     and not decision.get("verdict") and not comment.get("fixed")))


def is_set_aside(comment: dict) -> bool:
    """Answer later: the page remembers it; agents never count it as undecided."""
    decision = comment.get("decision") if isinstance(comment.get("decision"), dict) else {}
    return bool(comment.get("answer_later") and comment.get("decision_request") and not decision.get("verdict"))


def is_undecided(card: dict) -> bool:
    return (not card.get("pending")
            and not card.get("answer_later")
            and not card.get("fixed")
            and card.get("verdict") not in ANSWER_VERDICTS)
