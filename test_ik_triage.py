"""
test_ik_triage.py

Deterministic, no-network coverage for ik_triage.py -- the shared
Indian-Kanoon-hit triage primitives used by related_judgments.py.

Run: python test_ik_triage.py
"""

import sys
from datetime import date

import ik_triage as t

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


# ---- parse_ik_date ----
check(t.parse_ik_date("2025-03-14") == date(2025, 3, 14), "ISO date parses")
check(t.parse_ik_date("14-03-2025") == date(2025, 3, 14), "day-first date parses")
check(t.parse_ik_date("14 March, 2025") == date(2025, 3, 14), "'14 March, 2025' parses")
check(t.parse_ik_date("sometime last year") is None, "unparseable -> None, no raise")
check(t.parse_ik_date(None) is None, "None -> None")
check(t.parse_ik_date(20250314) is None, "non-string -> None")

# ---- classify_court_tier / court_tier_rank ----
check(t.classify_court_tier("Supreme Court of India") == "supreme_court", "SC tier")
check(t.classify_court_tier("Calcutta High Court") == "high_court", "HC tier")
check(t.classify_court_tier("Delhi District Court") == "other", "district -> other")
check(t.classify_court_tier(None) == "unknown", "missing docsource -> unknown")
check(t.court_tier_rank("supreme_court") > t.court_tier_rank("high_court") > t.court_tier_rank("other"),
      "tier ranks are ordered SC > HC > other")

# ---- strip_html / normalise_title ----
check(t.strip_html("<b>Foo</b> &amp; Bar") == "Foo & Bar", "tags stripped, entity unescaped")
check(t.strip_html(None) == "", "None -> ''")
check(t.normalise_title("Arnesh Kumar vs State Of Bihar on 2 July, 2014") == "arnesh kumar state of bihar",
      "title normalised: lowercased, 'vs' and trailing date dropped")

# ---- find_adverse_markers ----
check(t.find_adverse_markers("the earlier view was overruled by a larger bench") == ["larger bench", "overrul"],
      "multiple adverse markers found, sorted")
check(t.find_adverse_markers("a clean judgment applying the settled rule") == [],
      "no markers in a clean snippet")

# ---- title_matches_any ----
CORPUS = ["Arnesh Kumar v State of Bihar", "D.K. Basu v State of West Bengal", "Vihaan Kumar v State of Haryana"]
check(t.title_matches_any("Arnesh Kumar vs State Of Bihar on 2 July, 2014", CORPUS),
      "an IK title of a corpus case matches")
check(not t.title_matches_any("13. In Arnesh Kumar the Court laid down guidelines", CORPUS),
      "a judgment merely citing a corpus case (missing 'state of bihar') is not flagged as that case")
check(not t.title_matches_any("Rabin Burman vs State of West Bengal on 14 March 2025", CORPUS),
      "an unrelated WB case is not mistaken for D.K. Basu just on 'state of west bengal'")
check(not t.title_matches_any("", CORPUS), "empty title -> no match")

# ---- triage_hit ----
hit = {
    "tid": 999,
    "title": "<b>Rabin Burman</b> vs State Of West Bengal on 14 March, 2025",
    "publishdate": "2025-03-14",
    "docsource": "Calcutta High Court",
    "headline": "petitioner was not named in the FIR ... this was later distinguished",
}
tr = t.triage_hit(hit, corpus_case_names=CORPUS, today=date(2026, 9, 3))
check(tr["tid"] == 999 and tr["url"] == "https://indiankanoon.org/doc/999/", "tid + url")
check(tr["court_tier"] == "high_court", "court tier flagged")
check(tr["publish_date"] == "2025-03-14", "publish date normalised to ISO")
check(tr["post_three_code_commencement"] is True, "post-1-Jul-2024 flagged True")
check(tr["is_corpus_case"] is False, "not one of the 22 corpus cases")
check(tr["adverse_markers"] == ["distinguish"], "'distinguished' in the snippet is flagged")

# date-missing -> None, not a guess
tr2 = t.triage_hit({"tid": 1, "title": "X v Y", "docsource": "Bombay High Court"}, today=date(2026, 9, 3))
check(tr2["post_three_code_commencement"] is None, "no date -> post-commencement flag is None (not False)")
check(tr2["publish_date"] is None, "no date -> publish_date None")

# ---------------------------------------------------------------------------
# find_procedural_disposal_markers / classify_document_finality (2026-09-04)
# CONFIRMED REAL FAILURE this guards against: "Attapuram Bharath Reddy vs
# The State Of Telangana" was ranked, fetched, and USER-CONFIRMED into
# related_judgments_approved.json -- but its only pinned paragraph (real,
# verbatim, reproduced below) is a PetArg (petitioner's argument) praying
# for bail, not any court's judgment or finding.
# ---------------------------------------------------------------------------

