"""Goal 1 overhead budget: a model-free small round on this checkout must stay under budget."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("bench_budget", ROOT / "scripts" / "bench_budget.py")
budget = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(budget)


def test_small_round_stays_within_every_action_budget():
    result = budget.run_budget(ROOT / "src", answers=3, port=18761, python=sys.executable)
    assert result["over"] == [], budget.render(result) + "\n" + "\n".join(result["outputs"].values())
    m = result["measured"]
    assert m["small_round"]["commands"] == 3 and m["resolve_a_round"]["commands"] == 1
    assert m["ask_markup"]["tokens"] <= 10 and m["publish_small_update"]["input_ratio"] <= 1.2  # stage 3
    assert not any("http" in out for out in result["outputs"].values())  # no share link in any receipt


def test_budget_names_each_action_that_goes_over():
    limit = budget.budgets(3)
    measured = {a: {"commands": b["commands"], "tokens": b["tokens"]} for a, b in limit.items()}
    assert budget.over_budget(measured, limit) == []
    measured["resolve_a_round"]["commands"] = 3                     # one resolve per card, as before 2.28.3
    measured["read_one_round"]["tokens"] = limit["read_one_round"]["tokens"] + 1
    measured["publish_small_update"]["retries"] = 1
    measured["publish_small_update"]["input_ratio"] = 1.5          # republishing the whole page for one section
    assert budget.over_budget(measured, limit) == ["read_one_round", "resolve_a_round", "publish_small_update"]
    measured["publish_small_update"]["retries"] = 0
    assert "publish_small_update" in budget.over_budget(measured, limit)  # the input ratio alone
