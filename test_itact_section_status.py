
"""
test_itact_section_status.py

Regression suite for itact_section_status.py -- the "is this IT Act
section still valid law at all" check, Phase 3a of the loc-transit-
remand-plan.

Run with: python test_itact_section_status.py
No API cost -- pure Python, no LLM/embedding/Indian Kanoon calls.
"""

from itact_section_status import (
    get_itact_section_status,
    ITACT_SECTION_STATUS,
    match_cyber_backstory_no_confirmed_section,
    get_cyber_backstory_note,
    NOT_YET_VERIFIED,
    match_66a_mention,
    get_itact_status_override,
)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


# ---- Unknown section: explicit NOT_YET_VERIFIED, never None, never a crash ----

record = get_itact_section_status("999")
check(record is not None, "an unknown section returns a dict, not None")
check(record["status"] == NOT_YET_VERIFIED, "an unknown section returns NOT_YET_VERIFIED status")
check(record["verified_note"] is not None, "an unknown section still returns a non-empty verified_note")
check(record.get("user_facing_note") is None,
      "an unknown section's user_facing_note is None (nothing safe to show yet, not guessed)")
check(record.get("struck_down_by") is None, "an unknown section has no struck_down_by record")

# a wrong act prefix must not accidentally match a real ITACT entry
check(get_itact_section_status("66A", act="BNS")["status"] == NOT_YET_VERIFIED,
      "'BNS 66A' (wrong act) does not match the ITACT 66A entry")


# ---- Section 66A: the real, curated entry ----

r66a = get_itact_section_status("66A")
check(r66a["status"] == "STRUCK_DOWN", "Section 66A resolves to STRUCK_DOWN")
check(r66a["struck_down_by"]["case_name"] == "Shreya Singhal v Union of India",
      "66A's struck_down_by names Shreya Singhal v Union of India")
check(r66a["struck_down_by"]["citation"] == "(2015) 5 SCC 1",
      "66A's struck_down_by carries the real (2015) 5 SCC 1 citation")
check(bool(r66a["user_facing_note"]), "66A has a real, non-empty user_facing_note")
check("cannot lawfully" in r66a["user_facing_note"].lower(),
      "66A's user_facing_note states plainly that it cannot lawfully be used")
check("shreya singhal" in r66a["user_facing_note"].lower(),
      "66A's user_facing_note names the case, not just a bare status word")

# the default act="ITACT" and an explicit act="ITACT" call must agree
check(get_itact_section_status("66A", act="ITACT") == r66a,
      "explicit act='ITACT' matches the default")


# ---- match_66a_mention: positive triggers ----
# Each isolated with no OTHER field/pattern able to satisfy a sibling
# pattern, per the lesson from the settled_doctrine_whitelist typo this
# session (a test passed for the wrong reason and hid a real bug).

for q in [
    "I have been charged under Section 66A of the IT Act for a message I sent",
    "the FIR mentions section 66A",
    "police filed a case citing IT Act 66A over my whatsapp message",
    "can they still register a cyber crime case under 66A",
    "is 66A of the information technology act still valid",
    "SECTION 66-A was invoked against me",
]:
    check(match_66a_mention(q), f"66A mention detected: {q!r}")

# ---- match_66a_mention: must NOT fire on unrelated text ----

for q in [
    "",
    "   ",
    "I was charged under Section 66 of the IT Act for hacking",
    "my case number is 66A/2024",  # a docket/case number, not a section reference
    "he lives at door number 66, apartment A",
    "police arrested me for theft under BNS 303",
]:
    check(not match_66a_mention(q), f"66A mention NOT falsely detected: {q!r}")


# ---- get_itact_status_override: the full chat-facing resolver ----

ov = get_itact_status_override("I have been charged under Section 66A of the IT Act")
check(len(ov) == 1, "66A override resolves to exactly one entry")
check(ov[0]["act"] == "ITACT" and ov[0]["section_number"] == "66A",
      "override is ITACT 66A")
check(ov[0]["source"] == "curated_override",
      "override carries source='curated_override' so callers can tell it apart")
check("shreya singhal" in ov[0]["text"].lower() and "struck down" in ov[0]["text"].lower(),
      "override's text states the struck-down fact and names the case")
check("(2015) 5 scc 1" in ov[0]["text"].lower(),
      "override's text carries the real citation")
check(ov[0]["context_note"] == get_itact_section_status("66A")["user_facing_note"],
      "override's context_note is exactly the curated user_facing_note")

check(get_itact_status_override("what is the weather today") == [],
      "no 66A mention -> empty override list")
