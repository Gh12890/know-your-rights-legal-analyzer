"""
test_doctrine_anchors.py

Fix 1 (doctrine_anchors.py) + Fix 2 (the decomposer's fixed doctrine-tag
checklist). No Anthropic / Indian Kanoon calls -- the reranker, fetch,
clean and decompose are all injected; the real LOCAL corpus embeddings
are used (that is what the anchor case names are validated against).

Run: python test_doctrine_anchors.py
"""

import datetime
import logging
import re
import sys

import doctrine_anchors as da
import related_judgments as rj
from settled_doctrine_whitelist import (
    _WHITELIST, DOCTRINE_TAG_CHOICES, coverage_report, match_issue,
)

logging.getLogger("related_judgments").setLevel(logging.CRITICAL)

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


# ---------------------------------------------------------------------------
# the curated map
# ---------------------------------------------------------------------------
check(set(da.DOCTRINE_ANCHOR_CASES) == set(_WHITELIST),
      "DOCTRINE_ANCHOR_CASES has an entry for every whitelist topic")
check(set(DOCTRINE_TAG_CHOICES) == set(_WHITELIST),
      "DOCTRINE_TAG_CHOICES has an entry for every whitelist topic")

from semantic_retrieval import _load_corpus_embeddings
_corpus_names = {r["case_name"] for r in _load_corpus_embeddings()["records"]
                 if r.get("type") == "judgment"}
_bad = [(t, c) for t, cs in da.DOCTRINE_ANCHOR_CASES.items() for c in cs
        if c not in _corpus_names]
check(not _bad, f"every anchor case name resolves in the corpus (bad: {_bad})")
check(da.DOCTRINE_ANCHOR_CASES["default_bail"] == [],
      "default_bail is explicitly an empty anchor list (known corpus gap)")


# ---------------------------------------------------------------------------
# anchor_candidates
# ---------------------------------------------------------------------------
cov_full = coverage_report([
    {"issue": "custodial assault", "hook_phrase": "beaten in the lockup",
     "doctrine_tags": ["dk_basu_safeguards"]},
])
ac = da.anchor_candidates(cov_full)
check([a["record"]["case_name"] for a in ac] == ["D.K. Basu v State of West Bengal"],
      "anchor_candidates: dk_basu issue -> the D.K. Basu anchor")
check(ac[0]["doctrine_anchor"] == "dk_basu_safeguards" and ac[0]["source"] == "corpus",
      "anchor candidate is tagged with the topic and shaped as a corpus candidate")
check(ac[0]["matched_issues"] == [0], "anchor candidate carries the issue index it came from")

cov_partial = coverage_report([
    {"issue": "loc", "hook_phrase": "look out circular", "doctrine_tags": ["loc_validity_challenge"]},
    {"issue": "no lady constable present", "hook_phrase": "no lady constable"},
])
ap = da.anchor_candidates(cov_partial)
check([a["record"]["case_name"] for a in ap]
      == ["Viraj Chetan Shah v Union of India & Anr (& Connected Matters)"],
      "anchor_candidates fires PER covered issue even when the whole question is not covered")

check(da.anchor_candidates(coverage_report([{"issue": "x", "hook_phrase": "y"}])) == [],
      "no whitelisted issue -> no anchors")
check(da.anchor_candidates(coverage_report([
        {"issue": "default bail", "hook_phrase": "no chargesheet after ninety days",
         "doctrine_tags": ["default_bail"]}])) == [],
      "a covered issue whose topic has no anchor -> no anchors (not a crash)")

# two issues, one topic each, sharing a case (Prabir Purkayastha anchors both
# grounds_of_arrest_communicated and twenty_four_hour_production)
cov_share = coverage_report([
    {"issue": "grounds not given", "hook_phrase": "grounds", "doctrine_tags": ["grounds_of_arrest_communicated"]},
    {"issue": "not produced in 24h", "hook_phrase": "produced", "doctrine_tags": ["twenty_four_hour_production"]},
])
names_share = [a["record"]["case_name"] for a in da.anchor_candidates(cov_share)]
prabir = "Prabir Purkayastha v State (NCT of Delhi)"
check(names_share.count(prabir) == 1, "a case anchoring two topics appears once")
check(sorted(next(a for a in da.anchor_candidates(cov_share)
                  if a["record"]["case_name"] == prabir)["matched_issues"]) == [0, 1],
      "and its matched_issues union both issue indices")


# ---------------------------------------------------------------------------
# merge_into_corpus_pool
# ---------------------------------------------------------------------------
_pool = [{"source": "corpus", "matched_issues": [0], "queries": [],
          "record": {"case_name": "D.K. Basu v State of West Bengal", "text": "x"}}]
merged = da.merge_into_corpus_pool(_pool, da.anchor_candidates(cov_full))
check(len(merged) == 1 and merged[0].get("doctrine_anchor") == "dk_basu_safeguards",
      "merge_into_corpus_pool tags an already-present case rather than duplicating it")

