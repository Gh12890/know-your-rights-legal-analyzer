
"""
eval_related_judgments.py

Quality harness for Lane B -- the "Show related court judgments" panel
(related_judgments.get_related_judgments).  This is Phase 6 of the
live-judgment-retrieval plan.

WHY THIS EXISTS:
test_related_judgments.py checks the PLUMBING -- dedup, the whitelist
gate, the finality exclusion, the empty-panel fallback -- with every
external call mocked.  Nothing measured whether the pipeline actually
SURFACES THE RIGHT JUDGMENT for a real situation: does a custodial-torture
question return D.K. Basu, does a Section 66A question return Shreya
Singhal, does a not-whitelisted property-dispute FIR correctly stay out of
the trusted panel while still showing everything under the "unverified,
you judge it" panel.  Every Lane B change so far has been judged by
eyeballing one or two review bundles.

This runs a fixed set of representative questions through the REAL
pipeline and reports, per question:
  - status, degraded (rerank down), show_user
  - the decomposed issues + the verbatim fact hooks the extractor kept
  - which settled-doctrine topic each issue mapped to (the whitelist gate)
  - how many candidates ranked, split corpus / Indian Kanoon
  - how many reached each panel (for_display / unverified_for_display)
  - for every displayed candidate: gloss present? gloss off-point?
    gloss clean of verdict/binding language? pinned paragraphs present
    and carrying the judgment's own paragraph number?
  - EXPECT_CASE / EXPECT_DISPLAYED / MUST_NOT_DISPLAYED substring checks
  - two invariants checked on every case regardless of expectations:
      * no procedural (bail/interlocutory) disposal ever reaches for_display
      * when status is 'ok', the two panels are never BOTH empty
  - the full ranked list + glosses, for human review

It is NOT a pass/fail gate.  The substring checks are directional
signals; the real judgement is a human reading report.md.  Later this can
grow an LLM-judge layer -- start with human review.  (Same philosophy as
eval_chat_answers.py.)

COST (live mode): real Indian Kanoon + Voyage + Anthropic calls.  Roughly,
per question: 1 Haiku decomposition, 2-6 IK searches, up to ~6 IK
full-document fetches (~Rs 0.20 each), one Voyage rerank, and up to ~6
Sonnet gloss calls.  A full 14-case run is a few tens of rupees of IK
credit plus ~50 Sonnet gloss calls.  Use --offline (free, mocked),
--limit, --only, --no-fetch, --no-gloss while iterating.

Run:
  python eval_related_judgments.py --offline          # free, mocked, CI-safe
  python eval_related_judgments.py                     # all live cases -> eval_related_out/
  python eval_related_judgments.py --only dk-basu-medical
  python eval_related_judgments.py --limit 3 --no-gloss
  python eval_related_judgments.py --label before      # tag the output dir
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
from datetime import datetime as _dt, timezone
from unittest.mock import patch

import related_judgments as rj

# The gloss verdict/binding-language blocklist -- reused so the harness
# checks END TO END that _verify_gloss's guarantee actually holds on a
# displayed candidate, not just in its own unit test.
from related_judgments import _GLOSS_FORBIDDEN, _OFF_POINT_RE


# ===========================================================================
# LIVE cases -- run against the real pipeline.
#
# Each case:
#   id                 -- stable slug
#   question           -- verbatim user input
#   expect_status      -- str or tuple; default ("ok",)
#   expect_show_user   -- True / False / None (None = don't check; use for
#                         situations that legitimately span a whitelisted
#                         and a non-whitelisted issue)
#   expect_topics      -- settled-doctrine topic names that SHOULD appear
#                         among the issue->topic mappings (subset check)
#   min_issues         -- the extractor should find at least this many
#   hook_substrings    -- each: some kept issue's hook_phrase contains it
#                         (verbatim-extraction sanity, case-insensitive)
#   expect_case        -- list of groups; each group is a tuple of title
#                         substrings, at least one of which must match some
#                         RANKED candidate's title (case-insensitive)
#   expect_displayed   -- title substrings that must appear in a panel
#                         (for_display OR unverified_for_display)
#   must_not_displayed -- title substrings that must NOT appear in
#                         for_display (the fully-trusted panel)
#   expect_procedural_flagged -- title substrings for which a candidate
#                         must exist AND be flagged procedural_disposal
#   notes              -- the ideal shape, for the human reading report.md
# ===========================================================================
LIVE_CASES = [
    {
        "id": "dk-basu-medical",
        "question": ("my uncle was picked up by the police last week over a theft "
                     "complaint, he was never taken for a medical check-up and he "
                     "says he was slapped and kept awake all night in the lockup"),
        "expect_show_user": True,
        "expect_topics": ["dk_basu_safeguards"],
        "min_issues": 1,
        "hook_substrings": ["medical", "slapped"],
        "expect_case": [("d.k. basu", "d. k. basu")],
        "expect_displayed": ["basu"],
        "notes": "Custodial-torture + no-medical-exam. Both issues map to D.K. Basu. "
                 "D.K. Basu (corpus) should rank #1 and show in the trusted panel. "
                 "KNOWN BASELINE GAP (2026-09-05): INTERMITTENT -- across baseline runs "
                 "D.K. Basu sometimes ranks ~#5 with a content_score below the trusted-"
                 "panel floor (losing to HC cases that merely RECITE its 48-hour rule, and "
                 "then -- because for_display is non-empty -- shown NOWHERE), and sometimes "
                 "clears it. The instability itself is the finding: for the single most "
                 "important citation on a canonical question, trusted-panel visibility is "
                 "a coin-flip between runs. Not a harness defect.",
    },
    {
        "id": "arnesh-no-notice",
        "question": ("the police arrested me directly over a cheating case that carries "
                     "about seven years, they never gave me any notice to appear first"),
        "expect_show_user": True,
        "expect_topics": ["arnesh_kumar_arrest_notice"],
        "min_issues": 1,
        "hook_substrings": ["notice"],
        "expect_case": [("arnesh kumar", "satender kumar antil")],
        "expect_displayed": ["satender kumar antil"],
        "notes": "The <=7-year direct-arrest-without-notice pattern -> Arnesh Kumar notice "
                 "topic. NOTE (2026-09-05 baseline): Arnesh Kumar v State of Bihar IS in "
                 "the corpus but did not surface as a candidate at all -- a retrieval gap. "
                 "The doctrine is currently carried by Satender Kumar Antil (its gloss on "
                 "this run was exactly on point), so the check accepts either. The "
                 "second decomposed issue ('cheating ~7 years') mapped to the default_bail "
                 "topic -- a classifier over-trigger worth watching, harmless here since "
                 "the panel gates on ALL issues being whitelisted and both are.",
    },
    {
        "id": "grounds-of-arrest-not-given",
        "question": ("the police took my brother to the station and neither he nor we "
                     "were ever told, in writing, the grounds on which he was arrested"),
        "expect_show_user": True,
        "expect_topics": ["grounds_of_arrest_communicated"],
        "min_issues": 1,
        "hook_substrings": ["grounds", "writing"],
        "expect_case": [("vihaan kumar", "prabir purkayastha", "pankaj bansal")],
        "expect_displayed": ["vihaan kumar", "prabir"],
        "notes": "Written grounds of arrest not furnished -> Article 22(1) / Vihaan Kumar "
                 "/ Prabir Purkayastha line. Whitelisted; on the baseline run both "
                 "displayed with on-point glosses. Pankaj Bansal (also in the corpus) did "
                 "not surface -- acceptable, Vihaan + Prabir cover the doctrine.",
    },
    {
        "id": "fir-copy-refused",
        "question": ("an FIR has been registered against me but the police station keeps "
                     "refusing to hand me a copy of it"),
        "expect_show_user": True,
        "expect_topics": ["fir_copy_right"],
        "min_issues": 1,
        "hook_substrings": ["copy"],
        "expect_case": [("youth bar association",)],
        "expect_displayed": ["youth bar association"],
        "notes": "FIR-copy right -> Youth Bar Association v Union of India. Whitelisted.",
    },
    {
        "id": "default-bail-75-days",
        "question": ("the police have kept my brother in custody for seventy-five days and "
                     "still have not filed any chargesheet"),
        "expect_show_user": True,
        "expect_topics": ["default_bail"],
        "min_issues": 1,
        "hook_substrings": ["chargesheet", "seventy-five"],
        # No expect_case: BASELINE FINDING (2026-09-05) -- the corpus has NO
        # dedicated default-bail judgment, even though default_bail is a
        # whitelisted topic. Every candidate on this run came from live IK and
        # none was on point (the top hit was a grounds-of-arrest case). Also
        # observed: the same IK case ("Kessireddy Rajasekhar Reddy") appeared
        # THREE times in the ranked list -- a live-pipeline dedup miss.
        "notes": "Default bail on chargesheet delay -> S.187 BNSS / S.167(2) CrPC line. "
                 "BASELINE GAP: no corpus judgment for this whitelisted topic; live IK "
                 "did not fill it. Candidate for a corpus-seeding batch "
                 "(Bikramjit Singh Bansal / Rakesh Kumar Paul / M. Ravindran). Also a "
                 "dedup miss (one IK case x3) worth chasing in _merge_ranked / the final "
                 "IK list.",
    },
    {
        "id": "not-produced-in-24h",
        "question": ("my father was arrested three days ago and has still not been "
                     "produced before any magistrate"),
        "expect_show_user": True,
        "expect_topics": ["twenty_four_hour_production"],
        "min_issues": 1,
        "hook_substrings": ["produced", "magistrate"],
        "expect_case": [("prabir purkayastha", "rakhi mitra", "gautam navlakha",
                         "d.k. basu", "d. k. basu")],
        "notes": "24-hour production -> Article 22(2) / S.58 BNSS. BASELINE BUG (2026-09-05, "
                 "INTERMITTENT): on some runs the decomposed issue is phrased as 'failure "
                 "to produce ... within mandatory time limit' and does NOT match the "
                 "twenty_four_hour_production whitelist entry -> show_user=False and the "
                 "whole trusted panel is suppressed for a settled-law question; on other "
                 "runs it phrases it with '24 hours' and matches fine. The whitelist "
                 "patterns for this topic should also catch 'produce/produced before (a) "
                 "magistrate within [a] mandatory/statutory time limit'. Retrieval is fine "
                 "-- Prabir Purkayastha and Rakhi Mitra surface with on-point glosses.",
    },
    {
        "id": "itact-66a-whatsapp",
        "question": ("the police have registered a case against me under section 66A of the "
                     "IT Act over a WhatsApp message I forwarded in a group"),
        "expect_show_user": True,
        "expect_topics": ["itact_66a_struck_down"],
        "min_issues": 1,
        "hook_substrings": ["66a"],
        "expect_case": [("shreya singhal",)],
        "expect_displayed": ["shreya singhal"],
        "notes": "Section 66A -> struck down in Shreya Singhal, reinforced by PUCL (2019). "
                 "Whitelisted (itact_66a_struck_down). KNOWN BASELINE GAP (2026-09-05, "
                 "INTERMITTENT): on some runs Shreya Singhal (corpus) scores ~0.44 -- just "
                 "below the trusted-panel content floor -- so the single most important "
                 "citation for a 66A question is not shown and the trusted panel instead "
                 "shows a WhatsApp-admin HC case; on other runs it clears the floor. Same "
                 "borderline-scoring instability as dk-basu-medical.",
    },
    {
        "id": "loc-igi-airport",
        "question": ("i have been detained by immigration at delhi igi airport because of a "
                     "look out circular and i do not know of any FIR against me"),
        "expect_show_user": None,  # LOC framework is whitelisted; the detention/no-FIR
                                   # issue may not be -- so the gate can legitimately
                                   # land either way. Don't hard-assert it.
        "expect_topics": ["loc_validity_challenge"],
        "min_issues": 1,
        "hook_substrings": ["look out circular"],
        "expect_case": [("viraj chetan shah", "sumer singh salkan", "vikram sharma")],
        "expect_displayed": ["viraj chetan shah", "sumer singh salkan"],
        "notes": "LOC challenge -> Viraj Chetan Shah / the Sumer Singh Salkan guidelines "
                 "(quoted verbatim inside Viraj Chetan Shah). BASELINE FINDING (2026-09-05, "
                 "expect_case / expect_displayed left FAILING -- CONSISTENT across every "
                 "baseline run): Viraj Chetan Shah is IN the corpus but NEVER surfaced as a "
                 "candidate for an LOC question -- the corpus hits are always Prabir / "
                 "Vihaan / Arnesh Kumar with 'not closely on point' glosses. The LOC "
                 "chunks are framework-heavy ('OM/LOC-framework validity', 'Clause 8(j)') "
                 "and carry no airport/immigration/detention vocabulary, so a plain-"
                 "language LOC question does not retrieve them. This is the single "
                 "clearest, most reproducible finding of the baseline: a whitelisted "
                 "corpus landmark that is unreachable by its own doctrine's plain query. "
                 "Also seen: the same IK case listed twice (dedup miss); 20s IK read-"
                 "timeouts on some runs (degrades gracefully).",
    },
    {
        "id": "property-dispute-fir",
        "question": ("an FIR was registered against me over a property dispute about "
                     "ancestral land, and the police are now threatening to arrest me"),
        "expect_show_user": False,
        "min_issues": 1,
        "notes": "NOT a settled-doctrine topic (property-dispute-as-crime, threatened "
                 "arrest). for_display must stay empty; unverified_for_display must hold "
                 "the full ranked list; the review bundle is still written.",
    },
    {
        "id": "partnership-cheating",
        "question": ("i ran a small trading partnership with my cousin, he moved money out "
                     "of the firm account, and now he has filed a cheating case against me"),
        "expect_show_user": False,
        "min_issues": 1,
        # No expect_case: NOT whitelisted, so everything routes to the
        # unverified panel a human reads anyway. BASELINE NOTE (2026-09-05):
        # Vijay Kumar Ghai and Satishchandra (both in the corpus, both the
        # right "civil dispute is not cheating" authorities) did NOT surface;
        # only an off-point corpus hit (Md. Ibrahim) did. Same corpus-
        # retrieval-miss pattern as arnesh-no-notice / loc-igi-airport.
        "notes": "Civil/commercial dispute dressed as cheating -- NOT whitelisted, panel "
                 "hidden, all candidates to the unverified panel. Corpus retrieval missed "
                 "the on-point authorities (Vijay Kumar Ghai / Satishchandra) -- a "
                 "recurring baseline finding, tracked separately.",
    },
    {
        "id": "boundary-dispute-arrest",
        "question": ("there's an ongoing boundary dispute between our family and the "
                     "neighbours, and after a scuffle the police arrested my son the same "
                     "evening"),
        "expect_show_user": False,
        "min_issues": 1,
        "notes": "Mixed civil backstory + a same-day scuffle arrest -- not a clean "
                 "whitelisted doctrine. Expect hidden panel, unverified list populated.",
    },
    {
        "id": "bank-account-frozen",
        "question": ("money stopped working in my savings account and the bank told me the "
                     "police had frozen it, nobody sent me anything"),
        "expect_status": ("ok", "no_candidates", "no_decomposition"),
        "expect_show_user": False,
        "notes": "Freeze is a different domain with almost no judgment corpus. Acceptable "
                 "outcomes: a hidden panel with an unverified list, or an honest "
                 "no_candidates / no_decomposition. Must never crash or show a trusted panel.",
    },
    {
        "id": "night-arrest-woman-no-lady-constable",
        "question": ("the police came to our house around 9 pm and took away my sister, "
                     "there was no lady constable with the team and they handed us no paper"),
        "expect_show_user": False,
        "min_issues": 2,
        "hook_substrings": ["lady constable", "no paper", "paper"],
        "notes": "Two issues: no lady constable (NOT whitelisted) + no arrest notice "
                 "(arnesh_kumar_arrest_notice, whitelisted). Because ONE issue is "
                 "uncovered, show_user must be False -- the whole panel gates on ALL "
                 "issues being settled. unverified list carries both issues' hits.",
    },
    {
        "id": "opposed-bail-three-months",
        "question": ("my brother has been in jail for three months, the police keep "
                     "opposing his bail and the trial has not even started"),
        "expect_status": ("ok", "no_candidates"),
        "expect_show_user": None,
        "notes": "FINALITY PROBE. BASELINE FINDING (2026-09-05): this question pulled real "
                 "HC bail orders to ranks #1 and #3 (Dilipsingh Gurjar, Golu @ Yashvantsingh "
                 "-- both 'bail granted with conditions'), and classify_document_finality "
                 "flagged NEITHER. That is the classifier being deliberately conservative "
                 "-- a modern HC bail order with a reasoned Analysis section does not meet "
                 "the (no-reasoning-structure AND disposal-phrase) conjunction. Harmless "
                 "here (not whitelisted -> unverified panel only), but if a similarly-"
                 "phrased question were whitelisted, a reasoned bail order could reach "
                 "for_display. Worth revisiting the finality heuristic for reasoned bail "
                 "grants, not just bare disposals.",
    },
    {
        "id": "gibberish-no-situation",
        "question": "asdfjkl qwerty zxcv 12345 lorem ipsum",
        "expect_status": ("no_decomposition", "no_candidates"),
        "expect_show_user": False,
        "notes": "No legal situation. The extractor should return nothing and the "
                 "function should stop at no_decomposition -- never a raise, never a "
                 "fabricated issue.",
    },
]


# ===========================================================================
# OFFLINE fixture -- a compact mocked pipeline so the harness (and its
# report format) can be exercised for free / in CI.  These cases test the
# GATES and INVARIANTS, not retrieval quality.
# ===========================================================================
_OFF_TODAY = datetime.date(2026, 9, 5)


def _off_ik_doc(tid, title, court="Delhi High Court"):
    return {"tid": tid, "title": title, "docsource": court,
            "publishdate": "2025-03-01", "headline": "snippet"}


def _off_corpus_rec(name, para, text, score=0.6):
    return {"type": "judgment", "chunk_id": f"judgment:{name}:{para}", "case_name": name,
            "paragraph_number": para, "text": text, "score": score,
            "source_url": f"https://indiankanoon.org/doc/{para}/"}


# Per-offline-case canned decomposition + search results, keyed by slug.
_OFF = {
    "off-whitelisted-dk-basu": {
        "decompose": {
            "primary_grievance": "beaten in custody, no medical exam",
            "procedural_stage": "pre-chargesheet",
            "issues": [
                {"issue": "physical assault of a detainee in police custody",
                 "hook_phrase": "he was slapped in the lockup", "section_hooks": ["D.K. Basu"]},
                {"issue": "failure to conduct a medical examination after arrest",
                 "hook_phrase": "never taken for a medical check-up", "section_hooks": ["D.K. Basu"]},
            ],
        },
        "ik": [_off_ik_doc(9001, "Ramesh vs State Of U.P. on 4 March, 2021"),
               _off_ik_doc(9002, "Suresh Kumar vs State bail order on 1 May, 2022")],
        "corpus": [_off_corpus_rec(
            "D.K. Basu v State of West Bengal", "35",
            "An arrestee must be medically examined and any custodial assault or torture "
            "is prohibited; the safeguards apply to every arrest.", score=0.82)],
        "fetch": {
            "9001": ("<p data-structure='Analysis' id='p1'>1. The petitioner alleged he was "
                     "assaulted in the lockup and not produced for medical examination.</p>"
                     "<p data-structure='Conclusion' id='p2'>2. The State is directed to hold "
                     "an inquiry into the custodial treatment.</p>"),
            # Structure tags present but NONE are reasoning tags, plus a
            # disposal phrase -> classify_document_finality flags it procedural.
            "9002": ("<p data-structure='Facts' id='p1'>1. Heard counsel for the applicant.</p>"
                     "<p data-structure='Facts' id='p2'>2. The bail application is allowed and "
                     "the applicant be enlarged on bail on furnishing a bond.</p>"),
        },
        "expect": {
            "expect_show_user": True,
            "expect_topics": ["dk_basu_safeguards"],
            "expect_case": [("d.k. basu",)],
            "expect_displayed": ["basu"],
            "must_not_displayed": ["suresh kumar"],
            "expect_procedural_flagged": ["suresh kumar"],
            "notes": "Whitelisted. D.K. Basu displays; the 'bail application is allowed' IK "
                     "order (9002) is flagged procedural and kept out of for_display.",
        },
    },
    "off-not-whitelisted-property": {
        "decompose": {
            "primary_grievance": "FIR over a land dispute, arrest threatened",
            "procedural_stage": "pre-arrest",
            "issues": [
                {"issue": "criminal FIR arising from a civil property dispute",
                 "hook_phrase": "a property dispute about ancestral land", "section_hooks": []},
            ],
        },
        "ik": [_off_ik_doc(9101, "Kamla Devi vs State Of Haryana on 8 August, 2023"),
               _off_ik_doc(9102, "Ravinder Singh vs State on 2 February, 2024")],
        "corpus": [],
        "fetch": {
            "9101": ("<p data-structure='Analysis' id='p1'>1. A property dispute does not by "
                     "itself constitute a cognizable offence and the Court examined whether "
                     "the FIR disclosed one.</p>"
                     "<p data-structure='Conclusion' id='p2'>2. The petition is disposed of "
                     "with directions to the investigating officer.</p>"),
            "9102": ("<p data-structure='Analysis' id='p1'>1. The parties are in a long-running "
                     "civil suit over the same land.</p>"),
        },
        "expect": {
            "expect_show_user": False,
            "expect_case": [("kamla devi", "ravinder singh")],
            "expect_displayed": ["kamla devi", "ravinder singh"],
            "notes": "NOT whitelisted -> for_display empty, unverified_for_display holds the "
                     "full ranked list, bundle still written.",
        },
    },
    "off-disabled": {
        "disable_live": True,
        "decompose": {"primary_grievance": "x", "issues": [
            {"issue": "y", "hook_phrase": "y", "section_hooks": []}]},
        "ik": [], "corpus": [], "fetch": {},
        "expect": {
            "expect_status": ("disabled",),
            "expect_show_user": False,
            "notes": "Kill switch set -> status 'disabled', no work, both panels empty.",
        },
    },
    "off-no-decomposition": {
        "decompose": None,
        "ik": [], "corpus": [], "fetch": {},
        "expect": {
            "expect_status": ("no_decomposition",),
            "expect_show_user": False,
            "notes": "Extractor returns nothing -> status 'no_decomposition', never a raise.",
        },
    },
    "off-whitelisted-but-weak": {
        "decompose": {
            "primary_grievance": "not told grounds of arrest",
            "procedural_stage": "post-arrest",
            "issues": [
                {"issue": "grounds of arrest not communicated in writing",
                 "hook_phrase": "never told the grounds in writing",
                 "section_hooks": ["Article 22"]},
            ],
        },
        # Only weak, barely-overlapping IK hits and NO corpus hit -> for_display
        # will be empty even though show_user is True.  The regression guard
        # (panels never both empty) must still pass via unverified fallback.
        "ik": [_off_ik_doc(9201, "Unrelated Zoning Appeal vs Municipal Board on 9 September, 2019")],
        "corpus": [],
        "fetch": {
            "9201": ("<p data-structure='Analysis' id='p1'>1. This appeal concerns a building "
                     "plan sanction and has nothing to do with arrest.</p>"),
        },
        "expect": {
            "expect_show_user": True,
            "expect_topics": ["grounds_of_arrest_communicated"],
            "notes": "show_user True but every candidate scores under the display floor -> "
                     "for_display empty, unverified_for_display falls back to the full list "
                     "(the 2026-09-05 'both panels empty' regression guard).",
        },
    },
}


def _offline_fns(slug):
    """Build the injected-callable set for one offline case."""
    spec = _OFF[slug]

    def decompose_fn(_msg):
        d = spec["decompose"]
        return json.loads(json.dumps(d)) if d else None

    def ik_search_many_fn(queries):
        docs = spec["ik"]
        return {q: {"docs": list(docs)} for q in queries}

    def local_search_fn(_query):
        return [json.loads(json.dumps(r)) for r in spec["corpus"]]

    def rerank_fn(q, docs, top_k=None):
        ql = set(re.findall(r"[a-z]+", q.lower()))
        out = []
        for i, d in enumerate(docs):
            dl = set(re.findall(r"[a-z]+", d.lower()))
            out.append({"index": i, "score": len(ql & dl) / (len(ql) + 1), "document": d})
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:top_k] if top_k else out

    def fetch_many_fn(tids):
        return {str(t): {"doc": spec["fetch"].get(str(t), "")} for t in tids}

    def clean_fn(html):
        paras = []
        for m in re.finditer(r"<p(?:\s+data-structure='([^']*)')?[^>]*>(.*?)</p>", html):
            paras.append({"tag": "p", "structure": m.group(1) or None, "text": m.group(2),
                          "has_citation": False, "citation_sentiments": []})
        return {"title": "offline", "paragraphs": paras, "paragraph_count": len(paras)}

    def gloss_fn(_situation, paragraphs_text):
        # A plain descriptive sentence, no verdict/binding language, so it
        # passes _verify_gloss.  "bail" mentions get the off-point sentence
        # the pipeline itself uses.
        low = paragraphs_text.lower()
        if "bail application is allowed" in low or "enlarged on bail" in low:
            return "This one may not be closely on point."
        if "zoning" in low or "building plan" in low:
            return "This one may not be closely on point."
        return "This judgment dealt with the treatment of a person after arrest and the safeguards the police must observe."

    return dict(decompose_fn=decompose_fn, ik_search_many_fn=ik_search_many_fn,
                local_search_fn=local_search_fn, rerank_fn=rerank_fn,
                fetch_many_fn=fetch_many_fn, clean_fn=clean_fn, gloss_fn=gloss_fn,
                today=_OFF_TODAY)


def _offline_cases():
    cases = []
    for slug, spec in _OFF.items():
        c = {"id": slug, "question": f"[offline fixture] {slug}",
             "disable_live": spec.get("disable_live", False)}
        c.update(spec["expect"])
        cases.append(c)
    return cases


# ===========================================================================
# Checks + metrics
# ===========================================================================
def _title(cand):
    return (cand.get("triage", {}).get("title") or "").lower()


def _check_group(haystack_titles, group):
    """group: a tuple of substrings; ok if any appears in any title."""
    hits = [g for g in group if any(g.lower() in t for t in haystack_titles)]
    return (bool(hits), f"any({list(group)}) -> {hits or 'NONE'}")


def _displayed_titles(result):
    seen, out = set(), []
    for key in ("for_display", "unverified_for_display"):
        for c in result.get(key) or []:
            k = rj._judgment_identity(c)
            if k not in seen:
                seen.add(k)
                out.append(_title(c))
    return out


def _run(question, kwargs, *, disable_live, offline_slug):
    """One get_related_judgments call. Offline runs are made hermetic:
    the mutable approved-store (related_judgments_approved.json) is stubbed
    to [] so a fixture case never depends on what a live session happened
    to save."""
    stack = []
    if disable_live:
        stack.append(patch.dict(os.environ, {rj._KILL_SWITCH_ENV: "1"}))
    if offline_slug is not None:
        stack.append(patch.object(rj, "approved_candidates", lambda profile, **kw: []))
    for ctx in stack:
        ctx.__enter__()
    try:
        return rj.get_related_judgments(question, **kwargs)
    finally:
        for ctx in reversed(stack):
            ctx.__exit__(None, None, None)


def run_case(case, *, offline, pin, gloss):
    t0 = time.time()
    kwargs = dict(write_bundle=not offline, pin=pin, gloss=gloss)
    slug = case["id"] if offline else None
    if offline:
        kwargs.update(_offline_fns(case["id"]))

    try:
        result = _run(case["question"], kwargs,
                      disable_live=case.get("disable_live", False), offline_slug=slug)
    except Exception as exc:  # noqa: BLE001 -- get_related_judgments is documented never to raise
        return {"id": case["id"], "error": repr(exc), "elapsed": round(time.time() - t0, 1)}

    profile = result.get("profile") or {}
    issues = profile.get("issues", []) or []
    wl = result.get("whitelist") or {}
    topics = sorted({t for _, t in wl.get("by_issue", []) if t})
    hooks = [i.get("hook_phrase", "") for i in issues]
    cands = result.get("candidates") or []
    for_display = result.get("for_display") or []
    unverified = result.get("unverified_for_display") or []
    n_corpus = sum(1 for c in cands if c.get("source") == "corpus")
    n_ik = sum(1 for c in cands if c.get("source") == "indiankanoon")
    disp_titles = _displayed_titles(result)
    fd_titles = [_title(c) for c in for_display]

    # per-displayed-candidate quality
    disp_quality = []
    for c in for_display:
        g = c.get("gloss")
        pinned = c.get("pinned") or []
        disp_quality.append({
            "title": c.get("triage", {}).get("title"),
            "has_gloss": bool(g),
            "gloss_off_point": bool(g and _OFF_POINT_RE.search(g)),
            "gloss_forbidden": bool(g and any(b in g.lower() for b in _GLOSS_FORBIDDEN)),
            "n_pinned": len(pinned),
            "pinned_numbered": all(p.get("para_number") for p in pinned) if pinned else False,
        })

    procedural_flagged = [c.get("triage", {}).get("title")
                          for c in cands if c.get("procedural_disposal") is True]
    procedural_in_fd = [t for t in fd_titles
                        for c in for_display
                        if _title(c) == t and c.get("procedural_disposal") is True]

    checks = []

    want_status = case.get("expect_status", ("ok",))
    want_status = want_status if isinstance(want_status, tuple) else (want_status,)
    checks.append(("status", result.get("status") in want_status,
                   f"{result.get('status')} (want {' or '.join(want_status)})"))

    if case.get("expect_show_user") is not None:
        checks.append(("show_user", result.get("show_user") is case["expect_show_user"],
                       f"{result.get('show_user')} (want {case['expect_show_user']})"))

    if case.get("min_issues"):
        checks.append(("min_issues", len(issues) >= case["min_issues"],
                       f"{len(issues)} issue(s) (want >= {case['min_issues']})"))

    for sub in case.get("hook_substrings", []):
        ok = any(sub.lower() in h.lower() for h in hooks)
        checks.append(("hook", ok, f"{sub!r} in a kept hook -> {ok}  hooks={hooks}"))

    for topic in case.get("expect_topics", []):
        checks.append(("topic", topic in topics, f"{topic!r} in {topics}"))

    ranked_titles = [_title(c) for c in cands]
    for group in case.get("expect_case", []):
        ok, detail = _check_group(ranked_titles, group)
        checks.append(("expect_case", ok, detail))

    for sub in case.get("expect_displayed", []):
        ok = any(sub.lower() in t for t in disp_titles)
        checks.append(("expect_displayed", ok, f"{sub!r} in a panel -> {ok}"))

    for sub in case.get("must_not_displayed", []):
        ok = not any(sub.lower() in t for t in fd_titles)
        checks.append(("must_not_displayed", ok,
                       f"{sub!r} {'absent from' if ok else 'PRESENT IN'} for_display"))

    for sub in case.get("expect_procedural_flagged", []):
        ok = any(sub.lower() in (t or "").lower() for t in procedural_flagged)
        checks.append(("procedural_flagged", ok,
                       f"{sub!r} flagged procedural -> {ok}  flagged={procedural_flagged}"))

    # --- invariants, checked on every case ---
    checks.append(("INVARIANT no procedural in for_display", not procedural_in_fd,
                   f"{procedural_in_fd or 'none'}"))
    if result.get("status") == "ok":
        checks.append(("INVARIANT panels not both empty",
                       bool(for_display) or bool(unverified),
                       f"for_display={len(for_display)} unverified={len(unverified)}"))
    bad_gloss = [d["title"] for d in disp_quality if d["gloss_forbidden"] or d["gloss_off_point"]]
    if disp_quality:
        checks.append(("INVARIANT displayed glosses clean", not bad_gloss,
                       f"{bad_gloss or 'all clean'}"))
    if pin and for_display:
        missing_pins = [d["title"] for d in disp_quality if d["n_pinned"] == 0]
        checks.append(("displayed have pinned paras", not missing_pins,
                       f"{missing_pins or 'all pinned'}"))

    return {
        "id": case["id"],
        "question": case["question"],
        "notes": case.get("notes", ""),
        "status": result.get("status"),
        "degraded": result.get("degraded"),
        "show_user": result.get("show_user"),
        "grievance": profile.get("primary_grievance"),
        "issues": [{"issue": i.get("issue"), "hook": i.get("hook_phrase"),
                    "topic": dict(wl.get("by_issue", [])).get(i.get("issue"))}
                   for i in issues],
        "whitelist_covered": wl.get("covered"),
        "whitelist_uncovered": wl.get("uncovered"),
        "topics": topics,
        "n_candidates": len(cands),
        "n_corpus": n_corpus,
        "n_ik": n_ik,
        "n_for_display": len(for_display),
        "n_unverified": len(unverified),
        "top_score": round(cands[0]["score"], 3) if cands else None,
        "displayed": disp_quality,
        "procedural_flagged": procedural_flagged,
        "ranked": [{"score": round(c.get("score", 0), 3), "source": c.get("source"),
                    "title": c.get("triage", {}).get("title"),
                    "procedural": c.get("procedural_disposal"),
                    "gloss": c.get("gloss")} for c in cands],
        "checks": checks,
        "n_fail": sum(1 for _, ok, _ in checks if not ok),
        "elapsed": round(time.time() - t0, 1),
    }


# ===========================================================================
# Report
# ===========================================================================
def _write_report(results, out_dir, tag, mode):
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)

    lines = [f"# Related-judgments (Lane B) eval  ({tag})  [{mode}]", ""]
    total_fail = 0
    for r in results:
        if "error" in r:
            lines += [f"## {r['id']}  -- ERROR", "```", r["error"], "```", ""]
            total_fail += 1
            continue
        total_fail += r["n_fail"]
        lines.append(f"## {r['id']}   [{r['n_fail']} check failure(s)]")
        lines.append(f"**Q:** {r['question']}")
        lines.append(f"**Ideal:** {r['notes']}")
        lines.append(
            f"status=`{r['status']}` show_user=`{r['show_user']}` "
            f"degraded=`{r['degraded']}` covered=`{r['whitelist_covered']}` "
            f"top_score=`{r['top_score']}` ({r['elapsed']}s)")
        lines.append(
            f"candidates=`{r['n_candidates']}` (corpus `{r['n_corpus']}` / IK `{r['n_ik']}`)  "
            f"for_display=`{r['n_for_display']}`  unverified=`{r['n_unverified']}`  "
            f"procedural_flagged=`{len(r['procedural_flagged'])}`")
        if r["whitelist_uncovered"]:
            lines.append(f"panel hidden by uncovered issue(s): `{r['whitelist_uncovered']}`")
        lines.append("")
        for i in r["issues"]:
            lines.append(f"- issue: {i['issue']}  <- {i['hook']!r}  **[{i['topic'] or 'NOT whitelisted'}]**")
        lines.append("")
        for name, ok, detail in r["checks"]:
            lines.append(f"- [{'x' if ok else ' '}] {name}: {detail}")
        lines.append("")
        lines.append("**Ranked candidates:**")
        lines.append("")
        for c in r["ranked"]:
            flag = " _(procedural)_" if c["procedural"] is True else ""
            lines.append(f"- `{c['score']}` [{c['source']}] {c['title']}{flag}")
            if c["gloss"]:
                lines.append(f"  - gloss: {c['gloss']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.insert(1, f"\n**{len(results)} cases, {total_fail} total check failures "
                    f"(directional -- read the report, this is not a gate).**\n")
    report_path = os.path.join(out_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return report_path, total_fail


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true",
                    help="run the mocked fixture cases -- no API calls, no cost")
    ap.add_argument("--only", action="append", help="run only these case ids (repeatable)")
    ap.add_argument("--limit", type=int, help="run only the first N cases")
    ap.add_argument("--label", default=None, help="tag for the output dir (e.g. 'before')")
    ap.add_argument("--out-root", default="eval_related_out")
    ap.add_argument("--no-fetch", action="store_true",
                    help="stop after ranking -- no IK full-document fetches (live mode)")
    ap.add_argument("--no-gloss", action="store_true",
                    help="skip the Sonnet gloss call (live mode)")
    args = ap.parse_args()

    mode = "offline" if args.offline else "live"
    cases = _offline_cases() if args.offline else LIVE_CASES
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        sys.exit("no cases selected")

    if not args.offline:
        est = len(cases)
        print(f"LIVE mode: {est} case(s), real Indian Kanoon + Voyage + Anthropic calls.")
        print("  ~1 Haiku + 2-6 IK searches"
              + ("" if args.no_fetch else " + up to ~6 IK fetches")
              + ("" if args.no_gloss else " + up to ~6 Sonnet glosses")
              + " per case.\n")

    stamp = _dt.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = f"{stamp}-{args.label}" if args.label else stamp
    out_dir = os.path.join(args.out_root, tag)
    os.makedirs(out_dir, exist_ok=True)

    results = []
    for c in cases:
        print(f"  running {c['id']} ...", flush=True)
        results.append(run_case(c, offline=args.offline,
                                pin=not args.no_fetch, gloss=not args.no_gloss))

    report_path, total_fail = _write_report(results, out_dir, tag, mode)
    print(f"\n{len(results)} cases, {total_fail} total check failures.")
    print(f"report: {report_path}")
    for r in results:
        flag = "ERR" if "error" in r else f"{r['n_fail']:>2} fail"
        print(f"  {flag}  {r['id']}")


if __name__ == "__main__":
    main()