check(get_itact_status_override("") == [], "empty question -> empty override list, never crashes")


# ---- Every entry is structurally well-formed ----

REQUIRED_FIELDS = {"status", "struck_down_by", "verified_note", "user_facing_note", "last_checked_date"}
for key, entry in ITACT_SECTION_STATUS.items():
    check(set(entry) >= REQUIRED_FIELDS, f"{key}: has all required fields")
    check(entry["status"] in ("GOOD_LAW", "STRUCK_DOWN"), f"{key}: has a valid status value")
    check(entry["status"] != NOT_YET_VERIFIED,
          f"{key}: does not hardcode NOT_YET_VERIFIED (that's the lookup-miss default only)")
    if entry["status"] == "STRUCK_DOWN":
        check(entry["struck_down_by"] is not None, f"{key}: STRUCK_DOWN entry names what struck it down")
        check(bool(entry["verified_note"]), f"{key}: verified_note is non-empty")
        check(bool(entry["user_facing_note"]), f"{key}: STRUCK_DOWN carries a real user_facing_note")
    check(key.startswith("ITACT "), f"{key}: key is prefixed with the act name ('ITACT ')")


# ---------------------------------------------------------------------------
# match_cyber_backstory_no_confirmed_section / get_cyber_backstory_note
# (2026-09-05, real bug found via live user testing: the LOC/transit-
# remand scenario's chat answer discussed ONLY BNSS 58/187 and never
# mentioned the IT Act at all, despite the situation being driven by a
# deleted Twitter post that "Chennai Cyber Crime" police were
# investigating -- exactly the fact pattern Phase 3 exists for).
# ---------------------------------------------------------------------------

# the exact real-world scenario that surfaced the gap
_LOC_SCENARIO = (
    "I have been detained by Immigration at Delhi IGI Airport due to a "
    "Look Out Circular (LOC) issued by the Chennai Cyber Crime / Tamil "
    "Nadu Police regarding a X Twitter Post in June, which is already "
    "deleted. We need a criminal defense lawyer in Delhi/NCR who can "
    "immediately reach the IGI Airport Police Station or Patiala House "
    "Court to handle the situation and contest the upcoming transit "
    "remand."
)
check(match_cyber_backstory_no_confirmed_section(_LOC_SCENARIO),
      "REGRESSION: the real LOC/transit-remand scenario (cyber crime + Twitter "
      "post + LOC/detained/remand) triggers the general IT Act orientation note")

_POSITIVE_CASES = [
    "the cyber cell called me in over a Facebook post and I'm afraid of being arrested",
    "I got a police notice from the cyber crime branch about a WhatsApp message I sent",
    "an FIR was registered against me by cyber police for a video I uploaded",
]
for q in _POSITIVE_CASES:
    check(match_cyber_backstory_no_confirmed_section(q), f"cyber backstory detected: {q!r}")

_NEGATIVE_CASES = [
    "what is the cyber crime cell",  # no online-content word, no accusation
    "I posted a video of my wedding",  # no cyber agency, no accusation
    "the police arrested me for theft of a goat",  # no cyber agency, no online content
    "my bank account was frozen by the police",  # unrelated
    "",
]
for q in _NEGATIVE_CASES:
    check(not match_cyber_backstory_no_confirmed_section(q), f"cyber backstory NOT falsely detected: {q!r}")

note = get_cyber_backstory_note(_LOC_SCENARIO)
check(len(note) == 1, "get_cyber_backstory_note returns exactly one entry for the LOC scenario")
check(note[0]["act"] == "ITACT" and note[0]["source"] == "curated_override",
      "the note is tagged ITACT / curated_override")
check(note[0]["section_number"] != "66A",
      "the general note does NOT claim to be Section 66A specifically -- no section is confirmed")
check("information technology act" in note[0]["text"].lower(),
      "the note names the IT Act generally")
check("fir or remand copy" in note[0]["text"].lower() or "fir" in note[0]["text"].lower(),
      "the note tells the person how to find out the ACTUAL section (ask for the FIR/remand copy)")
check("66a" in note[0]["text"].lower() and "shreya singhal" in note[0]["text"].lower(),
      "the note conditionally flags the 66A struck-down fact ('if that is the section shown')")
check("if that is the section" in note[0]["text"].lower(),
      "the 66A mention is explicitly conditional, never asserted as the actual charge")

check(get_cyber_backstory_note("what is the weather today") == [],
      "no trigger -> empty note list")
check(get_cyber_backstory_note("") == [], "empty question -> empty note list, never crashes")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("RESULT: ALL TESTS PASSED")
