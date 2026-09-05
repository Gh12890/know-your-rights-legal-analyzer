
"""
test_statute_doctrine_map.py

Unit tests for statute_doctrine_map -- the curated keyword->statute
overrides that bypass semantic-retrieval uncertainty for known,
high-stakes gaps (BNSS 43(5) night arrest of women; BNSS 482 anticipatory
bail).

These overrides are NOT subject to the retrieval block-cap in
find_relevant_sections (they are merged in downstream, in
chat_assistant.evaluate_question), so they are the right tool for a
provision the corpus genuinely under-retrieves.

Run with: python test_statute_doctrine_map.py
No API cost.
"""

from statute_doctrine_map import (
    match_statute_doctrine,
    get_statute_doctrine_override,
    STATUTE_DOCTRINE_MAP,
)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


# ---- empty / junk input ----

check(match_statute_doctrine("") == [], "empty string -> [], never crashes")
check(match_statute_doctrine("   ") == [], "whitespace-only -> []")
check(match_statute_doctrine("what is the weather in delhi") == [],
      "an unrelated question matches nothing")


# ---- BNSS 482 anticipatory bail ----

_482 = "bnss_482_anticipatory_bail"

for q in [
    "i think the police are going to arrest me soon, what can i do",
    "how do I apply for anticipatory bail",
    "I am afraid of arrest, can I get bail before arrest",
    "police are about to be arrested? no -- I might be arrested next week",
    "how can I avoid arrest in a false FIR",
]:
    check(_482 in match_statute_doctrine(q), f"482 triggers on: {q!r}")

# Must NOT fire for someone already arrested (present/past framing, no
# apprehension words).
for q in [
    "police arrested me yesterday for theft",
    "the police took me to the station without telling me what i had done",
    "my father was arrested yesterday and was never taken to a doctor",
    "what are my rights if the police arrest me",
]:
    check(_482 not in match_statute_doctrine(q),
          f"482 does NOT fire (already/hypothetically arrested, no apprehension): {q!r}")

ov = get_statute_doctrine_override(
    "i think the police are going to arrest me soon, what can i do")
check(len(ov) == 1, "override resolves to exactly one entry")
check(ov[0]["act"] == "BNSS" and ov[0]["section_number"] == "482",
      "override is BNSS 482")
check(ov[0]["source"] == "curated_override",
      "override carries source='curated_override' so callers can tell it apart")
check("482" in ov[0]["text"] and "bail" in ov[0]["text"].lower(),
      "override carries the real statute text from get_statute_section")
check("non-bailable" in ov[0]["context_note"].lower()
      and "discretionary" in ov[0]["context_note"].lower(),
      "context_note states the load-bearing limits (non-bailable only, discretionary)")


# ---- BNSS 43(5) night arrest of women (pre-existing entry, still works) ----

_43 = "bnss_43_5_night_arrest_women"
check(_43 in match_statute_doctrine("can a woman be arrested at night by police"),
      "43(5) still triggers on a night-arrest-of-a-woman question")
check(_482 not in match_statute_doctrine("can a woman be arrested at night by police"),
      "a night-arrest question does not also drag in 482")


# ---- BNSS 58/187 transit remand / Look Out Circular (2026-09-05,
# loc-transit-remand-plan Phase 1) ----

_58 = "bnss_58_transit_production_24_hours"
_187 = "bnss_187_transit_remand_forwarding"

# Real scenario that surfaced this gap: detained by Immigration at an
# airport on an LOC issued by another state's police, contesting a
# transit remand -- confirmed to hit zero deterministic matches before
# this fix.
_loc_scenario = (
    "I have been detained by Immigration at Delhi IGI Airport due to a "
    "Look Out Circular (LOC) issued by the Chennai Cyber Crime / Tamil "
    "Nadu Police. We need a lawyer to contest the upcoming transit remand."
)
for q in [
    _loc_scenario,
    "what is a look out circular and can I contest it",
    "police from another state have a lookout notice against me at the airport",
    "I was detained by immigration, what happens with the transit remand",
]:
    matched = match_statute_doctrine(q)
    check(_58 in matched, f"58 triggers on: {q!r}")
    check(_187 in matched, f"187 triggers on: {q!r}")

# Must NOT fire for ordinary single-state arrest questions -- this is a
# genuinely different fact pattern (cross-jurisdiction detention), not a
# catch-all for every arrest/detention question.
for q in [
    "police arrested me yesterday for theft",
    "my uncle was picked up for theft and beaten in custody",
    "the police took my brother to the local station near our house",
    "my cousin was detained by the local police for questioning",
    "can a woman be arrested at night by police",
    "i think the police are going to arrest me soon, what can i do",
]:
    matched = match_statute_doctrine(q)
    check(_58 not in matched,
          f"58 does NOT fire on an ordinary single-state arrest question: {q!r}")
    check(_187 not in matched,
          f"187 does NOT fire on an ordinary single-state arrest question: {q!r}")

ov = get_statute_doctrine_override(_loc_scenario)
check(len(ov) == 2, "LOC/transit-remand override resolves to exactly two entries")
sections = {(r["act"], r["section_number"]) for r in ov}
check(sections == {("BNSS", "58"), ("BNSS", "187")},
      "the two entries are BNSS 58 and BNSS 187")
for r in ov:
    check(r["source"] == "curated_override",
          f"BNSS {r['section_number']}: carries source='curated_override'")
r58 = next(r for r in ov if r["section_number"] == "58")
r187 = next(r for r in ov if r["section_number"] == "187")
check("whether having jurisdiction or not" in r58["text"],
      "BNSS 58's real statute text carries the jurisdiction-agnostic-production clause")
check("forwarded to a magistrate having such jurisdiction" in r187["text"].lower(),
      "BNSS 187's real statute text carries the transit-remand-forwarding clause")
check("transit" in r58["context_note"].lower() and "transit" in r187["context_note"].lower(),
      "both context_notes name the transit-remand concept explicitly")
check("bnss 47" in r187["context_note"].lower() or "section 47" in r187["context_note"].lower(),
      "BNSS 187's context_note cross-references the grounds-of-arrest safeguard (S.47)")


# ---- every entry is structurally well-formed ----

for key, entry in STATUTE_DOCTRINE_MAP.items():
    check(set(entry) >= {"act", "section_number", "trigger_groups", "context_note"},
          f"{key}: has the required fields")
    check(all(isinstance(g, tuple) and len(g) >= 1 for g in entry["trigger_groups"]),
          f"{key}: every trigger group is a non-empty tuple")
    check(entry["context_note"].strip() != "", f"{key}: context_note is non-empty")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("RESULT: ALL TESTS PASSED")