merged2 = da.merge_into_corpus_pool([], da.anchor_candidates(cov_full))
check(len(merged2) == 1 and merged2[0]["record"]["case_name"] == "D.K. Basu v State of West Bengal",
      "merge_into_corpus_pool appends an anchor the pool does not have")
check(da.merge_into_corpus_pool(_pool, []) is not _pool
      and da.merge_into_corpus_pool(_pool, []) == _pool,
      "merge_into_corpus_pool with no anchors returns an equal but fresh list")


# ---------------------------------------------------------------------------
# Fix 2: match_issue prefers the ticked box; decompose validates tags
# ---------------------------------------------------------------------------
# prose that the twenty_four_hour_production patterns do NOT catch, but the
# tag does -- the exact baseline flap this fix targets
_flappy = {"issue": "failure to produce the arrested person within the mandatory time limit",
           "hook_phrase": "within the mandatory time limit",
           "section_hooks": [], "doctrine_tags": ["twenty_four_hour_production"]}
check(match_issue(_flappy) == "twenty_four_hour_production",
      "Fix 2: a ticked doctrine tag maps the issue even when no keyword pattern would")
check(match_issue({**_flappy, "doctrine_tags": []}) is None,
      "...and without the tag that same prose is (correctly) not matched -- the flap this fixes")
check(match_issue({**_flappy, "doctrine_tags": ["not_a_real_topic"]}) is None,
      "an unknown tag is ignored, not treated as a match")

# decompose_situation tag validation (client mocked)
from unittest.mock import MagicMock, patch
_resp = MagicMock()
_resp.content = [MagicMock(text=(
    '{"primary_grievance":"g","procedural_stage":"s","issues":['
    '{"issue":"not produced in time","hook_phrase":"never produced before a magistrate",'
    '"section_hooks":["BNSS 58"],"doctrine_tags":["twenty_four_hour_production","bogus","fir_copy_right"]}]}'
))]
with patch.object(rj, "client") as mc:
    mc.messages.create.return_value = _resp
    prof = rj.decompose_situation("he was never produced before a magistrate at all")
check(prof and prof["issues"][0]["doctrine_tags"] == ["twenty_four_hour_production", "fir_copy_right"],
      "decompose_situation keeps only real whitelist keys from doctrine_tags, in order")
# and temperature is pinned to 0 for the extraction call
check(mc.messages.create.call_args.kwargs.get("temperature") == 0,
      "decompose_situation calls the model at temperature 0")


# ---------------------------------------------------------------------------
# end to end: get_related_judgments injects + displays the anchor when the
# search finds nothing on point
# ---------------------------------------------------------------------------
def _decompose_dk(_msg):
    return {"primary_grievance": "beaten in custody", "procedural_stage": "in custody",
            "issues": [{"issue": "custodial assault and no medical exam",
                        "hook_phrase": "beaten in custody and no doctor",
                        "section_hooks": [], "doctrine_tags": ["dk_basu_safeguards"]}]}


def _ik_none(queries):
    return {q: {"docs": []} for q in queries}


def _rerank_lex(q, docs, top_k=None):
    ql = set(re.findall(r"[a-z]+", q.lower()))
    out = [{"index": i, "score": len(ql & set(re.findall(r"[a-z]+", d.lower()))) / (len(ql) + 1),
            "document": d} for i, d in enumerate(docs)]
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top_k] if top_k else out


with patch.object(rj, "approved_candidates", lambda profile, **k: []):
    res = rj.get_related_judgments(
        "he was beaten in custody and no doctor ever saw him",
        write_bundle=False, decompose_fn=_decompose_dk,
        ik_search_many_fn=_ik_none, local_search_fn=lambda q: [],
        rerank_fn=_rerank_lex, fetch_many_fn=lambda tids: {}, clean_fn=lambda h: {"paragraphs": []},
        gloss_fn=lambda s, p: "This one may not be closely on point.",
        today=datetime.date(2026, 9, 5),
    )

names = [c["triage"]["title"] for c in res["candidates"]]
check("D.K. Basu v State of West Bengal" in names,
      "end to end: the D.K. Basu anchor is injected into candidates though search found nothing")
anchor = next((c for c in res["candidates"]
               if c["triage"]["title"] == "D.K. Basu v State of West Bengal"), None)
check(anchor is not None and anchor.get("doctrine_anchor") == "dk_basu_safeguards",
      "...and it carries the doctrine_anchor tag")
check(res["show_user"] is True, "the question is fully whitelisted -> show_user True")
disp = [c["triage"]["title"] for c in res["for_display"]]
check(disp and disp[0] == "D.K. Basu v State of West Bengal",
      "...and it LEADS the trusted panel despite the off-point gloss "
      f"(for_display: {disp})")


# ---------------------------------------------------------------------------
print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
