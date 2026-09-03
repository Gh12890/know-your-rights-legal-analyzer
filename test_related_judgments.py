"""
test_related_judgments.py

Coverage for related_judgments.py (Lane B) through Phase 1b:
  - situation decomposition (Anthropic client mocked)
  - anchor building + the answer-section anchor (real statute_concordance)
  - ik_query_builder.build_issue_query / semantic_retrieval.rerank
  - search_candidates / rank_candidates / get_related_judgments with every
    external call (IK search, local search, reranker, decomposition)
    injected -- nothing here touches the network.

Run: python test_related_judgments.py
"""

import datetime
import logging
import re
import sys
from unittest.mock import MagicMock, patch

import related_judgments as rj

# The failure-path cases below deliberately feed bad JSON / raise from the
# mocked client; related_judgments logs those at warning/exception level.
# Silence them so the test output stays readable -- the assertions, not
# the logs, are what verify the honest give-up behaviour.
logging.getLogger("related_judgments").setLevel(logging.CRITICAL)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


def _fake_response(text):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


# ---------------------------------------------------------------------------
# _hook_phrase_in_text -- the guard that throws away issues the user did
# not actually raise.
# ---------------------------------------------------------------------------
MSG = ("Last month police came to our house around 11pm and took my younger "
       "brother. His name was not in the FIR. They never told us why or showed "
       "any papers. It's been over two months now and no chargesheet.")

check(rj._hook_phrase_in_text("name was not in the FIR", MSG),
      "verbatim substring hook is accepted")
check(rj._hook_phrase_in_text("His name was not in the FIR", MSG),
      "case-insensitive substring hook is accepted")
check(rj._hook_phrase_in_text("no chargesheet", MSG),
      "short verbatim hook is accepted")
check(rj._hook_phrase_in_text("brother house police", MSG),
      "content-word bag match (reordered words) is accepted")
check(not rj._hook_phrase_in_text("he was beaten in custody", MSG),
      "a hook the user never said (custodial assault) is rejected")
check(not rj._hook_phrase_in_text("", MSG),
      "empty hook is rejected")
check(not rj._hook_phrase_in_text("the police station court case", MSG),
      "a hook that only overlaps on stopwords/filler is rejected")


# ---------------------------------------------------------------------------
# _parse_section_hook
# ---------------------------------------------------------------------------
check(rj._parse_section_hook("BNSS 35") == ("BNSS", "35"), "'BNSS 35' parses")
check(rj._parse_section_hook("BNS 318(4)") == ("BNS", "318"), "'BNS 318(4)' -> base number only")
check(rj._parse_section_hook("Section 187 BNSS") == ("BNSS", "187"), "'Section 187 BNSS' parses")
check(rj._parse_section_hook("Article 22(1)") is None, "'Article 22(1)' is not a BNS/BNSS section")
check(rj._parse_section_hook("D.K. Basu") is None, "'D.K. Basu' is not a section")
check(rj._parse_section_hook("") is None, "empty hook parses to None")


# ---------------------------------------------------------------------------
# extract_answer_sections
# ---------------------------------------------------------------------------
check(
    rj.extract_answer_sections("Section 303(2) covers theft; Section 35 of the BNSS applies; also Section 187.")
    == {"303", "35", "187"},
    "base section numbers pulled from an answer, subsection suffix stripped",
)
check(rj.extract_answer_sections("no section numbers here") == set(),
      "an answer with no sections -> empty set")


# ---------------------------------------------------------------------------
# build_anchors -- real concordance lookups, no LLM, no network.
# ---------------------------------------------------------------------------
profile = {
    "primary_grievance": "brother held without grounds",
    "procedural_stage": "arrested, pre-chargesheet, ~2 months",
    "issues": [
        {"issue": "grounds of arrest not communicated",
         "hook_phrase": "never told us why", "section_hooks": ["BNSS 47", "Article 22(1)"]},
        {"issue": "arrest of a person not named in the FIR",
         "hook_phrase": "name was not in the FIR", "section_hooks": ["BNSS 35"]},
        {"issue": "chargesheet not filed in time",
         "hook_phrase": "no chargesheet", "section_hooks": ["BNSS 187"]},
        {"issue": "some issue with no section",
         "hook_phrase": "took my younger brother", "section_hooks": []},
    ],
}
anchors = rj.build_anchors(profile)

