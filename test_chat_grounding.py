
"""
test_chat_grounding.py

Regression suite for the deterministic safety nets around
chat_assistant.py's generate_grounded_response(): grounding verification
(2026-09-01) and cognizable/bailable verification (2026-09-01, Phase 2
of the chat-quality plan).

CONFIRMED REAL BUG the grounding net guards against: asked "police came
to my house and arrested me directly saying that i stole a goat" via
the live chat feature, the model's answer confidently named "Section
274 of the BNSS" (summons-case procedure) with an accurate description
of its real text -- but Section 274 never appeared anywhere in what was
actually retrieved for that query. Reproducing the identical question+
retrieved_text pair 9 more times found 0/9 repeats -- a real but
low-frequency, stochastic failure of the "use ONLY the information
provided" instruction, not a deterministic bug, and NOT caused by
citation_currency.py's prompt injection (ruled out via the same
before/after trials). Since no prompt wording can be proven to
eliminate a stochastic LLM failure, this is a deterministic Python
safety net instead.

CONFIRMED GAP the cognizable/bailable net closes: the grounding check
only proves a cited section NUMBER was really retrieved -- it says
nothing about whether the model's CLAIM about that section (cognizable?
bailable?) is correct. find_relevant_sections() already computes that
fact deterministically from BNS_SECTION_DATA (the same table the
compliance engine uses); nothing verified the model's prose against it.

Run with: python test_chat_grounding.py
No API cost -- the Anthropic client is mocked throughout.
"""

import sys
from unittest.mock import patch, MagicMock

