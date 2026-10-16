from pathlib import Path


def test_provider_skill_contracts_stay_identical_and_concise():
    root = Path(__file__).parents[1]
    source = root / 'src/agent_annotate/skills'
    plugin = root / 'plugins/codex/agent-annotate/skills/annotate'
    contract_bytes = (source / 'claude/SKILL.md').read_bytes()
    assert contract_bytes == (source / 'codex/SKILL.md').read_bytes() == (plugin / 'SKILL.md').read_bytes()
    contract = contract_bytes.decode('utf-8')
    assert contract == (source / 'codex/SKILL.md').read_text() == (plugin / 'SKILL.md').read_text()
    for reference in (source / 'claude/references').glob('*.md'):
        assert reference.read_bytes() == (plugin / 'references' / reference.name).read_bytes()



def test_skill_has_one_format_reference_and_no_retired_instructions():
    root = Path(__file__).parents[1]
    source = root / "src/agent_annotate/skills/claude"
    assert {p.name for p in (source / "references").glob("*.md")} == {"page.md"}
    text = (source / "SKILL.md").read_text() + (source / "references/page.md").read_text()
    for retired in ("Chang", "Linear", "Cloudflare", "monitor", "annotate carry", "under 30 words"):
        assert retired not in text
    assert "one line and the URL" in text
