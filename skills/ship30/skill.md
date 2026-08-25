# skill.md — Ship 30 for 30 Writing Skill
<!-- Placeholder. Do not implement until Phase 7 is reached. -->

## Purpose

This skill transforms grounded answers from the Lenny's Podcast knowledge base
into a Ship 30 for 30–style essay. The writing principles must be explicitly
encoded here, not buried in a one-off prompt.

## Ship 30 for 30 Writing Principles (to be formalised in Phase 7)

Reference: https://ship30for30.com/

Key constraints based on the framework:
- ~1,250 words per essay
- Strong hook (opening line must create curiosity or tension)
- Clear narrative progression (problem → insight → implication)
- Skimmable formatting: headings, bullets, selective bold
- One specific, actionable takeaway
- Every claim must be grounded in the transcript knowledge base
- No fluff; every sentence earns its place

## Skill Boundary (Architecture Intent)

The Ship 30 skill MUST have an explicit, testable boundary from the generic
assistant. This means:

1. The agent must explicitly route to this skill (not infer it from context).
2. The skill's prompt template lives here, not inline in application code.
3. The skill must be independently testable with a fixture input/output pair.
4. The writing principles are data/config, not magic strings in the LLM call.

## Proposed Directory Layout (Phase 7)

```
skills/ship30/
├── skill.md                  ← This file (principles + contract)
└── implementation/
    ├── __init__.py
    ├── ship30_skill.py       ← Skill class implementing the tool/skill interface
    ├── prompt_template.py    ← Explicit prompt template with writing principles
    └── tests/
        └── test_ship30.py   ← Unit tests for skill routing and output shape
```

## Status

- [ ] Principles researched and formalised (Phase 7)
- [ ] Prompt template written and reviewed (Phase 7)
- [ ] Skill class implemented (Phase 7)
- [ ] Agent routing wired (Phase 7)
- [ ] Unit tests passing (Phase 7)
