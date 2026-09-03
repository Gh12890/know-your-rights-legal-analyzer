"""
test_related_judgments.py

Phase 0 coverage for related_judgments.py: situation decomposition
(model mocked -- no API cost) and the pure-Python anchor building
(real statute_concordance lookups).

Run: python test_related_judgments.py
"""

import logging
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
check('"They never told us why"' in q, "verbatim fact phrase is quoted in the query")
check(" 50 " in f" {q} " and " 47 " in f" {q} ", "old (CrPC 50) and new (BNSS 47) section numbers both appear")
check("Article 22 1" not in q and "Article 22" in q, "'Article 22(1)' -> 'Article 22' (subsection paren dropped)")
check("doctypes:supremecourt,highcourts" in q, "court filter appended")
check("fromdate:01-01-2015" in q, "fromdate appended when given")

qs = build_issue_queries(_anchor)
check(len(qs) == 2, "phrase-anchored + phrase-less fallback when the anchor has both a phrase and sections")
check('"They never told us why"' not in qs[1], "the fallback query drops the verbatim phrase")

no_sec = {"issue": "x", "hook_phrase": "police came to our house", "new_sections": [],
          "old_sections": [], "doctrine_hooks": []}
check(len(build_issue_queries(no_sec)) == 1, "no fallback when there are no section numbers to broaden to")

empty = {"issue": "arrest procedure", "hook_phrase": "", "new_sections": [],
         "old_sections": [], "doctrine_hooks": []}
check(build_issue_query(empty).startswith("arrest procedure"),
      "a signal-less anchor falls back to the issue text, never an empty query")


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
print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
