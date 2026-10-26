"""The Windmill test profiles stay runnable against this checkout (agent-annotate-4zw)."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = tomllib.loads((ROOT / ".windmill/test-profiles.toml").read_text())


def _argv(value):
    return isinstance(value, list) and value and all(isinstance(part, str) and part for part in value)


def test_steps_and_profiles_are_argv_lists_with_limits():
    assert PROFILES["schema"] == 1
    assert all(_argv(step) for step in PROFILES["setup"] + PROFILES["toolchain"])
    assert _argv(PROFILES["assert_imports"])
    assert set(PROFILES["profiles"]) == {"fast", "full", "browser"}
    for name, profile in PROFILES["profiles"].items():
        assert _argv(profile["command"]), name
        assert 0 < profile["timeout_s"] <= 3600, name
        assert profile["capacity"] in {"heavy", "light"}, name
        assert profile["artifacts"] == ["junit.xml"], name
        # Every path the command names exists at this revision.
        for part in profile["command"][1:]:
            if part.startswith(("scripts/", "tests/")):
                assert (ROOT / part).exists(), (name, part)


def test_allowed_skips_name_real_skip_marked_tests():
    for profile in PROFILES["profiles"].values():
        for node in profile["allowed_skips"]:
            path, function = node.split("::")
            source = (ROOT / path).read_text()
            match = re.search(r"((?:@pytest\.mark\.[^\n]*\n)*)def " + re.escape(function) + r"\(", source)
            assert match and "skipif" in match[1], node


def test_environment_routes_scratch_and_junit_into_the_job():
    env = PROFILES["environment"]
    assert env["TMPDIR"] == "{tmp}"
    assert "--junitxml={artifacts}/junit.xml" in env["PYTEST_ADDOPTS"]
