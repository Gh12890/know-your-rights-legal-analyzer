"""
test_judgment_doctrine_map.py

Unit tests for judgment_doctrine_map -- the curated keyword->judgment
anchors that put the genuinely-relevant case law into a chat answer when
voyage-law-2 similarity ranks it below JUDGMENT_SIMILARITY_THRESHOLD (the
confirmed failure: a narrative "arrested for cheating and breach of trust
in a partnership" query surfaced NO judgment at all).

Run with: python test_judgment_doctrine_map.py
No API cost (get_judgment_paragraphs is local file reads).
"""

from judgment_doctrine_map import (
    match_judgment_doctrine,
    get_judgment_doctrine_override,
    JUDGMENT_DOCTRINE_MAP,
)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


# ---- empty / junk input ----
check(match_judgment_doctrine("") == [], "empty string -> [], never crashes")
check(match_judgment_doctrine("   ") == [], "whitespace-only -> []")
check(match_judgment_doctrine("what is the weather in delhi") == [],
      "an unrelated question matches nothing")
check(match_judgment_doctrine("what is section 318 of the bns") == [],
      "a plain 'what is section X' does NOT anchor any judgment")
check(match_judgment_doctrine("how do i get my father's will cancelled") == [],
      "a civil-only question anchors nothing")

# ---- the confirmed-failure query ----
Q = ("I ran a small trading partnership with my cousin, and he took out three "
     "separate loans against our joint stock using signatures he says I gave "
     "him, but I never signed anything after March. He told the police I "
     "attacked him and now I have been arrested for cheating and breach of "
     "trust. I have been in the lock-up two days and nobody has shown me the "
     "loan documents.")
keys = match_judgment_doctrine(Q)
check("grounds_of_arrest_must_be_furnished_in_writing" in keys,
      "partnership/arrest query anchors the grounds-of-arrest doctrine")
check("arrest_must_be_necessary_not_automatic" in keys,
      "...and the arrest-necessity doctrine")
check("civil_dispute_criminalised_as_cheating_or_cbt" in keys,
      "...and the civil-dispute-as-cheating doctrine")

ov = get_judgment_doctrine_override(Q)
names = {m["case_name"] for m in ov}
check(any("Prabir Purkayastha" in n for n in names),
      "override resolves Prabir Purkayastha to real text")
check(any("Vijay Kumar Ghai" in n for n in names),
      "override resolves Vijay Kumar Ghai to real text")
check(all(m.get("text") for m in ov), "every anchored paragraph has real text")
check(all(m.get("source") == "curated_judgment_override" for m in ov),
      "every anchor is tagged curated_judgment_override")
check(all(m.get("type") == "judgment" for m in ov), "every anchor is typed 'judgment'")
check(len(ov) <= 8, "total anchored paragraphs are capped (<=8)")
check(len({m["case_name"] for m in ov}) >= 4,
      "a multi-issue query surfaces at least 4 distinct cases (round-robin)")
per_case = {}
for m in ov:
    per_case[m["case_name"]] = per_case.get(m["case_name"], 0) + 1
check(all(v <= 2 for v in per_case.values()), "no single case contributes more than 2 paragraphs")

# ---- FIR-refusal + default-bail anchors ----
check("fir_registration_is_mandatory_lalita_kumari" in
      match_judgment_doctrine("the police won't register my fir"),
      "FIR-refusal anchors Lalita Kumari")
check("default_bail_is_an_indefeasible_right" in
      match_judgment_doctrine("my brother is 70 days in custody and there is no chargesheet"),
      "chargesheet-delay anchors the default-bail doctrine")

# ---- every entry is resolvable (chunk file registered, paras exist) ----
for key, entry in JUDGMENT_DOCTRINE_MAP.items():
    from retrieval import get_judgment_paragraphs
    paras = get_judgment_paragraphs(entry["case_key"], entry["paragraph_numbers"],
                                    opinion_author=entry.get("opinion_author"))
    check(bool(paras), f"{key}: chunk file registered and >=1 paragraph resolves")
    check(bool(entry.get("context_note")), f"{key}: has a context_note")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print("  -", f)
    raise SystemExit(1)
print("RESULT: ALL TESTS PASSED")
