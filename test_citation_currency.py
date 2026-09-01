
"""
test_citation_currency.py

Regression suite for citation_currency.py and its wiring into
main.py's _result() helper -- Project 2's first working slice.

Run with: python test_citation_currency.py
No API cost -- pure Python, no LLM/embedding/Indian Kanoon calls.
"""

import sys

from citation_currency import (
    get_citation_currency,
    get_citation_currency_for_case_name,
    CITATION_CURRENCY_MAP,
    NOT_YET_VERIFIED,
)
from retrieval import JUDGMENT_CITATION_MAP, get_judgment_doctrine
from main import _result
from chat_assistant import format_retrieved_text_for_prompt

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


# ---- Unknown doctrine_key: explicit NOT_YET_VERIFIED, never None, never a crash ----

record = get_citation_currency("this_key_does_not_exist")
check(record is not None, "unknown doctrine_key returns a dict, not None")
check(record["status"] == NOT_YET_VERIFIED, "unknown doctrine_key returns NOT_YET_VERIFIED status")
check(record["verified_note"] is not None, "unknown doctrine_key still returns a non-empty verified_note")

# ---- Every entry in CITATION_CURRENCY_MAP has a real doctrine_key ----
# (catches typos that would silently create an orphaned currency record
# nothing ever looks up)

for key in CITATION_CURRENCY_MAP:
    check(
        key in JUDGMENT_CITATION_MAP,
        f"citation_currency key '{key}' has a matching JUDGMENT_CITATION_MAP entry",
    )

# ---- Every status value used is one of the four documented values ----

VALID_STATUSES = {"GOOD_LAW", "SUPERSEDED_BY_STATUTE", "OVERRULED", "DISTINGUISHED"}
for key, entry in CITATION_CURRENCY_MAP.items():
    check(
        entry["status"] in VALID_STATUSES,
        f"'{key}' has a valid status value ({entry['status']})",
    )
    check(
        entry["status"] != NOT_YET_VERIFIED,
        f"'{key}' does not hardcode NOT_YET_VERIFIED (that's the lookup-miss default only)",
    )

# ---- The worked example: tapas_d_neogy has BOTH dimensions verified ----

tapas = get_citation_currency("tapas_d_neogy_bank_account_as_property")
check(tapas["status"] == "SUPERSEDED_BY_STATUTE", "tapas_d_neogy: statute renumbering correctly flagged")
check(
    tapas["successor_provision"] == {"act": "BNSS", "section": "106"},
    "tapas_d_neogy: successor provision recorded as BNSS 106",
)
check(
    "Khilji" in tapas["successor_treatment"],
    "tapas_d_neogy: real post-BNSS citing case recorded in successor_treatment",
)
check(
    "CONFIRMED FALSE" in tapas["successor_treatment"],
    "tapas_d_neogy: the retracted Malabar Gold/Neelkanth lineage claim is documented as retracted",
)

# ---- Second worked example: arnesh_kumar_checklist now has BOTH dimensions verified too ----

arnesh = get_citation_currency("arnesh_kumar_checklist")
check(arnesh["status"] == "SUPERSEDED_BY_STATUTE", "arnesh_kumar_checklist: statute renumbering correctly flagged")
check(
    arnesh["successor_provision"] == {"act": "BNSS", "section": "35(1)(b)(ii), 35(3)-(6)"},
    "arnesh_kumar_checklist: successor provision recorded as BNSS 35",
)
check(
    "Vijayalaxmi" in arnesh["successor_treatment"] and "20163394" in arnesh["successor_treatment"],
    "arnesh_kumar_checklist: real post-BNSS citing case recorded in successor_treatment",
)

# No SUPERSEDED_BY_STATUTE entry should still be carrying the old
# "not yet independently verified" placeholder now that both worked
# examples are complete -- this would catch a future entry added without
# actually doing the case-law-treatment search.
for key in ["arnesh_kumar_checklist", "tapas_d_neogy_bank_account_as_property"]:
    entry = get_citation_currency(key)
    check(
        "NOT YET INDEPENDENTLY VERIFIED" not in entry["successor_treatment"],
        f"'{key}' no longer carries an unconfirmed-treatment placeholder (fully verified)",
    )

