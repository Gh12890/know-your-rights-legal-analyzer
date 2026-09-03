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

print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