from chat_assistant import (
    _extract_section_numbers,
    _find_ungrounded_sections,
    _extract_text_from_response,
    _explicit_section_matches,
    _bns_section_variants,
    _gather_offence_variants,
    _find_cognizable_bailable_mismatches,
    _format_mismatch,
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


# ---- _explicit_section_matches: "what is section N" lookup (real get_statute_section, no API) ----

from chat_assistant import _explicit_section_matches

m = _explicit_section_matches("what is section 318 of BNS")
check(len(m) == 1 and (m[0]["act"], m[0]["section_number"]) == ("BNS", "318"),
      "'section 318 of BNS' resolves to BNS 318 with real statute text")
check(bool(m[0].get("text")) and m[0]["source"] == "explicit_section_ref",
      "the resolved match carries real text and the explicit_section_ref source tag")

check(_explicit_section_matches("police said i violated section 420") == [],
      "'section 420' (a famous old IPC number, not in BNS) resolves to nothing -- no fabricated section")

mb = _explicit_section_matches("does BNSS 35 require a notice")
check(len(mb) == 1 and mb[0]["act"] == "BNSS" and mb[0]["section_number"] == "35",
      "an explicit 'BNSS 35' is looked up in BNSS, not BNS")

check(_explicit_section_matches("what are my rights if arrested") == [],
      "a question naming no section number yields no explicit match")

multi = _explicit_section_matches("compare section 303 and section 316 of BNS")
check({(x["act"], x["section_number"]) for x in multi} == {("BNS", "303"), ("BNS", "316")},
      "two explicitly named sections both resolve (capped at 2)")

# explicit BNS lookups now carry the Phase 2 enrichment via the shared
# _bns_section_as_match, so they must not have lost all_variants in the refactor
check(bool(_explicit_section_matches("what is section 318 of BNS")[0].get("all_variants")),
      "an explicit BNS section still carries the BNS_SECTION_DATA all_variants enrichment")


# ---- Phase 5: offence-keyword anchors (real get_statute_section, no API) ----

from chat_assistant import _offence_keyword_matches

goat = _offence_keyword_matches("police came to my house and arrested me saying that i stole a goat")
check(len(goat) == 1 and (goat[0]["act"], goat[0]["section_number"]) == ("BNS", "303"),
      "REAL-SHAPED GAP: 'stole a goat' anchors deterministically to BNS 303 (theft), not left to the embedding")
check(bool(goat[0].get("text")) and bool(goat[0].get("all_variants")),
      "the anchored match carries real statute text AND the cognizable/bailable enrichment")

check((_offence_keyword_matches("they are accusing me of cheating a customer")[0]["section_number"]) == "318",
      "'cheating' anchors to BNS 318")

check(_offence_keyword_matches("attempted to murder")[0]["section_number"] == "109"
      and _offence_keyword_matches("they say i murdered him")[0]["section_number"] == "103",
      "'attempt to murder' resolves to 109 BEFORE the bare 'murder' -> 103 (order matters)")

check(_offence_keyword_matches("what are my rights if the police arrest me") == [],
      "a message describing no specific offence yields no anchor")

check(len(_offence_keyword_matches("they say i stole the goat and also cheated the buyer")) == 1,
      "capped at one anchor even when the message names two offences -- no laundry list")


# ---- Phase 2: cognizable/bailable verification -- real BNS_SECTION_DATA, no API cost ----

BNS_318_VARIANTS = _gather_offence_variants(_explicit_section_matches("what is section 318 of BNS"))
BNS_303_VARIANTS = _gather_offence_variants(_explicit_section_matches("what is section 303 of BNS"))

# Distinct from REAL_RETRIEVED_TEXT_EXCERPT (which is about Sections 35/106,
# not 318) so the retry-integration tests below exercise ONLY the
# cognizable/bailable check -- using REAL_RETRIEVED_TEXT_EXCERPT with a
# "Section 318" answer would ALSO trip the (unrelated) grounding check,
# since "318" never appears in that excerpt, confounding the test.
BNS_318_RETRIEVED_TEXT = (
    "[BNS Section 318]\n"
    "318(4). Whoever cheats and thereby dishonestly induces the person "
    "deceived to deliver any property to any person shall be punished "
    "with imprisonment for a term which may extend to seven years, and "
    "shall also be liable to fine."
)

check(
    set(_bns_section_variants("318").keys()) == {"318(2)", "318(3)", "318(4)"},
    "_bns_section_variants('318') returns all three real subsection entries",
)
check(
    _bns_section_variants("999999") == {},
    "_bns_section_variants for a non-existent section returns {}, never crashes",
)
check(
    _gather_offence_variants([]) == {} and _gather_offence_variants(None) == {},
    "_gather_offence_variants handles an empty/None match list",
)
check(
    _gather_offence_variants([{"all_variants": {"a": 1}}, {"all_variants": {"b": 2}}]) == {"a": 1, "b": 2},
    "_gather_offence_variants merges all_variants across every match fed to the prompt",
)

check(
    _find_cognizable_bailable_mismatches("Section 318(4) is cognizable and non-bailable.", BNS_318_VARIANTS) == [],
    "a CORRECT cognizable/bailable claim for a single-condition section is not flagged",
)
_wrong = _find_cognizable_bailable_mismatches(
    "Section 318(4) is non-cognizable and bailable, punishable up to 7 years.", BNS_318_VARIANTS
)
check(
    len(_wrong) == 2 and {p["field"] for p in _wrong} == {"cognizable", "bailable"},
    "REPRODUCES A REAL-SHAPED FAILURE: a wrong cognizable/bailable claim for 318(4) is flagged on both fields",
)
_wrong_by_field = {p["field"]: p for p in _wrong}
check(
    all(p["section"] == "318(4)" for p in _wrong)
    and _wrong_by_field["cognizable"]["claimed"] is False   # text said "non-cognizable"
    and _wrong_by_field["bailable"]["claimed"] is True,     # text said "bailable"
    "each flagged problem carries the exact section and the model's (wrong) claimed value",
)
check(
    "Section 318(4) is cognizable, not non-cognizable as you wrote." in {_format_mismatch(p) for p in _wrong},
    "_format_mismatch renders a clear, specific correction sentence",
)

check(
    _find_cognizable_bailable_mismatches(
        "Section 303(2) is cognizable and non-bailable in the general case.", BNS_303_VARIANTS
    ) == [],
    "303(2) general-case claim NOT flagged -- a real, valid answer for this multi-condition section",
)
check(
    _find_cognizable_bailable_mismatches(
        "Section 303(2) is non-cognizable and bailable if the value is under Rs.5,000 and returned.",
        BNS_303_VARIANTS,
    ) == [],
    "303(2) low-value-carveout claim ALSO not flagged -- the other real, valid answer for the same "
    "section (this is the exact goat-theft fact pattern) -- no false positive on genuine ambiguity",
)
check(
    _find_cognizable_bailable_mismatches("Section 303 covers theft and is cognizable.", BNS_303_VARIANTS) == [],
    "a bare 'Section 303' mention (no subsection) is not flagged even though 303(2)'s two conditions "
    "disagree -- genuinely ambiguous from the number alone, so this stays silent rather than guessing",
)

check(
    _find_cognizable_bailable_mismatches("nothing about any section here", BNS_318_VARIANTS) == [],
    "a response naming no section is trivially not flagged",
)
check(
    _find_cognizable_bailable_mismatches("Section 318(4) is cognizable.", {}) == [],
    "an empty variants dict (no matches carried BNS_SECTION_DATA, e.g. a judgment-only answer) is a pure no-op",
)


with patch("chat_assistant.client") as mock_client:
    # First response gets 318(4)'s status backwards; retry corrects it ->
    # the CORRECTED retry text is returned, mirroring the ungrounded-retry
    # contract exactly (same "one retry, then trust or give up" shape).
    mock_client.messages.create.side_effect = [
        _fake_response("Section 318(4) is non-cognizable and bailable, up to 7 years."),
        _fake_response("Section 318(4) is cognizable and non-bailable, up to 7 years."),
    ]
    result = generate_grounded_response(
        "test question", BNS_318_RETRIEVED_TEXT,
        matches=[{"all_variants": BNS_318_VARIANTS}],
    )
    check(mock_client.messages.create.call_count == 2, "a wrong cognizable/bailable claim triggers exactly one retry")
    check(result == "Section 318(4) is cognizable and non-bailable, up to 7 years.",
          "the corrected retry text is returned")

with patch("chat_assistant.client") as mock_client:
    # Both the original AND the retry get it wrong -> give up honestly (None).
    mock_client.messages.create.side_effect = [
        _fake_response("Section 318(4) is non-cognizable and bailable."),
        _fake_response("Section 318(4) is non-cognizable and bailable."),
    ]
    result = generate_grounded_response(
        "test question", BNS_318_RETRIEVED_TEXT,
        matches=[{"all_variants": BNS_318_VARIANTS}],
    )
    check(result is None, "returns None when even the retry still has the wrong cognizable/bailable claim")

with patch("chat_assistant.client") as mock_client:
    # Correct on the first try -> no retry call, matches param is a pure
    # backward-compatible no-op when the answer is already right.
    mock_client.messages.create.side_effect = [
        _fake_response("Section 318(4) is cognizable and non-bailable."),
    ]
    result = generate_grounded_response(
        "test question", BNS_318_RETRIEVED_TEXT,
        matches=[{"all_variants": BNS_318_VARIANTS}],
    )
    check(mock_client.messages.create.call_count == 1, "no retry call when the claim is already correct")
    check(result == "Section 318(4) is cognizable and non-bailable.", "the original text is returned unchanged")

with patch("chat_assistant.client") as mock_client:
    # matches=None (every pre-Phase-2 call site/test shape) -> the
    # cognizable/bailable check is a guaranteed no-op, ungrounded-only
    # behavior is completely unchanged.
    mock_client.messages.create.side_effect = [
        _fake_response("Section 35 of the BNSS covers this."),
    ]
    result = generate_grounded_response("test question", REAL_RETRIEVED_TEXT_EXCERPT)
    check(mock_client.messages.create.call_count == 1,
          "backward compatibility: matches=None makes zero difference to the ungrounded-only path")
    check(result == "Section 35 of the BNSS covers this.", "unchanged result for a call with no matches param")


# ---- old IPC/CrPC -> BNS/BNSS translation in retrieved judgment text ----
# (statute_concordance wired into format_retrieved_text_for_prompt, 2026-09-02)

from chat_assistant import _old_code_equivalents, _old_code_refs_note, format_retrieved_text_for_prompt

_JUDG = ("The petitioner was booked under Section 420 of the Indian Penal Code "
         "and the arrest ignored Section 41A of the Code of Criminal Procedure, 1973. "
         "A separate charge under Section 124A IPC was also pressed.")

eqs = _old_code_equivalents(_JUDG)
pairs = {(e["old"], e["new"]) for e in eqs}
check(("IPC 420", "BNS 318(4)") in pairs,
      "judgment text 'Section 420 IPC' -> BNS 318(4) equivalent extracted")
check(any(e["old"] == "CrPC 41A" and e["new"] and "BNSS 35(3)" in e["new"] for e in eqs),
      "'Section 41A of the Code of Criminal Procedure' -> BNSS 35(3)")
check(any(e["old"] == "IPC 124A" and e["new"] is None for e in eqs),
      "repealed 'Section 124A IPC' surfaces with new=None (no re-enacted successor)")
check(any(e["old"] == "IPC 420" and e["changed"] is False for e in eqs)
      and any(e["old"] == "CrPC 41A" for e in eqs),
      "the change flag rides along per-mapping")

check(_old_code_equivalents("your rights on arrest, plainly stated, no section numbers") == [],
      "plain text with no old-code citation -> no equivalents, no false positives")
check(_old_code_equivalents("This turns on Section 35 of the BNSS and Section 103 BNS") == [],
      "a NEW-code 'Section 35 BNSS' reference is never mistaken for an old-code one")

note = _old_code_refs_note(_JUDG)
check("IPC 420 -> BNS 318(4)" in note and "not re-enacted: IPC 124A" in note,
      "the prompt note is one compact line: current equivalents + not-re-enacted list")
check(note.startswith("\n\n[") and note.rstrip().endswith("]")
      and "\n" not in note.strip(),
      "the note stays terse (single appended line) so it can't crowd the answer")

# end to end: format_retrieved_text_for_prompt appends the note to a judgment match,
# and the modern numbers become part of retrieved_text (so the grounding net treats
# an answer that cites BNS 318(4) as grounded, not a hallucination)
rt = format_retrieved_text_for_prompt([{"case_name": "Some v State", "paragraph_number": "7", "text": _JUDG}])
check("318(4)" in rt and "35(3)" in rt,
      "format_retrieved_text_for_prompt folds the modern numbers into retrieved_text")
check(_find_ungrounded_sections("This is now Section 318 of the BNS.", rt) == [],
      "an answer citing the concordance-supplied modern section is NOT flagged ungrounded")


# ---------------------------------------------------------------------------
# extract_arrest_situation -- the bounded fact-extraction for the chat draft
# (client mocked, no API). EXTRACTION ONLY -- decides no verdict.
# ---------------------------------------------------------------------------
from chat_assistant import extract_arrest_situation

_EXTRACT_JSON = """{
  "sections_cited": ["303"],
  "arrestee_gender": "male",
  "arrest_datetime_full": null,
  "production_datetime_full": null,
  "chargesheet_filed_date": null,
  "punishment_years_upper_bound": null,
  "41A_or_35_BNSS_notice_issued_before_arrest": false,
  "grounds_of_arrest_in_writing_furnished_to_arrestee": "unclear",
  "witness_attested_memo": "unclear",
  "family_or_friend_informed": "unclear",
  "medical_exam_at_arrest_recorded": false,
  "female_officer_present_for_female_arrestee": "not applicable",
  "matters_raised": ["he was slapped and kept awake all night", "handcuffed to the hospital bed"]
}"""

with patch("chat_assistant.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response(_EXTRACT_JSON)]
    fields, matters = extract_arrest_situation("user: my uncle was picked up for theft and beaten in custody")
    check(fields is not None, "extract_arrest_situation parses a clean JSON response")
    check(fields["sections_cited"] == ["303"] and fields["medical_exam_at_arrest_recorded"] is False,
          "compliance fields come through; 'no medical' -> False, not 'unclear'")
    check("matters_raised" not in fields, "matters_raised is split out of the fields dict")
    check(matters == ["he was slapped and kept awake all night", "handcuffed to the hospital bed"],
          "matters_raised carries the verbatim-ish grievance phrases")

_EXTRACT_JSON_NO_SEC = _EXTRACT_JSON.replace('"sections_cited": ["303"]', '"sections_cited": []')
with patch("chat_assistant.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response(_EXTRACT_JSON_NO_SEC)]
    fields, _ = extract_arrest_situation("user: my uncle was picked up for theft and beaten in custody")
    check(fields["sections_cited"] == ["303"],
          "when the person says 'theft' but no number, the offence-keyword anchor supplies BNS 303")

with patch("chat_assistant.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response("I can't do that")]
    f, m = extract_arrest_situation("something")
    check(f is None and m == [], "an unparseable response -> (None, []), never a raise")

with patch("chat_assistant.client", None):
    check(extract_arrest_situation("x") == (None, []), "client unavailable -> (None, [])")

check(extract_arrest_situation("   ") == (None, []), "blank conversation -> (None, []), no call")


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
    sys.exit(0)
