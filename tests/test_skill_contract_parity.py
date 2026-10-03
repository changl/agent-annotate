from pathlib import Path


def test_provider_skill_contracts_stay_identical_and_concise():
    root = Path(__file__).parents[1]
    source = root / 'src/agent_annotate/skills'
    plugin = root / 'plugins/codex/agent-annotate/skills/annotate'
    contract = (source / 'claude/SKILL.md').read_text()
    assert contract == (source / 'codex/SKILL.md').read_text() == (plugin / 'SKILL.md').read_text()
    assert len(contract.split()) <= 500, 'Keep startup instructions concise; move detail to references'
    for reference in (source / 'claude/references').glob('*.md'):
        assert reference.read_text() == (plugin / 'references' / reference.name).read_text()
