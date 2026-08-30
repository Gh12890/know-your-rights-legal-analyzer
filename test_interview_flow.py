
"""
test_interview_flow.py

Regression suite for interview_flow.py, covering real bugs found and
fixed during the 2026-08-29 session -- NOT hypothetical edge cases.
Every test here corresponds to an actual confirmed failure observed in
a live conversation, caught by hand at the time. This file exists so
the SAME class of regression is caught automatically going forward,
rather than requiring another multi-hour live-debugging session like
today's.

Uses real assert-and-record checks (fails loudly, no manual reading
required) alongside print output, extending test_integration.py's
existing print-style convention rather than replacing it.

COST NOTE: tests marked [LIVE API] make real calls (semantic search
embeddings, Haiku field extraction) and incur small real costs. Tests
marked [PURE] only exercise deterministic Python logic and are free to
run as often as you like.

Run with: python test_interview_flow.py
"""

import sys

from interview_flow import (
    InterviewState,
    suggest_offence,
    _infer_gender_from_text,
    extract_field_from_answer,
)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


print("\n" + "=" * 70)
print("GENDER INFERENCE TESTS [PURE -- no API calls]")
print("=" * 70)

check(
    _infer_gender_from_text("they arrested my brother for theft") == "male",
    "infers male from 'brother'"
)
check(
    _infer_gender_from_text("my sister was taken by police") == "female",
    "infers female from 'sister'"
)
check(
    _infer_gender_from_text("they arrested my husband") == "male",
    "infers male from 'husband'"
)
check(
    _infer_gender_from_text("they arrested my cousin") is None,
    "does NOT infer from 'cousin' (deliberately ambiguous, excluded from vocabulary)"
)
check(
    _infer_gender_from_text("they arrested a person near my sonny's shop") is None,
    "does NOT false-positive-match 'son' inside 'sonny' (word-boundary check)"
)
check(
    _infer_gender_from_text("they arrested someone at the market") is None,
    "returns None when no relationship word is present at all"
)


print("\n" + "=" * 70)
print("TIER LOGIC TESTS [PURE -- no API calls]")
print("=" * 70)

state = InterviewState()
state.offence_confirmed = True
state.offence_plain_language = "theft"
state.fields["sections_cited"] = ["303"]

questions_seen = []
for _ in range(10):
    result = state.next_question()
    if result is None:
        break
    field_name, question_text = result
    questions_seen.append(field_name)
    state.fields[field_name] = "no"

check(
    len(questions_seen) == 5,
    f"Tier 1 asks exactly 5 questions before exhausting (got {len(questions_seen)}: {questions_seen})"
)
check(
    state.active_tier == 1,
    "active_tier stays 1 until explicitly advanced (never auto-advances)"
)

state.advance_to_tier_2()
check(state.active_tier == 2, "advance_to_tier_2() correctly sets active_tier to 2")

tier_2_questions_seen = []
for _ in range(10):
    result = state.next_question()
    if result is None:
        break
    field_name, question_text = result
    tier_2_questions_seen.append(field_name)
    state.fields[field_name] = "no"

check(
    len(tier_2_questions_seen) == 5,
    f"Tier 2 asks exactly 5 more questions before exhausting (got {len(tier_2_questions_seen)}: {tier_2_questions_seen})"
)
check(
    len(set(questions_seen) & set(tier_2_questions_seen)) == 0,
    "Tier 1 and Tier 2 questions never overlap"
)


print("\n" + "=" * 70)
print("OFFENCE IDENTIFICATION TESTS [LIVE API -- real cost incurred]")
print("=" * 70)

try:
    result = suggest_offence("they arrested my brother last night for theft")
    check(
        result is not None,
        "suggest_offence returns a real suggestion for a clear theft description"
    )
    if result:
        check(
            result["section_number"] == "303",
            f"correctly identifies Section 303 for theft (got {result.get('section_number')!r}) "
            f"-- REGRESSION TEST: this exact phrase previously matched Section 60 before the "
            f"offence-phrase-extraction fix"
        )
        check(
            result["plain_offence_name"] == "theft",
            f"plain_offence_name is the real word 'theft', not a fallback placeholder "
            f"(got {result.get('plain_offence_name')!r}) -- REGRESSION TEST: this previously "
            f"fell back to the literal string 'this offence' due to the bare-section lookup bug"
        )
except Exception as e:
    check(False, f"suggest_offence raised an unexpected exception: {e}")


print("\n" + "=" * 70)
print("RELATIVE DATE TESTS [LIVE API -- real cost incurred]")
print("=" * 70)

try:
    value = extract_field_from_answer(
        "arrest_datetime_full",
        "When exactly did the arrest happen -- do you know the date and roughly what time?",
        "yesterday at around 1030 pm he was arrested",
    )
    check(
        value != "unclear" and value is not None,
        f"'yesterday at around 1030 pm' resolves to a real date, not 'unclear' (got {value!r}) "
        f"-- REGRESSION TEST"
    )
except Exception as e:
    check(False, f"extract_field_from_answer raised an unexpected exception: {e}")

try:
    value = extract_field_from_answer(
        "arrest_datetime_full",
        "When exactly did the arrest happen -- do you know the date and roughly what time?",
        "i dont know",
    )
    check(
        value == "unclear",
        f"genuinely vague answer ('i dont know') still correctly returns 'unclear' "
        f"(got {value!r}) -- confirms the relative-date fix didn't overcorrect into guessing"
    )
except Exception as e:
    check(False, f"extract_field_from_answer raised an unexpected exception: {e}")


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
    sys.exit(0)