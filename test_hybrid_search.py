"""
test_hybrid_search.py

Unit coverage for the "search the library two ways" addition
(semantic_retrieval.lexical_search + hybrid_search), the Lane B
corpus-recall fix for the eval baseline's finding #1 ("a landmark
doesn't match its own doctrine's plain words").

  - lexical_search: real BM25 over the real corpus_embeddings.json index
    (pure Python, no API) -- exact phrases land on the right judgment.
  - hybrid_search: RRF fusion + graceful degradation, with both search
    arms injected (no API, no corpus needed).

Run: python test_hybrid_search.py
"""

import os
import sys

import semantic_retrieval as sr
from semantic_retrieval import lexical_search, hybrid_search

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


def _names(results):
    return [r.get("case_name") or r.get("section_number") or r.get("type")
            for r in (results or [])]


# ---------------------------------------------------------------------------
# lexical_search -- real index over the real corpus
# ---------------------------------------------------------------------------
_HAVE_CORPUS = os.path.exists(sr.EMBEDDINGS_PATH)

if not _HAVE_CORPUS:
    print(f"[SKIP] {sr.EMBEDDINGS_PATH} absent -- lexical_search real-index checks skipped")
else:
    # When the distinctive phrase co-occurs with the doctrine's own
    # vocabulary, lexical nails the landmark that meaning-search missed at
    # baseline. (Pure layman phrasing -- "detained at the airport" -- is
    # still corpus-side "Fix 5" territory: the chunk genuinely lacks
    # "airport"/"immigration" vocabulary, and no keyword search invents it.)
    loc = lexical_search("Sumer Singh Salkan look out circular LOC guidelines", top_k=5)
    check(loc and loc[0].get("case_name")
          == "Viraj Chetan Shah v Union of India & Anr (& Connected Matters)",
          f"lexical_search: 'look out circular' + doctrine terms ranks Viraj Chetan "
          f"Shah first (got {_names(loc)[:3]})")

    a66 = lexical_search("charged under Section 66A of the IT Act", top_k=5)
    check(a66 and (a66[0].get("case_name") == "Shreya Singhal v Union of India"),
          f"lexical_search: 'Section 66A' ranks Shreya Singhal first (got {_names(a66)[:3]})")

    dkb = lexical_search("D.K. Basu custodial safeguards", top_k=5)
    check("D.K. Basu v State of West Bengal" in _names(dkb),
          "lexical_search: a case name in the query retrieves that case")

    check(lexical_search("", top_k=5) == [],
          "lexical_search: empty query -> [] (never None, never a crash)")
    check(lexical_search("zzzqqq xkcd nonexistenttoken", top_k=5) == [],
          "lexical_search: no indexable term -> []")

    every = lexical_search("Section 66A of the IT Act", top_k=5)
    check(all(r["score"] > 0 for r in every) and every == sorted(
              every, key=lambda r: r["score"], reverse=True),
          "lexical_search: results are positive-scored and sorted best-first")
    check(all(r.get("lexical_score") == r.get("score") for r in every),
          "lexical_search: carries lexical_score == score")


# ---------------------------------------------------------------------------
# hybrid_search -- RRF fusion + degradation, both arms injected
# ---------------------------------------------------------------------------
def _rec(cid, **kw):
    return {"chunk_id": cid, "type": "judgment", "text": f"text {cid}", **kw}


def sem_fn(q, top_k=50):
    return [dict(_rec("A"), score=0.9), dict(_rec("B"), score=0.8),
            dict(_rec("C"), score=0.7)]


def lex_fn(q, top_k=50):
    return [dict(_rec("C"), score=12.0), dict(_rec("D"), score=8.0),
            dict(_rec("E"), score=3.0)]


fused = hybrid_search("q", semantic_fn=sem_fn, lexical_fn=lex_fn)
fnames = [r["chunk_id"] for r in fused]

check(set(fnames) == {"A", "B", "C", "D", "E"},
      "hybrid_search: union of both arms, deduped by chunk_id")
check(fnames[0] == "C",
      f"hybrid_search: the doc in BOTH lists (C: sem#3 + lex#1) beats a #1 in "
      f"only one list (got {fnames})")
check(fused[0]["retrieval"] == "hybrid" and fused[0]["semantic_score"] == 0.7
      and fused[0]["lexical_score"] == 12.0,
      "hybrid_search: a fused hit carries both raw scores + retrieval='hybrid'")
_b = next(r for r in fused if r["chunk_id"] == "B")
check(_b["retrieval"] == "semantic" and _b.get("lexical_score") is None,
      "hybrid_search: a semantic-only hit is tagged 'semantic'")
_d = next(r for r in fused if r["chunk_id"] == "D")
check(_d["retrieval"] == "lexical" and _d.get("semantic_score") is None,
      "hybrid_search: a lexical-only hit is tagged 'lexical'")
check(fused == sorted(fused, key=lambda r: r["score"], reverse=True),
      "hybrid_search: sorted by fused RRF score, best first")

# degradation
deg = hybrid_search("q", semantic_fn=lambda q, top_k=50: None, lexical_fn=lex_fn)
check([r["chunk_id"] for r in deg] == ["C", "D", "E"],
      "hybrid_search: Voyage down (semantic->None) -> lexical results alone, not nothing")
check(all(r["retrieval"] == "lexical" for r in deg),
      "hybrid_search: all-lexical degradation tags every hit 'lexical'")

check(hybrid_search("q", semantic_fn=lambda q, top_k=50: None,
                    lexical_fn=lambda q, top_k=50: []) is None,
      "hybrid_search: both arms empty AND semantic was None -> None (honest 'unavailable')")
check(hybrid_search("q", semantic_fn=lambda q, top_k=50: [],
                    lexical_fn=lambda q, top_k=50: []) == [],
      "hybrid_search: both arms genuinely empty (semantic not None) -> []")


# ---------------------------------------------------------------------------
# Lane B wiring: corpus_candidates now defaults to hybrid_search
# ---------------------------------------------------------------------------
import related_judgments as rj

_seen = {}


def _spy_hybrid(q, top_k=50):
    _seen["called"] = True
    return [dict(_rec("Z", case_name="Spy v State"), score=0.01, retrieval="hybrid")]


pool = rj.corpus_candidates(
    [{"issue": "custodial torture", "hook_phrase": "beaten in custody"}],
    local_search_fn=_spy_hybrid,
)
check(_seen.get("called") and pool and pool[0]["record"]["case_name"] == "Spy v State",
      "corpus_candidates threads its local_search_fn through (hybrid_search by default)")


# ---------------------------------------------------------------------------
print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
