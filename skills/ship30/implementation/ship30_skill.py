"""
skills/ship30/implementation/ship30_skill.py — Ship 30 for 30 Skill

Framework-agnostic implementation compiled from explicit principles constants.
Called by AgentRunner for BOTH the Claude Agent SDK path and the Ollama native path.
"""
from __future__ import annotations

from skills.ship30.implementation.principles import (
    FORMATTING_RULES,
    GROUNDING_RULE,
    HOOK_RULE,
    STRUCTURAL_OUTLINE,
    TARGET_WORDS,
)


class Ship30Skill:
    """
    Builds the Ship 30 for 30 prompt from explicit encoded principles.

    Design contract:
    - `build_prompt()` is pure (no I/O) — fully testable without any LLM call.
    - Principles are stored in principles.py, not inline in application code.
    - The LLM (not keyword matching) decides when to invoke this skill via the
      'write_ship_30_essay' agent tool.
    """

    name: str = "write_ship_30_essay"
    description: str = (
        "Write a ~1,250-word Ship 30 for 30 style essay on a product or growth topic. "
        "Uses Lenny's Podcast transcript knowledge as the sole source."
    )

    def build_prompt(self, topic: str, context: str) -> str:
        """
        Return a fully-specified prompt that encodes all Ship 30 principles.

        Args:
            topic:   The essay subject (from the tool call argument).
            context: Retrieved transcript text (may be empty string if no chunks found).
        """
        if context.strip():
            context_block = (
                "## Transcript Context\n\n"
                "Use ONLY the following transcript material as your factual source:\n\n"
                f"{context}\n"
            )
        else:
            context_block = (
                "## Transcript Context\n\n"
                "No relevant transcript material was found for this topic. "
                "Clearly state in the essay that the available knowledge base "
                "does not contain sufficient material to ground this piece.\n"
            )

        return (
            f"You are writing a Ship 30 for 30 atomic essay.\n\n"
            f"**Topic**: {topic}\n\n"
            f"{context_block}\n"
            f"## Writing Requirements\n\n"
            f"**Target length**: Approximately {TARGET_WORDS} words.\n\n"
            f"**Hook rule**:\n{HOOK_RULE}\n\n"
            f"**Structure** (five parts):\n{STRUCTURAL_OUTLINE}\n\n"
            f"**Formatting**:\n{FORMATTING_RULES}\n\n"
            f"**Grounding rule**:\n{GROUNDING_RULE}\n\n"
            f"Write the complete Markdown essay now. "
            f"Begin directly with the hook sentence."
        )