check(len(anchors) == 4, "one anchor per issue")
a0, a1, a2, a3 = anchors

check(a0["new_sections"] == ["BNSS 47"], "BNSS 47 kept as the new-section label")
check("CrPC 50" in a0["old_sections"], "BNSS 47 -> CrPC 50 via concordance")
check(a0["doctrine_hooks"] == ["Article 22(1)"], "'Article 22(1)' kept as a doctrine hook, not a section")

check("CrPC 41" in a1["old_sections"], "BNSS 35 -> CrPC 41 via concordance")
check(a1["hook_phrase"] == "name was not in the FIR", "hook phrase carried onto the anchor")

check("CrPC 167" in a2["old_sections"], "BNSS 187 -> CrPC 167 (default bail) via concordance")

check(a3["new_sections"] == [] and a3["old_sections"] == [] and a3["doctrine_hooks"] == [],
      "an issue with no section hooks yields an anchor with empty lists (still searchable by phrase)")

check(rj.build_anchors(None) == [], "build_anchors(None) -> []")
check(rj.build_anchors({}) == [], "build_anchors({}) -> []")


# ---------------------------------------------------------------------------
# decompose_situation -- model mocked.
# ---------------------------------------------------------------------------
GOOD_JSON = """{
  "primary_grievance": "brother arrested and held without grounds",
  "procedural_stage": "arrested, pre-chargesheet, ~2 months",
  "issues": [
    {"issue": "grounds of arrest not communicated", "hook_phrase": "never told us why", "section_hooks": ["BNSS 47", "Article 22(1)"]},
    {"issue": "arrest of a person not named in the FIR", "hook_phrase": "name was not in the FIR", "section_hooks": ["BNSS 35"]},
    {"issue": "chargesheet not filed within the time limit", "hook_phrase": "no chargesheet", "section_hooks": ["BNSS 187"]}
  ]
}"""

