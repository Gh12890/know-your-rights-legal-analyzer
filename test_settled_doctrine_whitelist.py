"""
test_settled_doctrine_whitelist.py

The gate that decides whether Lane B's live "related judgments" panel is
shown to a user. Pure Python, no network, no model.

Run: python test_settled_doctrine_whitelist.py
"""

import sys

import settled_doctrine_whitelist as wl

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


def I(issue, hook="", sections=None):
    return {"issue": issue, "hook_phrase": hook, "section_hooks": sections or []}


# ---- whitelisted topics match, by section OR by phrase ----
check(wl.match_issue(I("chargesheet not filed within the time limit", sections=["BNSS 187"])) == "default_bail",
      "default bail matches on section BNSS 187")
check(wl.match_issue(I("police have kept my brother for over two months with no chargesheet")) == "default_bail",
      "default bail matches on the '2 months, no chargesheet' phrasing (no section hook)")
check(wl.match_issue(I("arrest of a person not named in the FIR", sections=["BNSS 35"])) == "arnesh_kumar_arrest_notice",
      "not-named-in-FIR arrest matches Arnesh Kumar / BNSS 35")
check(wl.match_issue(I("no notice under Section 41A was given before the arrest")) == "arnesh_kumar_arrest_notice",
      "S.41A notice matches Arnesh Kumar by phrase")
check(wl.match_issue(I("grounds of arrest were never communicated to him")) == "grounds_of_arrest_communicated",
      "grounds-of-arrest matches")
check(wl.match_issue(I("the police refused to give a copy of the FIR")) == "fir_copy_right",
      "FIR-copy refusal matches")
check(wl.match_issue(I("he was not produced before a magistrate within 24 hours")) == "twenty_four_hour_production",
      "24-hour production matches")
check(wl.match_issue(I("was not allowed to meet a lawyer for two days")) == "right_to_lawyer_on_arrest",
      "right-to-a-lawyer matches")
check(wl.match_issue(I("my father was arrested and never taken to a doctor")) == "dk_basu_safeguards",
      "custodial medical-exam matches D.K. Basu safeguards")
check(wl.match_issue(I("physical assault and mistreatment during police custody",
                       "he was slapped and kept awake all night", ["BNSS 35"])) == "dk_basu_safeguards",
      "custodial assault matches D.K. Basu even with a spurious 'BNSS 35' section hook -- "
      "the keyword pattern beats the broad section (which would else give Arnesh Kumar)")
check(wl.match_issue(I("visible injuries not medically documented or examined by a doctor",
                       "", ["BNSS 35"])) == "dk_basu_safeguards",
      "'injuries not medically documented' matches D.K. Basu, not the BNSS-35 section hook")
check(wl.match_issue(I("a Look Out Circular was issued by another state's police")) == "loc_validity_challenge",
      "'Look Out Circular' (no hook_phrase, isolates the phrase pattern itself) "
      "matches the loc_validity_challenge topic")
check(wl.match_issue(I("validity and legality of detention based on look out circular")) == "loc_validity_challenge",
      "a realistic decompose_situation-shaped issue string ('...based on look out "
      "circular') matches -- real phrasing seen from a live decomposition run, not "
      "an invented test string")
check(wl.match_issue(I("how do I get the lookout notice against me cancelled")) == "loc_validity_challenge",
      "'lookout notice ... cancelled' matches by phrase")
check(wl.match_issue(I("wants to challenge the LOC that was issued against him")) == "loc_validity_challenge",
      "'challenge the LOC' matches by phrase (action verb + bare LOC)")
check(wl.match_issue(I("detained by immigration at the airport due to a transit remand")) is None,
      "a transit-remand/immigration-detention issue with no LOC wording is NOT this topic "
      "(that's the separate statute_doctrine_map BNSS 58/187 overrides, not Lane B)")

# ---- ITACT 66A struck-down (2026-09-05, Phase 3c) ----

_66a = "itact_66a_struck_down"
for q in [
    "charged under section 66A of the IT act",
    "is 66A of the information technology act still valid",
    "SECTION 66-A was invoked against me",
]:
    check(wl.match_issue(I(q)) == _66a, f"66A struck-down topic matches: {q!r}")

for q in [
    "my case number is 66A/2024",
    "he lives at door number 66, apartment A",
    "detained by immigration at the airport due to a transit remand",
    "someone hacked my computer",
]:
    check(wl.match_issue(I(q)) != _66a, f"66A struck-down topic does NOT falsely match: {q!r}")

check(wl.match_issue(I("validity of 66A", sections=["ITACT 66A"])) == _66a,
      "also matches on the ITACT 66A section hook, not just phrase")


# ---- NOT whitelisted topics do not match ----
check(wl.match_issue(I("police froze my bank account", sections=["BNSS 107"])) is None,
      "bank-account freeze (BNSS 106/107) is NOT whitelisted")
check(wl.match_issue(I("charged under the organised crime provision", sections=["BNS 111"])) is None,
      "BNS 111 organised crime is NOT whitelisted")
check(wl.match_issue(I("the security cheque I gave was presented and bounced")) is None,
      "cheque / NI Act matters are NOT whitelisted")
check(wl.match_issue(I("can the police seize the cryptocurrency in my wallet")) is None,
      "crypto seizure is NOT whitelisted")
check(wl.match_issue(I("my landlord filed an eviction suit against me")) is None,
      "an unrelated civil matter is NOT whitelisted")


# ---- is_covered: ALL issues must be whitelisted ----
check(wl.is_covered([
    I("arrest of a person not named in the FIR", sections=["BNSS 35"]),
    I("chargesheet not filed within the time limit", sections=["BNSS 187"]),
]) is True, "every issue whitelisted -> covered")

check(wl.is_covered([
    I("grounds of arrest not communicated"),
    I("police also froze his bank account", sections=["BNSS 107"]),
]) is False, "ONE non-whitelisted issue -> not covered")

check(wl.is_covered([]) is False, "no issues -> not covered")
check(wl.is_covered(None) is False, "None -> not covered")


# ---- coverage_report ----
rep = wl.coverage_report([
    I("grounds of arrest not communicated"),
    I("charged with an offence under the terrorist-act provision", sections=["BNS 113"]),
])
check(rep["covered"] is False, "coverage_report: covered False when one issue fails")
check(rep["uncovered"] == ["charged with an offence under the terrorist-act provision"],
      "coverage_report: names the exact issue that kept the panel hidden")
check(dict(rep["by_issue"])["grounds of arrest not communicated"] == "grounds_of_arrest_communicated",
      "coverage_report: by_issue maps the covered issue to its topic")

check(isinstance(wl.list_topics(), dict) and len(wl.list_topics()) >= 6,
      "list_topics returns the whitelist with its 'settled because' notes")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