# ---- NI Act citations never get SUPERSEDED_BY_STATUTE (NI Act untouched by BNS/BNSS) ----

NI_ACT_KEYS = [
    "rangappa_section_139_presumption_mandatory",
    "bir_singh_blank_cheque_and_informal_loan",
    "damodar_prabhu_compounding_cost_scheme",
    "kaveri_plastics_amount_specifically_demanded",
    "prakash_chimanlal_sheth_jurisdiction",
]
for key in NI_ACT_KEYS:
    entry = get_citation_currency(key)
    check(entry["status"] == "GOOD_LAW", f"NI Act citation '{key}' is GOOD_LAW, not flagged as superseded")

# ---- main.py's _result() actually attaches citation_currency ----

result = _result("test requirement", "Compliant", "test explanation", doctrine_key="tapas_d_neogy_bank_account_as_property")
check("citation_currency" in result, "_result() attaches citation_currency when doctrine_key is given")
check(
    result["citation_currency"]["status"] == "SUPERSEDED_BY_STATUTE",
    "_result()'s attached citation_currency matches the real record",
)

result_no_key = _result("test requirement", "Compliant", "test explanation")
check(
    "citation_currency" not in result_no_key,
    "_result() attaches nothing when doctrine_key is omitted (existing call sites unaffected)",
)

result_unverified = _result("test requirement", "Compliant", "test explanation", doctrine_key="some_future_key_not_yet_added")
check(
    result_unverified["citation_currency"]["status"] == NOT_YET_VERIFIED,
    "_result() surfaces NOT_YET_VERIFIED for a doctrine_key with no currency record, rather than omitting the field",
)

# ---- retrieval.py's chunk-file registry gap (Project 2 discovery) is closed ----
# 8 case_keys used by JUDGMENT_CITATION_MAP (freeze + cheque-bounce
# domains) were never registered in _JUDGMENT_CHUNK_FILES, so
# get_judgment_doctrine() silently returned nothing for them -- no
# exception, just an empty source_paragraphs field in every compliance
# check that cited them. Confirmed fixed for the 3 freeze-domain keys
# with real paragraph_numbers already recorded (the 5 cheque-bounce
# keys still have paragraph_numbers=[] pending re-chunking/verification,
# a separate tracked gap -- not what this checks).

PREVIOUSLY_BROKEN_DOCTRINE_KEYS = [
    "tapas_d_neogy_bank_account_as_property",
    "malabar_gold_section_106_107_textual_holding",
    "neelkanth_blanket_freeze_disproportionate",
]
for key in PREVIOUSLY_BROKEN_DOCTRINE_KEYS:
    paragraphs = get_judgment_doctrine(key)
    check(
        bool(paragraphs),
        f"'{key}' now resolves to real source paragraph text (previously silently empty)",
    )

# ---- The 5 remaining cheque-bounce doctrine keys now resolve to real text ----
# (Project 2 backlog close-out, 2026-09-01: paragraph numbers already
# identified during Project 1's full-text reads but never transcribed
# into JUDGMENT_CITATION_MAP, plus one wrong number corrected.)

CHEQUE_BOUNCE_EXPECTED_TEXT = {
    "rangappa_section_139_presumption_mandatory": "legally enforceable debt or liability",
    "bir_singh_blank_cheque_and_informal_loan": "blank cheque leaf",
    "damodar_prabhu_compounding_cost_scheme": "10% of the cheque amount",
    "prakash_chimanlal_sheth_jurisdiction": "territorial jurisdiction",
}
for key, expected_fragment in CHEQUE_BOUNCE_EXPECTED_TEXT.items():
    paragraphs = get_judgment_doctrine(key)
    check(bool(paragraphs), f"'{key}' now resolves to real source paragraph text")
    check(
        any(expected_fragment in p["text"] for p in (paragraphs or [])),
        f"'{key}' paragraph text actually contains the claimed holding ({expected_fragment!r})",
    )

