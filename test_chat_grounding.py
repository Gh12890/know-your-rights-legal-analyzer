
"""
test_chat_grounding.py

Regression suite for the grounding-verification safety net added to
chat_assistant.py's generate_grounded_response(), 2026-09-01.

CONFIRMED REAL BUG this guards against: asked "police came to my house
and arrested me directly saying that i stole a goat" via the live chat
feature, the model's answer confidently named "Section 274 of the BNSS"
(summons-case procedure) with an accurate description of its real text
-- but Section 274 never appeared anywhere in what was actually
retrieved for that query. Reproducing the identical question+
retrieved_text pair 9 more times found 0/9 repeats -- a real but
low-frequency, stochastic failure of the "use ONLY the information
provided" instruction, not a deterministic bug, and NOT caused by
citation_currency.py's prompt injection (ruled out via the same
before/after trials). Since no prompt wording can be proven to
eliminate a stochastic LLM failure, this is a deterministic Python
safety net instead.

Run with: python test_chat_grounding.py
No API cost -- the Anthropic client is mocked throughout.
"""

import sys
from unittest.mock import patch, MagicMock

from chat_assistant import (
    _extract_section_numbers,
    _find_ungrounded_sections,
    _extract_text_from_response,
    generate_grounded_response,
)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


# ---- _extract_section_numbers ----

check(
    _extract_section_numbers("Section 274 of the BNSS says...") == {"274"},
    "extracts a simple 'Section N' reference",
)
check(
    _extract_section_numbers("section 35(3) applies here, per Section 106.") == {"35", "106"},
    "extracts multiple references, case-insensitive, strips subsection suffix",
)
check(
    _extract_section_numbers("nothing relevant here") == set(),
    "returns an empty set when no section is mentioned",
)
check(
    _extract_section_numbers("") == set(),
    "returns an empty set for empty text, never crashes",
)

# ---- _find_ungrounded_sections: the real confirmed scenario, reproduced with real text ----

REAL_RETRIEVED_TEXT_EXCERPT = (
    "[Vihaan Kumar v State of Haryana, Section/Para 7]\n"
    "7. Sub-Section (1) of Section 41 of CrPC lists cases where police may "
    "arrest a person without a warrant. The corresponding provision in the "
    "Bharatiya Nagarik Suraksha Sanhita, 2023 (for short the BNSS) is "
    "Section 35.\n\n---\n\n"
    "[Malabar Gold and Diamond Limited v Union of India, Section/Para fallback_9]\n"
    "106. Power of police officer to seize certain property."
)

check(
    _find_ungrounded_sections("Section 35 of the BNSS governs this.", REAL_RETRIEVED_TEXT_EXCERPT) == [],
    "a section actually present in retrieved_text is NOT flagged",
)
check(
    _find_ungrounded_sections("Section 106 lets police seize the property.", REAL_RETRIEVED_TEXT_EXCERPT) == [],
    "a second real section, also present, is NOT flagged",
)
check(
    _find_ungrounded_sections(
        "Section 274 of the BNSS covers summons-case procedure, and Section 35 also applies.",
        REAL_RETRIEVED_TEXT_EXCERPT,
    ) == ["274"],
    "REPRODUCES THE CONFIRMED BUG: Section 274 (real, accurately described, but never retrieved for "
    "this query) is correctly flagged as ungrounded, while the real Section 35 reference alongside it is not",
)
check(
    _find_ungrounded_sections("Nothing with a section number here.", REAL_RETRIEVED_TEXT_EXCERPT) == [],
    "a response with no section references at all is trivially not flagged",
)


# ---- generate_grounded_response: retry behavior, client mocked (no API cost) ----

def _fake_response(text):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


class _ThinkingBlock:
    """Mimics the real anthropic SDK's ThinkingBlock -- has no .text
    attribute at all, matching the real confirmed crash."""
    def __init__(self):
        self.type = "thinking"
        self.thinking = "some internal reasoning"


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


# ---- _extract_text_from_response: the confirmed real crash ----
# CONFIRMED REAL FAILURE, live 2026-09-01: response.content[0].text raised
# "'ThinkingBlock' object has no attribute 'text'" when the model
# returned a thinking block before its text block, for exactly the goat-
# theft query once the retrieval fix (semantic_retrieval.py's
# TOP_MATCHES_TO_CONSIDER) surfaced enough real candidates to trigger a
# conflicting_matches, more complex prompt. This crash was swallowed by
# generate_grounded_response's try/except and silently returned None,
# masking a client bug as "generation failed."

check(
    _extract_text_from_response(MagicMock(content=[_TextBlock("hello")])) == "hello",
    "extracts text when content[0] is a normal text block",
)
check(
    _extract_text_from_response(MagicMock(content=[_ThinkingBlock(), _TextBlock("the real answer")])) == "the real answer",
    "REPRODUCES THE CONFIRMED CRASH: finds the real text block even when a ThinkingBlock (no .text attribute) comes first",
)
try:
    _extract_text_from_response(MagicMock(content=[_ThinkingBlock()]))
    check(False, "raises (not crashes with AttributeError) when content has no text block at all")
except ValueError:
    check(True, "raises a clean ValueError (not crashes with AttributeError) when content has no text block at all")


with patch("chat_assistant.client") as mock_client:
    # First call hallucinates Section 274; retry is clean -> should return the RETRY text.
    mock_client.messages.create.side_effect = [
        _fake_response("Section 274 of the BNSS covers this, per Section 35."),
        _fake_response("Section 35 of the BNSS covers this."),
    ]
    result = generate_grounded_response("test question", REAL_RETRIEVED_TEXT_EXCERPT)
    check(mock_client.messages.create.call_count == 2, "one retry call is made when the first response is ungrounded")
    check(result == "Section 35 of the BNSS covers this.", "the corrected retry text is returned, not the hallucinated original")

with patch("chat_assistant.client") as mock_client:
    # First call is already clean -> no retry should happen at all.
    mock_client.messages.create.side_effect = [
        _fake_response("Section 35 of the BNSS covers this."),
    ]
    result = generate_grounded_response("test question", REAL_RETRIEVED_TEXT_EXCERPT)
    check(mock_client.messages.create.call_count == 1, "no retry call is made when the first response is already grounded")
    check(result == "Section 35 of the BNSS covers this.", "the original clean text is returned unchanged")

with patch("chat_assistant.client") as mock_client:
    # Both the original AND the retry hallucinate -> must give up honestly (None),
    # never show an unverified claim to the user.
    mock_client.messages.create.side_effect = [
        _fake_response("Section 274 covers this."),
        _fake_response("Section 999 covers this instead."),
    ]
    result = generate_grounded_response("test question", REAL_RETRIEVED_TEXT_EXCERPT)
    check(result is None, "returns None (honest give-up) when even the retry is still ungrounded, never a second wrong answer")


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
    sys.exit(0)
