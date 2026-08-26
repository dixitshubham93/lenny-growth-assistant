"""
tests/test_ship30.py — Tests for the Ship30Skill (Phase 6).
"""
import pytest

from skills.ship30.implementation.principles import (
    FORMATTING_RULES,
    GROUNDING_RULE,
    HOOK_RULE,
    STRUCTURAL_OUTLINE,
    TARGET_WORDS,
)
from skills.ship30.implementation.ship30_skill import Ship30Skill


def test_ship30_skill_build_prompt_with_context():
    """Verify prompt builder includes all principles and provided context."""
    skill = Ship30Skill()
    prompt = skill.build_prompt("Product-Market Fit", "Context: Brian Chesky... was awesome.")

    # Includes context
    assert "Brian Chesky... was awesome." in prompt
    assert "No relevant transcript material" not in prompt

    # Includes principles
    assert str(TARGET_WORDS) in prompt
    assert HOOK_RULE in prompt
    assert STRUCTURAL_OUTLINE in prompt
    assert FORMATTING_RULES in prompt
    assert GROUNDING_RULE in prompt
    assert "Topic**: Product-Market Fit" in prompt


def test_ship30_skill_build_prompt_empty_context():
    """Verify prompt builder explicitly instructs LLM about missing context."""
    skill = Ship30Skill()
    prompt = skill.build_prompt("Unknown topic", "   \n  ")

    assert "No relevant transcript material was found" in prompt
    assert str(TARGET_WORDS) in prompt
    assert HOOK_RULE in prompt
