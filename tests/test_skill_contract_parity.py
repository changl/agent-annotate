from pathlib import Path


def test_provider_skill_contracts_stay_identical_and_concise():
    root = Path(__file__).parents[1]
    source = root / 'src/agent_annotate/skills'
    plugin = root / 'plugins/codex/agent-annotate/skills/annotate'
    contract_bytes = (source / 'claude/SKILL.md').read_bytes()
    assert contract_bytes == (source / 'codex/SKILL.md').read_bytes() == (plugin / 'SKILL.md').read_bytes()
    contract = contract_bytes.decode('utf-8')
    assert contract == (source / 'codex/SKILL.md').read_text() == (plugin / 'SKILL.md').read_text()
    assert len(contract.split()) <= 500, 'Keep startup instructions concise; move detail to references'
    for reference in (source / 'claude/references').glob('*.md'):
        assert reference.read_bytes() == (plugin / 'references' / reference.name).read_bytes()


def test_skills_require_category_reuse_proof_and_explicit_orchestrator_exceptions():
    root = Path(__file__).parents[1]
    contract = (root / 'src/agent_annotate/skills/claude/SKILL.md').read_text()
    for instruction in ('one page per project', 'Review, Library, Findings, Plans',
                        'mark findings fixed only with proof', '--exception "REASON"',
                        'orchestrator must explicitly request'):
        assert instruction in contract
    assert 'modify installed skills only on explicit request' in contract
