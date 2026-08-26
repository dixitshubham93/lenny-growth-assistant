"""
skills/ship30/implementation/principles.py — Ship 30 for 30 Writing Constraints

All constraints are explicit constants — testable independently of the LLM.
These values encode the Ship 30 for 30 framework requirements from the assignment.
"""

# Target word count (±10%)
TARGET_WORDS: int = 1250

# The opening sentence rule
HOOK_RULE: str = (
    "Your opening sentence MUST create immediate curiosity or state a counter-intuitive truth. "
    "No preamble. No 'In this essay...' or 'Today I want to talk about...' openers."
)

# Five-part structural progression
STRUCTURAL_OUTLINE: str = (
    "1. Hook — One punchy sentence that earns the read.\n"
    "2. Problem/Context — Why this topic matters; what most people get wrong.\n"
    "3. Core Insight — The key product or growth lesson drawn from the transcript.\n"
    "4. Evidence/Proof — A specific example or data point from the transcript.\n"
    "5. Actionable Takeaway — One concrete thing the reader can do today."
)

# Formatting constraints for skimmability
FORMATTING_RULES: str = (
    "- Use Markdown headings (##) for each section.\n"
    "- Paragraphs: 2-3 sentences maximum.\n"
    "- Use bullet lists when enumerating 3 or more items.\n"
    "- Apply **bold** sparingly — only the single most critical phrase per section.\n"
    "- No filler sentences; every line earns its place."
)

# Strict grounding requirement
GROUNDING_RULE: str = (
    "CRITICAL: Every single claim, quote, and growth strategy in this essay MUST be derived "
    "exclusively from the provided transcript chunks. Do not add or invent any outside knowledge. "
    "If the provided context is EMPTY or does not contain enough evidence to write the essay, "
    "you MUST explicitly say that there is insufficient transcript evidence to write the essay and stop immediately. "
    "You must not fabricate episode or source details under any circumstances."
)
