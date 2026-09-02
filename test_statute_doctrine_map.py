
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