with patch("related_judgments.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response(GOOD_JSON)]
    result = rj.decompose_situation(MSG)
    check(result is not None, "a clean multi-issue message decomposes")
    check(len(result["issues"]) == 3, "all three verified issues are kept")
    check(result["issues"][0]["issue"] == "grounds of arrest not communicated",
          "issue order is preserved (most important first)")
    check(result["primary_grievance"].startswith("brother"), "primary_grievance carried through")

# An issue whose hook_phrase is NOT in the user's message must be dropped.
HALLUCINATED_HOOK_JSON = """{
  "primary_grievance": "x", "procedural_stage": "y",
  "issues": [
    {"issue": "real issue", "hook_phrase": "name was not in the FIR", "section_hooks": []},
    {"issue": "invented issue", "hook_phrase": "he was tortured with electric shocks", "section_hooks": []}
  ]
}"""
with patch("related_judgments.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response(HALLUCINATED_HOOK_JSON)]
    result = rj.decompose_situation(MSG)
    check(result is not None and len(result["issues"]) == 1,
          "an issue with a hook the user never said is dropped; the real one survives")
    check(result["issues"][0]["issue"] == "real issue", "the surviving issue is the grounded one")

# More than MAX_ISSUES -> capped.
many = ", ".join(f'{{"issue": "i{n}", "hook_phrase": "police came to our house", "section_hooks": []}}'
                 for n in range(8))
with patch("related_judgments.client") as mock_client:
    mock_client.messages.create.side_effect = [
        _fake_response('{"primary_grievance":"x","procedural_stage":"y","issues":[' + many + ']}')
    ]
    result = rj.decompose_situation(MSG)
    check(result is not None and len(result["issues"]) == rj.MAX_ISSUES,
          f"issue list is capped at MAX_ISSUES ({rj.MAX_ISSUES})")

# Fenced JSON is tolerated.
with patch("related_judgments.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response("```json\n" + GOOD_JSON + "\n```")]
    result = rj.decompose_situation(MSG)
    check(result is not None and len(result["issues"]) == 3, "a ```json fenced response still parses")

# Unparseable response -> None (honest give-up).
with patch("related_judgments.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response("I couldn't work that out, sorry.")]
    check(rj.decompose_situation(MSG) is None, "an unparseable model response -> None")

# No issue survives -> None.
with patch("related_judgments.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response(
        '{"primary_grievance":"x","procedural_stage":"y","issues":['
        '{"issue":"a","hook_phrase":"words the user never wrote at all","section_hooks":[]}]}'
    )]
    check(rj.decompose_situation(MSG) is None, "if every issue's hook fails verification -> None")

# Model call itself raises -> None.
with patch("related_judgments.client") as mock_client:
    mock_client.messages.create.side_effect = RuntimeError("network down")
    check(rj.decompose_situation(MSG) is None, "a model-call exception -> None, not a crash")

# client is None -> None, no call attempted.
with patch("related_judgments.client", None):
    check(rj.decompose_situation(MSG) is None, "client unavailable -> None")

# Empty / whitespace message -> None.
with patch("related_judgments.client") as mock_client:
    mock_client.messages.create.side_effect = [_fake_response(GOOD_JSON)]
    check(rj.decompose_situation("   ") is None, "empty message -> None (no model call)")
    check(mock_client.messages.create.call_count == 0, "no model call made for an empty message")


# ---------------------------------------------------------------------------
# ik_query_builder.build_issue_query / build_issue_queries (no network)
# ---------------------------------------------------------------------------
from ik_query_builder import build_issue_query, build_issue_queries

_anchor = {
    "issue": "grounds of arrest not communicated",
    "hook_phrase": "They never told us why",
    "new_sections": ["BNSS 47"],
    "old_sections": ["CrPC 50"],
    "doctrine_hooks": ["Article 22(1)"],
}
q = build_issue_query(_anchor, fromdate="01-01-2015")
check(q.startswith('"never told us why"'),
      "the phrase query is the trimmed verbatim phrase ALONE (leading stopword 'They' dropped)")
check("50" not in q and "47" not in q and "Article" not in q,
      "the phrase query carries NO section numbers or doctrine names -- kept clean")
check("doctypes:highcourts" in q, "court filter appended (High Courts only by default)")
check("fromdate:01-01-2015" in q, "fromdate appended when given")

kw = build_issue_query(_anchor, include_phrase=False)
check('"never told us why"' not in kw, "the keyword query drops the verbatim phrase")
check(any(w in kw for w in ("grounds", "arrest", "communicated")),
      "the keyword query carries content words from the issue description")
_nums = re.findall(r"(?<!\d)\d{1,3}[A-Z]?(?!\d)", kw.split("doctypes:")[0])
check(len(_nums) <= 1, "the keyword query carries at most ONE section number")

qs = build_issue_queries(_anchor)
check(len(qs) == 2 and '"never told us why"' in qs[0] and '"never told us why"' not in qs[1],
      "a phrase query then a keyword query, in that order")

empty = {"issue": "arrest procedure generally", "hook_phrase": "", "new_sections": [],
         "old_sections": [], "doctrine_hooks": []}
eq = build_issue_query(empty)
check("arrest" in eq and "procedure" in eq and eq.strip() != "doctypes:highcourts",
      "a phrase-less anchor still produces a non-empty keyword query from the issue text")


# ---------------------------------------------------------------------------
# semantic_retrieval.rerank -- Voyage client mocked (no API cost)
# ---------------------------------------------------------------------------
import semantic_retrieval as sr


class _RerankResult:
    def __init__(self, index, score):
        self.index = index
        self.relevance_score = score


class _RerankResponse:
    def __init__(self, pairs):
        self.results = [_RerankResult(i, s) for i, s in pairs]


check(sr.rerank("q", []) == [], "rerank with no documents -> [] (not None)")
check(sr.rerank("", ["a", "b"]) == [], "rerank with empty query -> []")

with patch("semantic_retrieval._voyage_available", True), \
     patch("semantic_retrieval.voyageai") as mock_voyage:
    mock_voyage.Client.return_value.rerank.return_value = _RerankResponse([(2, 0.9), (0, 0.4)])
    out = sr.rerank("which case is about X", ["doc-a", "doc-b", "doc-c"], top_k=2)
    check([o["index"] for o in out] == [2, 0], "results returned best-first by score")
    check(out[0]["document"] == "doc-c", "index maps back to the right document string")
    check(out[0]["score"] == 0.9, "relevance_score carried through")

with patch("semantic_retrieval._voyage_available", True), \
     patch("semantic_retrieval.voyageai") as mock_voyage:
    mock_voyage.Client.return_value.rerank.side_effect = RuntimeError("voyage down")
    check(sr.rerank("q", ["a", "b"]) is None, "a reranker exception -> None (honest 'could not rank')")

with patch("semantic_retrieval._voyage_available", False):
    check(sr.rerank("q", ["a", "b"]) is None, "reranker unavailable -> None")


# ---------------------------------------------------------------------------
# Phase 1b: search_candidates / rank_candidates / get_related_judgments
# -- every external call injected, nothing hits the network.
# ---------------------------------------------------------------------------

def _ik_doc(tid, title, court="Delhi High Court", pubdate="2025-06-01", headline="a snippet"):
    return {"tid": tid, "title": title, "docsource": court,
            "publishdate": pubdate, "headline": headline}


def _corpus_rec(name, para, text, score=0.5):
    return {"type": "judgment", "chunk_id": f"judgment:{name}:{para}", "case_name": name,
            "paragraph_number": para, "text": text, "score": score,
            "source_url": f"https://indiankanoon.org/doc/{para}/"}


ANCHORS = [
    {"issue": "arrest of a person not named in the FIR", "hook_phrase": "name was not in the FIR",
     "new_sections": ["BNSS 35"], "old_sections": ["CrPC 41"], "doctrine_hooks": []},
    {"issue": "chargesheet not filed within the time limit", "hook_phrase": "no chargesheet",
     "new_sections": ["BNSS 187"], "old_sections": ["CrPC 167"], "doctrine_hooks": []},
]

# IK returns the SAME tid 500 for both issues (cross-issue), plus tid 501 for
# issue 0 only, plus tid 502 which is really a corpus case (Arnesh Kumar).
_IK_RESULTS = {
    0: {"docs": [_ik_doc(500, "Ramesh v State"), _ik_doc(501, "Suresh v State"),
                 _ik_doc(502, "Arnesh Kumar vs State Of Bihar on 2 July, 2014", court="Supreme Court of India")]},
    1: {"docs": [_ik_doc(500, "Ramesh v State")]},
}


def _fake_ik_search(query):
    # crude: route by which section number appears in the query
    if " 41 " in f" {query} " or "41" in query.split() or "name was not in the FIR" in query:
        return _IK_RESULTS[0]
    return _IK_RESULTS[1]


def _fake_local_search(query):
    if "not named" in query or "FIR" in query:
        return [_corpus_rec("D.K. Basu v State of West Bengal", "35",
                            "The arrest safeguards apply regardless of whether the arrestee is named in the FIR.")]
    return []


def _fake_rerank(q, docs, top_k=None):
    # score by simple keyword overlap so the test is deterministic
    ql = set(re.findall(r"[a-z]+", q.lower()))
    out = []
    for i, d in enumerate(docs):
        dl = set(re.findall(r"[a-z]+", d.lower()))
        out.append({"index": i, "score": len(ql & dl) / (len(ql) + 1), "document": d})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


CORPUS_NAMES = ["Arnesh Kumar v State of Bihar", "D.K. Basu v State of West Bengal"]

pool = rj.search_candidates(ANCHORS, ik_search_fn=_fake_ik_search, local_search_fn=_fake_local_search)
by_tid = {c["raw"]["tid"]: c for c in pool if c["source"] == "indiankanoon"}
check(set(by_tid) == {500, 501, 502}, "IK hits pooled and deduped by tid across issues")
check(by_tid[500]["matched_issues"] == [0, 1], "a tid returned for two issues has both indices unioned")
check(by_tid[501]["matched_issues"] == [0], "a single-issue tid keeps just its index")
check(any(c["source"] == "corpus" for c in pool), "local corpus hit is pooled alongside IK hits")

ranked = rj.rank_candidates(pool, "police arrested him though his name was not in the FIR and no chargesheet",
                            rerank_fn=_fake_rerank, corpus_case_names=CORPUS_NAMES,
                            today=datetime.date(2026, 9, 3))
ranked_tids = [r["triage"]["tid"] for r in ranked if r["source"] == "indiankanoon"]
check(502 not in ranked_tids, "the IK hit that is really a corpus case (Arnesh Kumar) is dropped")
check(all(r["rerank_used"] for r in ranked), "rerank_used flag is True when a reranker was supplied")
check(ranked == sorted(ranked, key=lambda r: r["score"], reverse=True), "ranked list is sorted best-first")
c500 = next(r for r in ranked if r["source"] == "indiankanoon" and r["triage"]["tid"] == 500)
c501 = next(r for r in ranked if r["source"] == "indiankanoon" and r["triage"]["tid"] == 501)
check(c500["score"] > c501["score"], "the two-issue judgment outranks the one-issue judgment (cross-issue boost)")

degraded = rj.rank_candidates(pool, "q", rerank_fn=lambda *a, **k: None,
                              corpus_case_names=CORPUS_NAMES,
                              today=datetime.date(2026, 9, 3))
check(degraded and all(not r["rerank_used"] for r in degraded),
      "reranker returning None -> ranking still produces a list, marked not rerank_used")


# ---- get_related_judgments: full flow, everything injected ----
def _fake_decompose(msg):
    return {"primary_grievance": "held without grounds", "procedural_stage": "pre-chargesheet",
            "issues": [
                {"issue": "arrest of a person not named in the FIR", "hook_phrase": "name was not in the FIR", "section_hooks": ["BNSS 35"]},
                {"issue": "chargesheet not filed within the time limit", "hook_phrase": "no chargesheet", "section_hooks": ["BNSS 187"]},
            ]}

res = rj.get_related_judgments(
    "arrested though his name was not in the FIR, and still no chargesheet after 2 months",
    grounded_answer_text="Section 35 of the BNSS governs arrest; Section 187 governs default bail.",
    write_bundle=False,
    decompose_fn=_fake_decompose, ik_search_fn=_fake_ik_search,
    local_search_fn=_fake_local_search, rerank_fn=_fake_rerank,
    today=datetime.date(2026, 9, 3),
)
check(res["status"] == "ok", "get_related_judgments returns status 'ok' when candidates survive")
check(len(res["candidates"]) >= 1, "at least one candidate returned")
check(len(res["anchors"]) == 2, "one anchor per issue, no synthetic mega-anchor from the answer")
check(502 not in [c["triage"]["tid"] for c in res["candidates"] if c["source"] == "indiankanoon"],
      "corpus-case IK hit stays dropped through the full flow")

# answer-section parsing: act-qualified only, resolved via concordance
check(rj._answer_act_sections("Section 35 of the BNSS governs arrest; Section 187 BNSS covers default bail; Section 99 alone is ambiguous.")
      == [("BNSS", "35"), ("BNSS", "187")],
      "only ACT-qualified section references are pulled from the answer ('Section 99 alone' ignored)")
_old = rj.answer_old_sections("Section 35 of the BNSS governs arrest without warrant.")
check("CrPC 41" in _old and "IPC 97" not in _old,
      "'Section 35 of the BNSS' resolves to CrPC 41 only -- never IPC 97 (BNS 35 private defence)")

with patch.dict("os.environ", {"KYR_DISABLE_LIVE_JUDGMENTS": "1"}):
    r = rj.get_related_judgments("anything", decompose_fn=_fake_decompose)
    check(r["status"] == "disabled" and r["candidates"] == [], "kill switch -> status 'disabled', no work done")

r = rj.get_related_judgments("x", write_bundle=False, decompose_fn=lambda m: None)
check(r["status"] == "no_decomposition", "decomposition failure -> status 'no_decomposition', never a raise")

def _boom_ik(q):
    raise RuntimeError("IK down")

r = rj.get_related_judgments(
    "arrested, name not in FIR", write_bundle=False, pin=False, decompose_fn=_fake_decompose,
    ik_search_fn=_boom_ik, local_search_fn=lambda q: [], rerank_fn=_fake_rerank,
    today=datetime.date(2026, 9, 3),
)
check(r["status"] in ("ok", "no_candidates"), "an IK exception is swallowed -- get_related_judgments still returns a dict")


# ---------------------------------------------------------------------------
# Phase 2: fetch_and_pin -- fetch / clean / rerank all injected.
# ---------------------------------------------------------------------------
check(rj._para_number("14. The Court held that...") == 14, "leading 'N.' paragraph number extracted")
check(rj._para_number("42) In this case") == 42, "leading 'N)' paragraph number extracted")
check(rj._para_number("No number here") is None, "no leading number -> None")

_HTML_500 = "<h2 class='doc_title'>Ramesh v State</h2>" + "".join(
    f"<p data-structure='{s}' id='p_{i}'>{i}. {txt}</p>"
    for i, (s, txt) in enumerate([
        ("Facts", "The petitioner was arrested at his home."),
        ("Analysis", "The petitioner was not named in the FIR and the arrest was challenged."),
        ("Conclusion", "Not being named in the FIR does not by itself bar an arrest, but the Section 41A safeguards still apply."),
    ], start=1)
)


def _fake_fetch(tid):
    return {"doc": _HTML_500} if str(tid) == "500" else {"doc": ""}   # 501 -> empty -> fetch "fails"


def _fake_clean(html):
    # crude parse of the fake HTML -> the ik_text_cleaner.clean_document shape
    import re as _re
    paras = []
    for m in _re.finditer(r"<p data-structure='([^']+)'[^>]*>(.*?)</p>", html):
        paras.append({"tag": "p", "structure": m.group(1), "text": m.group(2),
                      "has_citation": False, "citation_sentiments": []})
    return {"title": "Ramesh v State", "paragraphs": paras, "paragraph_count": len(paras)}


# Build a ranked list by hand: two IK candidates (500 fetchable, 501 not),
# one corpus candidate.
_r500 = {"source": "indiankanoon", "matched_issues": [0, 1], "queries": ["q"],
         "raw": _ik_doc(500, "Ramesh v State"), "score": 0.6, "rerank_score": 0.6, "rerank_used": True,
         "triage": {"tid": 500, "title": "Ramesh v State", "url": "u", "court_tier": "high_court",
                    "adverse_markers": [], "is_corpus_case": False}}
_r501 = {"source": "indiankanoon", "matched_issues": [0], "queries": ["q"],
         "raw": _ik_doc(501, "Suresh v State"), "score": 0.55, "rerank_score": 0.55, "rerank_used": True,
         "triage": {"tid": 501, "title": "Suresh v State", "url": "u", "court_tier": "high_court",
                    "adverse_markers": [], "is_corpus_case": False}}
_rc = {"source": "corpus", "matched_issues": [0], "queries": [], "record": {},
       "score": 0.5, "rerank_score": 0.5, "rerank_used": True,
       "triage": {"tid": None, "title": "D.K. Basu v State of West Bengal", "url": "u",
                  "court_tier": "supreme_court", "adverse_markers": [], "is_corpus_case": True}}

_r501_score_before = _r501["score"]
with patch("related_judgments._corpus_para_pool", lambda name: [
    {"text": "10. The arrestee may meet his lawyer during interrogation.", "structure": None, "para_number": 10},
]):
    pinned = rj.fetch_and_pin([_r500, _r501, _rc], "arrested though not named in the FIR, no chargesheet",
                              fetch_fn=_fake_fetch, clean_fn=_fake_clean, rerank_fn=_fake_rerank)

by_tid = {c["triage"]["tid"]: c for c in pinned}
check(by_tid[500].get("pinned"), "the fetchable IK candidate (500) has pinned paragraphs")
check(by_tid[500]["content_score"] is not None, "fetched candidate has a content_score")
check(any(p["para_number"] in (1, 2, 3) for p in by_tid[500]["pinned"]),
      "a pinned paragraph carries the judgment's own paragraph number")
check(by_tid[501].get("fetch_failed") is True, "the IK candidate whose fetch returned empty HTML is flagged fetch_failed")
check(by_tid[501]["pinned"] == [] and by_tid[501]["score"] < _r501_score_before,
      "a fetch-failed candidate is demoted and has no pinned paragraphs, but is still present")
corpus_c = next(c for c in pinned if c["source"] == "corpus")
check(corpus_c.get("pinned") and corpus_c["pinned"][0]["para_number"] == 10,
      "the corpus candidate is paragraph-pinned from its local chunk pool (no fetch)")

# structure bonus: the 'Conclusion' paragraph should be pinnable above a
# 'Facts' paragraph of similar raw relevance
concl = [p for p in by_tid[500]["pinned"] if p["structure"] == "Conclusion"]
check(concl, "the Conclusion-tagged paragraph is among those pinned (structure bonus applied)")

# get_related_judgments with pin=True, everything injected
with patch("related_judgments._corpus_para_pool", lambda name: []):
    res2 = rj.get_related_judgments(
        "arrested though his name was not in the FIR, and still no chargesheet",
        grounded_answer_text="Section 35 of the BNSS governs arrest. Section 187 of the BNSS governs default bail.",
        write_bundle=False, pin=True,
        decompose_fn=_fake_decompose, ik_search_fn=_fake_ik_search,
        local_search_fn=_fake_local_search, rerank_fn=_fake_rerank,
        fetch_fn=_fake_fetch, clean_fn=_fake_clean, today=datetime.date(2026, 9, 3),
    )
check(res2["status"] == "ok", "pin=True full flow returns ok")
check(any("pinned" in c for c in res2["candidates"]), "candidates carry a 'pinned' field after pin=True")

res3 = rj.get_related_judgments(
    "arrested though his name was not in the FIR", write_bundle=False, pin=False,
    decompose_fn=_fake_decompose, ik_search_fn=_fake_ik_search,
    local_search_fn=_fake_local_search, rerank_fn=_fake_rerank, today=datetime.date(2026, 9, 3),
)
check(all(not c.get("pinned") for c in res3["candidates"]),
      "pin=False -> no paragraph fetching, no pinned paragraphs")


# ---------------------------------------------------------------------------
# Phase 3: the settled-doctrine whitelist gate (via get_related_judgments)
# Phase 4: the bounded gloss + its verification
# ---------------------------------------------------------------------------

# _verify_gloss -- the output gate
_PARA = "12. The right to be produced before a Magistrate within 24 hours under Section 57 is mandatory."
check(rj._verify_gloss("The court considered a delay in producing an arrested person and observed that the 24-hour rule is mandatory.", _PARA)
      is not None, "a clean descriptive one-sentence gloss passes")
check(rj._verify_gloss("Your arrest was illegal because you were not produced in time.", _PARA) is None,
      "a gloss with a verdict about the person ('your arrest was illegal') is rejected")
check(rj._verify_gloss("This is binding precedent that must be followed in your case.", _PARA) is None,
      "a gloss claiming 'binding' / 'must be followed' / 'your case' is rejected")
check(rj._verify_gloss("The court applied Section 167 to extend custody.", _PARA) is None,
      "a gloss citing Section 167, which is NOT in the paragraph, is rejected")
check(rj._verify_gloss("The court applied Section 57 to the facts.", _PARA) is not None,
      "a gloss citing Section 57, which IS in the paragraph, passes")
check(rj._verify_gloss("", _PARA) is None, "an empty gloss is rejected")


# gloss_and_verify -- gloss_fn injected
_cands = [
    {"source": "indiankanoon", "matched_issues": [0], "triage": {"tid": 1, "title": "X v State"},
     "pinned": [{"para_number": 12, "structure": "Section", "text": _PARA, "score": 0.6}]},
    {"source": "indiankanoon", "matched_issues": [0], "triage": {"tid": 2, "title": "Y v State"},
     "pinned": []},  # nothing pinned -> no gloss attempted
]
rj.gloss_and_verify(_cands, "not produced before a magistrate in time",
                    gloss_fn=lambda situation, paras: "The judgment dealt with a delayed production and the court observed the rule is mandatory.")
check(_cands[0]["gloss"] and "mandatory" in _cands[0]["gloss"], "a passing gloss is attached to the pinned candidate")
check(_cands[1]["gloss"] is None, "a candidate with no pinned paragraph gets gloss=None (no call)")

rj.gloss_and_verify(_cands, "situation", gloss_fn=lambda s, p: "This applies to you and your arrest was illegal.")
check(_cands[0]["gloss"] is None, "a gloss that fails verification is dropped (set to None), not shown")

rj.gloss_and_verify(_cands, "situation", gloss_fn=lambda s, p: (_ for _ in ()).throw(RuntimeError("model down")))
check(True, "a gloss_fn exception is swallowed -- gloss_and_verify does not raise")


# get_related_judgments: whitelist gate drives show_user + whether gloss runs
def _decompose_whitelisted(msg):
    return {"primary_grievance": "held without grounds", "procedural_stage": "pre-chargesheet",
            "issues": [
                {"issue": "arrest of a person not named in the FIR", "hook_phrase": "name was not in the FIR", "section_hooks": ["BNSS 35"]},
                {"issue": "chargesheet not filed within the time limit", "hook_phrase": "no chargesheet", "section_hooks": ["BNSS 187"]},
            ]}

def _decompose_not_whitelisted(msg):
    return {"primary_grievance": "account frozen", "procedural_stage": "unknown",
            "issues": [
                {"issue": "police froze the bank account", "hook_phrase": "bank account was frozen", "section_hooks": ["BNSS 107"]},
            ]}

_gloss_calls = []
def _tracking_gloss(situation, paras):
    _gloss_calls.append(1)
    return "The judgment dealt with a similar delay and the court made observations about it."

with patch("related_judgments._corpus_para_pool", lambda name: [
    {"text": "9. Article 22 of the Constitution reads thus: arrested shall be detained.", "structure": None, "para_number": 9},
]):
    wl_res = rj.get_related_judgments(
        "arrested though his name was not in the FIR and still no chargesheet after two months",
        write_bundle=False, pin=True, decompose_fn=_decompose_whitelisted,
        ik_search_fn=_fake_ik_search, local_search_fn=_fake_local_search,
        rerank_fn=_fake_rerank, fetch_fn=_fake_fetch, clean_fn=_fake_clean,
        gloss_fn=_tracking_gloss, today=datetime.date(2026, 9, 3),
    )
check(wl_res["show_user"] is True, "all-whitelisted issues -> show_user True")
check(wl_res["whitelist"]["covered"] is True, "whitelist report says covered")
check(len(_gloss_calls) >= 1, "the gloss runs on the whitelisted path")

_gloss_calls.clear()
nb_res = rj.get_related_judgments(
    "the police froze my bank account without telling me", write_bundle=False, pin=False,
    decompose_fn=_decompose_not_whitelisted, ik_search_fn=_fake_ik_search,
    local_search_fn=lambda q: [], rerank_fn=_fake_rerank, gloss_fn=_tracking_gloss,
    today=datetime.date(2026, 9, 3),
)
check(nb_res["show_user"] is False, "a non-whitelisted issue -> show_user False (panel hidden)")
check(nb_res["whitelist"]["uncovered"] == ["police froze the bank account"],
      "the whitelist report names the issue that hid the panel")
check(len(_gloss_calls) == 0, "the gloss does NOT run when the panel will not be shown (no Sonnet spend)")
check(nb_res["status"] in ("ok", "no_candidates"),
      "the run still completes and a bundle would still be written for hand-curation")


# _dedupe_batch -- a batch order gives one IK doc per connected petition
_batch = [
    {"score": 0.8, "triage": {"title": "Mujeeb Rahman v State of Kerala", "court": "Kerala High Court", "publish_date": "2026-08-21"},
     "pinned": [{"text": "12. The right to be produced before a Magistrate within twenty-four hours is mandatory and absolute."}]},
    {"score": 0.79, "triage": {"title": "Rashad Muhammed v State of Kerala", "court": "Kerala High Court", "publish_date": "2026-08-21"},
     "pinned": [{"text": "12. The right to be produced before a Magistrate within twenty-four hours is mandatory and absolute."}]},
    {"score": 0.7, "triage": {"title": "Someone Else v State of Punjab", "court": "Punjab & Haryana High Court", "publish_date": "2025-03-01"},
     "pinned": [{"text": "4. A wholly different holding about default bail arithmetic."}]},
]
_dd = rj._dedupe_batch(_batch)
check(len(_dd) == 2, "a 3-row list with 2 batch-identical rows collapses to 2")
check(_dd[0]["triage"]["title"] == "Mujeeb Rahman v State of Kerala",
      "the higher-scored row of the batch pair is the one kept")
check(any(c["triage"]["court"].startswith("Punjab") for c in _dd),
      "a genuinely different judgment (different court/date/para) is NOT deduped away")


# ---------------------------------------------------------------------------
print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