# Real, verbatim text of the paragraph that was actually pinned for
# Attapuram Bharath Reddy -- structure "PetArg" is exactly what IK's own
# classifier returned for it.
_ATTAPURAM_PETARG_TEXT = (
    "4.    The learned counsel for the petitioner contends that the\n\n"
    "petitioner is innocent and has no involvement in the alleged\n\n"
    "offences, and that he has been falsely implicated in the case. It\n\n"
    "is submitted that the petitioner was taken into custody by the\n\n"
    "Madhapur SOT team on 26.11.2025 in the morning hours near\n"
    "                                    -3-\n\n\n\n\n"
    "Panthangi Toll Gate and was kept in their custody till night\n\n"
    "without   being   informed    of    the   grounds   of   arrest   and\n\n"
    "subsequently handed over to the Madhapur Police at about\n\n"
    "08:00 PM on 26.11.2025 and was produced before the\n\n"
    "Magistrate only at about 07:00 PM on 27.11.2025, which is\n\n"
    "beyond the statutory period of 24 hours, thereby violating his\n\n"
    "fundamental rights. The learned counsel submits that all the\n\n"
    "allegations made by the prosecution are false and fabricated.\n\n"
    "The investigation in the case is stated to be substantially\n\n"
    "completed and material witnesses have already been examined,\n\n"
    "and charge sheet has not yet been filed. The petitioner\n\n"
    "undertakes to cooperate with the investigation and abide by any\n\n"
    "conditions imposed by this Court. Hence, it is prayed that the\n\n"
    "petitioner be enlarged on bail."
)

check(
    t.find_procedural_disposal_markers(_ATTAPURAM_PETARG_TEXT)
    == ["be enlarged on bail", "prayed that the petitioner be enlarged on bail"],
    "REPRODUCES THE CONFIRMED CASE: the real Attapuram paragraph text is caught by a disposal marker "
    "-- both the short and the longer containing phrase match, since PROCEDURAL_DISPOSAL_MARKERS "
    "deliberately keeps overlapping phrases rather than trying to dedupe substrings of each other",
)
check(
    t.find_procedural_disposal_markers("A clean judgment applying the settled rule.") == [],
    "no markers in a clean snippet",
)
check(
    t.find_procedural_disposal_markers(
        "he is entitled to be released on bail and that he may arrange for sureties"
    ) == [],
    "REGRESSION GUARD: the real Vihaan Kumar false-positive (a STATUTORY QUOTE about the right to be "
    "released on bail, not a court granting it) is NOT matched -- this is exactly why bare 'released on "
    "bail' was dropped from the marker list",
)

# The confirmed real case: ONE paragraph, structure "PetArg", disposal
# language present, no reasoning-structure tag anywhere.
attapuram_paras = [{"text": _ATTAPURAM_PETARG_TEXT, "structure": "PetArg"}]
result = t.classify_document_finality(attapuram_paras)
check(result["has_reasoning_structure"] is False,
      "REPRODUCES THE CONFIRMED CASE: PetArg alone carries no reasoning-structure tag")
check(result["disposal_markers"] == ["be enlarged on bail", "prayed that the petitioner be enlarged on bail"],
      "the real disposal markers are surfaced")
check(result["is_procedural_order"] is True,
      "REPRODUCES THE CONFIRMED CASE: PetArg-only + disposal language -> flagged as a likely procedural order")

# Negative control: an Arnesh-Kumar-SHAPED document -- genuinely discusses
# bail throughout (that IS its subject matter) but has real
# Analysis/Precedent/Conclusion structure elsewhere. Must NOT be flagged --
# this is the exact false-positive the conjunction exists to prevent.
arnesh_shaped_paras = [
    {"text": "The petitioner submits the arrest and remand were made without due application of mind.",
     "structure": "PetArg"},
    {"text": "Section 41 CrPC and the safeguards against automatic arrest are analysed in detail, with "
             "reference to the need for anticipatory bail and regular bail to remain meaningful remedies.",
     "structure": "Analysis"},
    {"text": "We accordingly lay down the following guidelines to be followed in all cases of arrest.",
     "structure": "Conclusion"},
]
result2 = t.classify_document_finality(arnesh_shaped_paras)
check(result2["has_reasoning_structure"] is True,
      "an Arnesh-Kumar-shaped document (Analysis + Conclusion present) has real reasoning structure")
check(result2["is_procedural_order"] is False,
      "REAL-SHAPED FIX: bail language throughout does NOT get an Arnesh-Kumar-shaped judgment flagged, "
      "because it has genuine reasoning structure -- the conjunction protects real precedent")

# No structure data at all (e.g. IK returned none for this document) ->
# unknown, never a guessed False-then-flag.
no_structure_paras = [{"text": "prayed that the petitioner be enlarged on bail.", "structure": None}]
result3 = t.classify_document_finality(no_structure_paras)
check(result3["has_reasoning_structure"] is None,
      "no structure tag anywhere -> has_reasoning_structure is None (unknown), not False")
check(result3["is_procedural_order"] is None,
      "unknown structure data -> is_procedural_order stays None even with disposal language present -- "
      "a phrase alone was shown to be an insufficient signal (see the Vihaan Kumar/NALSA false positives)")

check(t.classify_document_finality([]) == {
    "is_procedural_order": None, "has_reasoning_structure": None, "disposal_markers": [],
}, "empty paragraph list -> all-unknown, never a raise")
check(t.classify_document_finality(None) == {
    "is_procedural_order": None, "has_reasoning_structure": None, "disposal_markers": [],
}, "None -> all-unknown, never a raise")

# Reasoning structure present but NO disposal language at all -> not flagged
# (a genuine judgment with no bail discussion whatsoever).
clean_paras = [{"text": "The appeal raises a question of statutory interpretation.", "structure": "Issue"}]
check(t.classify_document_finality(clean_paras)["is_procedural_order"] is False,
      "reasoning structure present, no disposal language -> not flagged")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
