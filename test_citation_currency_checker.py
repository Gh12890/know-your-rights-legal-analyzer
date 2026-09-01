
"""
test_citation_currency_checker.py

Regression suite for citation_currency_checker.py (Project 2, Step 3 --
the case-law-treatment evidence gatherer).

NO API COST: every Indian Kanoon call is a locally-defined fake passed
in as search_fn / enrich_fn. This suite exercises the triage logic, the
de-duplication, the source-case exclusion, the post-commencement date
flag, the adverse-language scan, the bundle shape, and both fail-loud
paths -- all without touching the network.

Run with: python test_citation_currency_checker.py
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import date

import citation_currency_checker as ccc
from citation_currency_checker import (
    DoctrineKeyNotFoundError,
    MissingCaseMetadataError,
    _classify_court_tier,
    _find_adverse_markers,
    _looks_like_source_case,
    _parse_ik_date,
    _triage_candidate,
    gather_treatment_evidence,
    write_review_bundle,
)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


# ---------------------------------------------------------------------------
# _parse_ik_date
# ---------------------------------------------------------------------------

check(_parse_ik_date("2025-09-19") == date(2025, 9, 19), "parses ISO YYYY-MM-DD")
check(_parse_ik_date("05-12-2025") == date(2025, 12, 5), "parses day-first DD-MM-YYYY")
check(_parse_ik_date("19 September 2025") == date(2025, 9, 19), "parses '19 September 2025'")
check(_parse_ik_date("not a date") is None, "unparseable string -> None, no raise")
check(_parse_ik_date("") is None, "empty string -> None")
check(_parse_ik_date(None) is None, "None -> None")
check(_parse_ik_date(20250919) is None, "non-string -> None, no raise")


# ---------------------------------------------------------------------------
# _classify_court_tier
# ---------------------------------------------------------------------------

check(_classify_court_tier("Supreme Court of India") == "supreme_court", "SC docsource -> supreme_court")
check(_classify_court_tier("Bombay High Court") == "high_court", "HC docsource -> high_court")
check(_classify_court_tier("Delhi District Court") == "other", "district docsource -> other")
check(_classify_court_tier(None) == "unknown", "missing docsource -> unknown")


# ---------------------------------------------------------------------------
# _looks_like_source_case  (title starts with the name AND year matches)
# ---------------------------------------------------------------------------

RANGAPPA_META = {"case_name": "Rangappa v Sri Mohan", "year": 2010}

check(
    _looks_like_source_case("Rangappa vs Sri Mohan on 7 May, 2010", 2010, RANGAPPA_META),
    "the real source-case title + matching year is recognised as the source case",
)
check(
    not _looks_like_source_case(
        "Sudhir Kumar vs State Of Haryana on 3 March, 2021", 2021, RANGAPPA_META
    ),
    "an unrelated citing case is NOT flagged as the source case",
)
check(
    not _looks_like_source_case(
        "13. In Rangappa vs Sri Mohan (2010) 11 SCC 441, It Was ... on 12 May, 2022",
        2022,
        RANGAPPA_META,
    ),
    "REAL FALSE-POSITIVE CLASS (live run 2026-09-01): a citing judgment whose IK title merely "
    "begins with a paragraph number then names the case is NOT flagged (title doesn't start with the name)",
)
check(
    not _looks_like_source_case(
        "Rangappa vs Sri Mohan Reported In (2010) 11 SCC 441 ... on 3 September, 2019",
        2019,
        RANGAPPA_META,
    ),
    "a 2019 hit whose title DOES start with the case name is still NOT flagged -- its year (2019) "
    "is not the source year (2010)",
)
check(
    not _looks_like_source_case("", None, RANGAPPA_META),
    "empty candidate title -> not the source case, no crash",
)
check(
    not _looks_like_source_case("Rangappa vs Sri Mohan", None, RANGAPPA_META),
    "a title match with no parseable candidate year fails closed -> not the source case",
)


# ---------------------------------------------------------------------------
# _find_adverse_markers
# ---------------------------------------------------------------------------

check(
    _find_adverse_markers("The earlier view is overruled by this Bench.") == ["overrul"],
    "'overruled' matches the 'overrul' marker",
)
check(
    _find_adverse_markers("This decision is per incuriam and distinguished on facts.")
    == sorted(["per incuriam", "distinguish"]),
    "multiple adverse markers found and returned sorted",
)
check(
    _find_adverse_markers("The presumption under Section 139 was applied.") == [],
    "a neutral snippet yields no adverse markers",
)
check(_find_adverse_markers(None, "") == [], "None / empty inputs -> [], no crash")


# ---------------------------------------------------------------------------
# _triage_candidate
# ---------------------------------------------------------------------------

TODAY = date(2026, 9, 1)
SRC_META = {"case_name": "Rangappa v Sri Mohan", "year": 2010}

triaged = _triage_candidate(
    {
        "tid": 12345,
        "title": "ABC Traders vs State on 10 January, 2025",
        "publishdate": "2025-01-10",
        "docsource": "Karnataka High Court",
        "headline": "Following <b>Rangappa</b> v Sri Mohan, the presumption was upheld.",
    },
    SRC_META,
    TODAY,
)
check(triaged["tid"] == 12345, "triage keeps the tid")
check(triaged["url"] == "https://indiankanoon.org/doc/12345/", "triage builds the IK doc URL from the tid")
check(triaged["court_tier"] == "high_court", "triage classifies the court tier")
check(triaged["post_three_code_commencement"] is True, "a 2025-01-10 hit is flagged post-commencement (True)")
check(triaged["is_source_case"] is False, "a citing hit is not flagged as the source case")
check(triaged["adverse_treatment_markers"] == [], "a positive-citing hit has no adverse markers")
check("<b>" not in triaged["snippet"] and "Rangappa" in triaged["snippet"],
      "HTML highlight tags are stripped from the stored snippet")

triaged_old = _triage_candidate(
    {"tid": 1, "title": "Old Case vs State", "publishdate": "2012-06-01", "docsource": "Supreme Court of India"},
    SRC_META,
    TODAY,
)
check(triaged_old["post_three_code_commencement"] is False, "a 2012 hit is flagged NOT post-commencement (False)")

triaged_undated = _triage_candidate(
    {"tid": 2, "title": "Undated Case vs State", "docsource": "Supreme Court of India"},
    SRC_META,
    TODAY,
)
check(
    triaged_undated["post_three_code_commencement"] is None,
    "a hit with no parseable date -> post-commencement flag is None (unknown), never guessed",
)


# ---------------------------------------------------------------------------
# gather_treatment_evidence -- fail-loud paths (no API calls happen)
# ---------------------------------------------------------------------------

def _no_calls_search(query, page_num):  # pragma: no cover - must never run
    raise AssertionError("search_fn was called despite an expected fail-loud")


try:
    gather_treatment_evidence("this_is_not_a_real_doctrine_key", search_fn=_no_calls_search)
    check(False, "unknown doctrine_key raises DoctrineKeyNotFoundError")
except DoctrineKeyNotFoundError:
    check(True, "unknown doctrine_key raises DoctrineKeyNotFoundError before any search call")

# Temporarily drop a CASE_METADATA entry to force the MissingCaseMetadataError path.
import ik_query_builder

_saved = ik_query_builder.CASE_METADATA.pop("rangappa")
try:
    gather_treatment_evidence("rangappa_section_139_presumption_mandatory", search_fn=_no_calls_search)
    check(False, "doctrine_key with no CASE_METADATA raises MissingCaseMetadataError")
except MissingCaseMetadataError as exc:
    check("rangappa" in str(exc), "MissingCaseMetadataError names the exact case_key to add")
finally:
    ik_query_builder.CASE_METADATA["rangappa"] = _saved


# ---------------------------------------------------------------------------
# gather_treatment_evidence -- full run with a fake IK client
# ---------------------------------------------------------------------------

# rangappa_section_139_presumption_mandatory -> case_key "rangappa",
# which has a citation, so build_doctrine_queries yields TWO queries
# (case name, then citation). The fake returns overlapping docs across
# the two so we can prove de-duplication by tid.

_NAME_QUERY_DOCS = [
    {  # the source case itself, ranked #1 -- a good sanity signal, must be excluded from the citing count
        "tid": 100, "title": "Rangappa vs Sri Mohan on 7 May, 2010",
        "publishdate": "2010-05-07", "docsource": "Supreme Court of India",
        "headline": "the question was referred to the larger Bench for an authoritative view...",
    },
    {  # post-commencement positive citing case
        "tid": 200, "title": "Ramesh vs State of Karnataka on 3 February, 2025",
        "publishdate": "2025-02-03", "docsource": "Karnataka High Court",
        "headline": "Applying Rangappa v Sri Mohan, the S.139 presumption stands.",
    },
    {  # pre-commencement citing case
        "tid": 300, "title": "Old Matter vs State on 1 June, 2015",
        "publishdate": "2015-06-01", "docsource": "Supreme Court of India",
        "headline": "Rangappa was followed.",
    },
]

_CITATION_QUERY_DOCS = [
    {"tid": 200, "title": "Ramesh vs State of Karnataka on 3 February, 2025",  # DUPLICATE of tid 200
     "publishdate": "2025-02-03", "docsource": "Karnataka High Court", "headline": "..."},
    {  # adverse-language citing case, post-commencement
        "tid": 400, "title": "Contra View vs State on 9 September, 2024",
        "publishdate": "2024-09-09", "docsource": "Bombay High Court",
        "headline": "This line of reasoning appears per incuriam and is doubted.",
    },
    {  # a hit with no date at all
        "tid": 500, "title": "No Date Matter vs Someone",
        "docsource": "Madras High Court", "headline": "Rangappa cited.",
    },
]


def fake_search(query, page_num):
    if query == "(2010) 11 SCC 441":
        docs = _CITATION_QUERY_DOCS
    else:
        docs = _NAME_QUERY_DOCS
    return {"found": f"1 - {len(docs)} of {len(docs)}", "docs": docs}


bundle = gather_treatment_evidence(
    "rangappa_section_139_presumption_mandatory",
    search_fn=fake_search,
    today=TODAY,
)

check(bundle["doctrine_key"] == "rangappa_section_139_presumption_mandatory", "bundle carries the doctrine_key")
check(bundle["case_key"] == "rangappa", "bundle resolves and carries the case_key")
check(bundle["source_case_name"] == "Rangappa v Sri Mohan", "bundle carries the source case name")
check(len(bundle["queries_run"]) == 2, "both query variants (name + citation) were run")
check(bundle["counts"]["candidates_total"] == 5, "5 distinct candidates after de-duplicating tid 200 across both queries")
check(bundle["counts"]["source_case_hits"] == 1, "the source case (tid 100) is counted separately, not as citing progeny")
check(bundle["counts"]["citing_candidates"] == 4, "4 citing candidates (100 excluded as the source case)")
check(bundle["counts"]["post_commencement"] == 2, "2 citing hits dated on/after 1 July 2024 (tid 200 and tid 400)")
check(bundle["counts"]["with_adverse_markers"] == 1, "1 citing hit (tid 400) carries adverse-treatment language")

_by_tid = {c["tid"]: c for c in bundle["candidates"]}
check(_by_tid[100]["is_source_case"] is True, "tid 100 flagged is_source_case")
check(
    _by_tid[100]["adverse_treatment_markers"] == ["larger bench"],
    "the source case's own 'referred to the larger Bench' phrasing is still surfaced as a marker for a human",
)
check(_by_tid[400]["adverse_treatment_markers"] == sorted(["per incuriam", "doubted"]),
      "tid 400's adverse markers are detected and sorted")
check(_by_tid[500]["post_three_code_commencement"] is None, "tid 500 (no date) -> post-commencement flag None")
check("decides nothing" in bundle["summary"], "the summary explicitly disclaims deciding anything")
check("not a verdict" in bundle["disclaimer"], "the bundle carries the no-verdict disclaimer")


# ---------------------------------------------------------------------------
# enrich_fn backfill
# ---------------------------------------------------------------------------

def fake_search_thin(query, page_num):
    return {"found": "1 - 1 of 1", "docs": [{"tid": 900, "title": "Thin Hit vs State"}]}


def fake_enrich(tid):
    check(tid == 900, "enrich_fn is called with the thin hit's tid")
    return {"publishdate": "2025-05-05", "docsource": "Allahabad High Court"}


bundle_enriched = gather_treatment_evidence(
    "rangappa_section_139_presumption_mandatory",
    search_fn=fake_search_thin,
    enrich_fn=fake_enrich,
    today=TODAY,
)
_hit = bundle_enriched["candidates"][0]
check(_hit["court"] == "Allahabad High Court", "enrich_fn backfilled the missing court")
check(_hit["post_three_code_commencement"] is True, "enrich_fn backfilled date drives the post-commencement flag")


# ---------------------------------------------------------------------------
# write_review_bundle
# ---------------------------------------------------------------------------

_tmp = tempfile.mkdtemp(prefix="ccc_test_")
try:
    path = write_review_bundle(bundle, out_dir=_tmp)
    check(os.path.isfile(path), "write_review_bundle writes a file")
    check(path.endswith("rangappa_section_139_presumption_mandatory.json"), "bundle file is named by doctrine_key")
    with open(path, encoding="utf-8") as fh:
        reloaded = json.load(fh)
    check(reloaded["counts"] == bundle["counts"], "the written bundle round-trips through JSON unchanged")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Coverage guard: every doctrine_key in JUDGMENT_CITATION_MAP now resolves
# to a CASE_METADATA entry (no MissingCaseMetadataError for any of them).
# ---------------------------------------------------------------------------

from retrieval import JUDGMENT_CITATION_MAP
from ik_query_builder import CASE_METADATA

_unmapped = []
for _dk, _entry in JUDGMENT_CITATION_MAP.items():
    if _entry["case_key"] not in CASE_METADATA:
        _unmapped.append((_dk, _entry["case_key"]))
check(
    not _unmapped,
    f"every JUDGMENT_CITATION_MAP doctrine_key has CASE_METADATA for its case_key (unmapped: {_unmapped})",
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