# kaveri_plastics is a genuine duplicate-paragraph-number collision (same
# pattern as Neelkanth) -- confirm BOTH occurrences come back, and that
# the real holding (the long one) is among them, not just the short
# demand-notice-recitation fragment.
kaveri_paragraphs = get_judgment_doctrine("kaveri_plastics_amount_specifically_demanded")
check(len(kaveri_paragraphs or []) == 2, "kaveri_plastics_amount_specifically_demanded: both duplicate paragraph-5 occurrences returned")
check(
    any("We have to ascertain the meaning" in p["text"] for p in (kaveri_paragraphs or [])),
    "kaveri_plastics_amount_specifically_demanded: the real Suman Sethi quote is present in the returned text",
)

# ---- Chat-path wiring: get_citation_currency_for_case_name ----

arnesh_by_name = get_citation_currency_for_case_name("Arnesh Kumar v State of Bihar")
check(len(arnesh_by_name) == 1, "case-name lookup finds exactly one doctrine_key for Arnesh Kumar")
check(
    arnesh_by_name[0]["status"] == "SUPERSEDED_BY_STATUTE",
    "case-name lookup for Arnesh Kumar returns the same status as the direct doctrine_key lookup",
)

malabar_by_name = get_citation_currency_for_case_name("Malabar Gold and Diamond Limited v Union of India")
check(malabar_by_name[0]["status"] == "GOOD_LAW", "case-name lookup for Malabar Gold correctly returns GOOD_LAW")

unmapped_case = get_citation_currency_for_case_name("Pankaj Bansal v Union of India")
check(
    unmapped_case[0]["status"] == NOT_YET_VERIFIED and unmapped_case[0]["doctrine_key"] is None,
    "a corpus judgment with no JUDGMENT_CITATION_MAP entry (Pankaj Bansal) returns NOT_YET_VERIFIED, not an error",
)

nonexistent_case = get_citation_currency_for_case_name("Some Fictional Case v Nobody")
check(
    nonexistent_case[0]["status"] == NOT_YET_VERIFIED,
    "a case_name that isn't in the corpus at all still returns an explicit NOT_YET_VERIFIED record, never a crash",
)

# ---- Chat-path wiring: format_retrieved_text_for_prompt injects the currency note ----

prompt_text = format_retrieved_text_for_prompt([
    {"case_name": "Arnesh Kumar v State of Bihar", "paragraph_number": "fallback_12", "text": "sample text"},
])
check(
    "Citation currency note" in prompt_text and "SUPERSEDED_BY_STATUTE" in prompt_text,
    "format_retrieved_text_for_prompt injects a currency note for a non-GOOD_LAW judgment match",
)

prompt_text_good_law = format_retrieved_text_for_prompt([
    {"case_name": "Malabar Gold and Diamond Limited v Union of India", "paragraph_number": "fallback_22", "text": "sample text"},
])
check(
    "Citation currency note" not in prompt_text_good_law,
    "format_retrieved_text_for_prompt adds no currency note for a GOOD_LAW judgment match",
)

prompt_text_statute_only = format_retrieved_text_for_prompt([
    {"section_number": "106", "act": "BNSS", "text": "sample statute text"},
])
check(
    "Citation currency note" not in prompt_text_statute_only,
    "format_retrieved_text_for_prompt is a no-op for a statute match with no case_name",
)

# ---- The dead, fabricated kaveri_plastics entry was actually removed ----

check(
    "kaveri_plastics_security_cheque_maturity" not in JUDGMENT_CITATION_MAP,
    "the retracted fabricated 'security cheque, contingent liability' doctrine key was deleted from JUDGMENT_CITATION_MAP",
)


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
    sys.exit(0)
