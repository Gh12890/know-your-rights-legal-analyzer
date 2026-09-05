
"""
Semantic retrieval, Phase 2: real embeddings with scores, layered on top
of (never replacing) the exact-lookup retrieval built in retrieval.py.

Purpose: answer "which section(s)/judgment paragraph(s) are plausibly
relevant to this open-ended question?" -- something exact lookup cannot
do, since it requires already knowing a section number or doctrine name.
This is the missing piece for a chat interface where a layman describes a
situation in plain words rather than citing a section.

CRITICAL DESIGN RULE, carried over from the whole session's architecture:
this module NEVER decides a compliance verdict and NEVER answers a legal
question directly. It only returns ranked candidates with similarity
scores. Whatever calls this is responsible for (a) checking the score
against SIMILARITY_THRESHOLD before trusting a match at all, and (b)
routing any accepted match through the SAME deterministic lookups already
built (retrieval.py's get_statute_section / get_judgment_doctrine,
BNS_SECTION_DATA, the check_* functions in main.py) -- never generating an
answer straight from the retrieved text.

Why a real threshold matters here specifically (not just in the abstract):
"Can police arrest me directly for rioting?" genuinely matches MULTIPLE
BNS sections with materially different answers (191(2)/191(3), cognizable
vs 193(1)/(2)/(3), non-cognizable, a different question about
compensation liability). A single best-match answer would silently pick
one and hide the conflict. This module is built to surface "multiple
strong matches with different answers" as its own explicit case, not
just "one match, trust it" or "no match, give up" -- the same
"MIXED cognizability" honesty already implemented in
check_cognizable_arrest_basis, just extended to open-ended questions.
"""

import json
import os
import numpy as np


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv should already be installed (main.py depends on it)

try:
    import voyageai
    _voyage_available = True
except ImportError:
    _voyage_available = False

MODEL = "voyage-law-2"
RERANK_MODEL = "rerank-2"
EMBEDDINGS_PATH = "embeddings/corpus_embeddings.json"


SIMILARITY_THRESHOLD = 0.40
#Threshold level put at 0.40 down from 0.75. 1 means identical , pointing in same direction. 

# If multiple matches clear the threshold but disagree on a key legal
# attribute (e.g. different cognizable/bailable status for statute
# matches), surface that conflict explicitly rather than picking the
# top-ranked one. This gap defines "materially different" for the
# purposes of flagging a conflict.



# CONFIRMED REAL BUG (2026-09-01), found via live testing on "police came
# to my house and arrested me directly saying that i stole a goat": BNS
# Section 303 (theft) never appeared in the answer at all, even though it
# scored 0.3619 -- comfortably above STATUTE_SIMILARITY_THRESHOLD (0.34).
# Root cause: semantic_search() ranks statute AND judgment chunks
# TOGETHER in one combined pool, sorted by raw score, THEN slices to the
# top TOP_MATCHES_TO_CONSIDER BEFORE find_relevant_sections() ever splits
# them by type and applies the (deliberately different) per-type
# thresholds. For this exact query, all top 10 combined-ranked results
# were judgment paragraphs (arrest-procedure judgments score consistently
# higher than statute text on arrest-flavoured questions) -- direct
# verification found 13 real statute candidates clearing 0.34, but the
# last of them only appears at rank 39 in the combined list, so 12 of 13
# (including Section 303 itself) were silently discarded before the
# threshold filter ever ran. The SAME bug independently affects
# interview_flow.py's offence-identification path (semantic_search() at
# line ~562 there), which also filters `type == "statute"` out of this
# same shared, prematurely-truncated pool.
# FIX: raised from 10 to 50. This is a pure widening of the candidate
# pool, not a threshold change -- STATUTE_SIMILARITY_THRESHOLD/
# JUDGMENT_SIMILARITY_THRESHOLD still do the actual relevance filtering
# downstream, so nothing that would have failed the threshold before can
# pass now. 50 comfortably covers the confirmed real case (last
# qualifying statute candidate at rank 39) with margin, at negligible
# cost -- the expensive step (the full corpus @ query-vector matrix
# multiply, computed once per query regardless of top_k) is unchanged;
# only the post-hoc argsort/slice grows, which is microseconds even at
# this corpus's full ~1595-chunk size.
TOP_MATCHES_TO_CONSIDER = 50

_corpus_cache = None


def _load_corpus_embeddings():
    global _corpus_cache
    if _corpus_cache is not None:
        return _corpus_cache
    if not os.path.exists(EMBEDDINGS_PATH):
        return None
    with open(EMBEDDINGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = data["records"]
    # Precompute the embedding matrix once, since dot-product against a
    # numpy matrix is far faster than looping in Python per query.
    matrix = np.array([r["embedding"] for r in records])
    _corpus_cache = {"records": records, "matrix": matrix, "model": data.get("model")}
    return _corpus_cache


def semantic_search(query, top_k=TOP_MATCHES_TO_CONSIDER, _raise_errors=False):
    """Embeds `query` and returns the top_k closest corpus chunks by
    similarity score, each as a dict with the chunk's metadata plus a
    'score' field. Returns None if embeddings aren't available at all
    (no API key, no corpus_embeddings.json, or the voyageai package isn't
    installed) -- callers must treat None the same honest way every other
    "Cannot Determine" case in this project is treated, not as an error
    to hide.

    _raise_errors: debugging aid only, defaults to False (production
    behavior: swallow to None). Set True temporarily to see the real
    exception instead of a bare None if something unexpected breaks again.

    Does NOT apply SIMILARITY_THRESHOLD itself -- returns raw scored
    results so callers can inspect the full picture (e.g. to detect a
    genuine multi-match conflict) before deciding what to trust."""
    if not _voyage_available:
        return None
    corpus = _load_corpus_embeddings()
    if corpus is None:
        return None

    client = voyageai.Client()
    try:
        query_embedding = client.embed([query], model=MODEL, input_type="query").embeddings[0]
    except Exception:
        if _raise_errors:
            raise
        # Network/API failure -- honest None, not a crash, not a guess.
        return None

    query_vec = np.array(query_embedding)
    scores = corpus["matrix"] @ query_vec  # dot product; Voyage embeddings are pre-normalized
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        record = dict(corpus["records"][idx])
        record.pop("embedding", None)  # don't return the raw vector to callers
        record["score"] = float(scores[idx])
        results.append(record)
    return results


def rerank(query, documents, top_k=None, _raise_errors=False):
    """Score `documents` (a list of strings) for relevance to `query`
    using Voyage's cross-encoder reranker, which reads the query and each
    document TOGETHER -- unlike semantic_search's separate-embedding
    cosine, which loses nuance on long, multi-part queries.

    Used by related_judgments.py (Lane B) to rank a pool of candidate
    judgments against the user's FULL situation, and to pin the on-point
    paragraphs within a fetched judgment.

    Returns a list of {"index": int, "score": float, "document": str},
    sorted best-first (length min(top_k, len(documents))), OR None if the
    reranker is unavailable (no voyageai, no API key, network failure) --
    callers must treat None as an honest "could not rank", the same as
    semantic_search returning None, and fall back rather than crash.

    A scoring function, not a generator: it invents nothing and cites
    nothing. Consistent with this project's one architectural principle.
    """
    if not _voyage_available:
        return None
    docs = [d for d in (documents or []) if isinstance(d, str) and d.strip()]
    if not query or not docs:
        return []

    try:
        client = voyageai.Client()
        resp = client.rerank(query, docs, model=RERANK_MODEL, top_k=top_k)
    except Exception:
        if _raise_errors:
            raise
        return None

    out = []
    for r in getattr(resp, "results", []) or []:
        out.append({
            "index": int(r.index),
            "score": float(r.relevance_score),
            "document": docs[int(r.index)],
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


"""
ADD near the top of semantic_retrieval.py, replacing the single
SIMILARITY_THRESHOLD constant with two separate ones.

WHY SPLIT (2026-08-28): a real user question -- "police came to my
house and arrested me saying that i stole a goat" -- failed to surface
BNS Section 303 (theft) at all. Confirmed real score: 0.3542, just
below the single shared threshold of 0.40. Investigating this revealed
the deeper problem: statute matching and judgment matching were being
held to the SAME threshold, despite being fundamentally different
kinds of evidence:

- Statute sections are a CLOSED, fully-known vocabulary -- all ~360
  BNS sections and ~530 BNSS sections are already embedded, already
  verified, already have deterministic compliance data in
  BNS_SECTION_DATA. A statute match either genuinely applies or it
  doesn't; there's little risk in being more permissive here, since
  the SET of possible statute matches is small and fully controlled.
- Judgment/doctrine matches pull from a fuzzier, more open precedent
  space (currently 12 judgments, growing). Being too permissive here
  risks surfacing a genuinely unrelated case merely because it shares
  vocabulary -- a different, real risk (see BNS_SECTION_DATA's own
  "conflicting_matches" logic, built for exactly this kind of danger).

Given this asymmetry, statutes get a LOWER (more permissive) threshold
than judgments. The specific values below were chosen by testing
against every real confirmed score available at time of writing (this
session's goat-theft/D.K.-Basu/Prabir-Purkayastha/Youth-Bar-Association
scores, plus the Aug 27 handoff's BNSS-43(5) and confirmed-noise-ceiling
numbers) -- see the accompanying test script's output for the full
comparison table. STATUTE_SIMILARITY_THRESHOLD=0.34 was the narrowest
value that fixed both known statute-retrieval failures (goat theft at
0.3542, a hypothetical near-BNSS-43(5)-adjacent statute score) without
crossing the confirmed noise ceiling (~0.339) -- this is a narrow
margin (0.001), acknowledged directly, not a comfortable buffer.
JUDGMENT_SIMILARITY_THRESHOLD is kept at the existing 0.40, UNCHANGED,
since no confirmed real judgment-matching failure has been found at
that threshold -- lowering it was never the actual problem, and doing
so anyway would add judgment-matching risk to solve a statute-matching
problem.

MUST be revisited if a real failure is later found on either side of
this split -- these are evidence-based starting points from a small
number of real data points, not a large-scale calibration.
"""

STATUTE_SIMILARITY_THRESHOLD = 0.34
JUDGMENT_SIMILARITY_THRESHOLD = 0.40

# conflicting_matches is only declared when the competing provisions are
# BOTH genuinely relevant: each must score at least CONFLICT_MIN_SCORE
# (a real, confident match -- not noise-level) AND be within
# CONFLICT_SCORE_MARGIN of the top statute match. A genuine "the law
# forks here" case (e.g. "can police arrest me for cheating" -> 318(2)
# no vs 318(4) yes) has the competing provisions scoring high and close
# together, usually as subsections of the same section. When the best
# statute match is only noise-level (~0.36, as for "stole a goat",
# where nothing aligns cleanly), there is no confident fork to surface
# -- fall through to single_match and let the answer explain from the
# (weak) statute set plus the judgment matches. See the long note in
# find_relevant_sections().
CONFLICT_SCORE_MARGIN = 0.03
CONFLICT_MIN_SCORE = 0.40

# How many match blocks actually reach the answer generator.
#
# WHY (2026-09-02): threshold filtering (0.34 statute / 0.40 judgment) is
# a deliberately low bar -- for a typical situation question ~18 blocks
# clear it, of which only a handful are genuinely on point and the rest
# are topic-adjacent noise. Confirmed real case: "police... arrested me...
# saying that i stole a goat" put 13 statute candidates over 0.34, the
# last at rank 39; feeding all of them let the model wander to a
# tangential procedural section instead of staying on BNS 303 (theft).
# The Phase 5 offence-keyword anchor worked around this by injecting one
# strong correct match; this is the actual fix -- rank what cleared the
# threshold and keep only the strongest.
#
# Two-stage, applied PER TYPE (statute and judgment capped separately, so
# a weaker-scoring but genuinely relevant judgment is never crowded out
# by statute chunks or vice versa), on the already-score-ordered list:
#   1. relative gap -- drop anything scoring more than MATCH_SCORE_GAP
#      below that type's top match (adapts: keeps all of a genuine
#      multi-section cluster, trims a lone strong match's noise tail).
#   2. absolute cap -- then keep at most MAX_*_MATCHES_FOR_PROMPT.
# The top match of each type is always kept. Both stages are strictly
# looser than the conflicting_matches gate (within CONFLICT_SCORE_MARGIN
# 0.03 of top AND >= CONFLICT_MIN_SCORE 0.40), so conflict detection sees
# every provision it did before -- see _conflict_state().
MATCH_SCORE_GAP = 0.08
MAX_STATUTE_MATCHES_FOR_PROMPT = 5
MAX_JUDGMENT_MATCHES_FOR_PROMPT = 4

# Kept for any external code that still imports the old combined name
# directly -- deliberately aliased to the MORE CONSERVATIVE (judgment)
# value, not the more permissive statute one, so nothing that isn't
# explicitly updated to use the split constants silently becomes more
# permissive by accident.
SIMILARITY_THRESHOLD = JUDGMENT_SIMILARITY_THRESHOLD

# Case names embedded in the shared corpus for the freeze / cheque-bounce
# document-upload domains (built for main.py's compliance checks, not this
# arrest/FIR chat -- chat_assistant.SCOPE_CLASSIFIER_PROMPT tells the
# scope classifier this chat's OWN case law does not cover them). They
# live in the same embeddings file only because it is shared, so a
# generic similarity hit against one of them is never real arrest/FIR
# case law and must not be treated as a "verified corpus" authority for
# this chat feature or Lane B.
#
# CONFIRMED REAL FAILURE (2026-09-04): "Rangappa v Sri Mohan" -- an NI
# Act S.139 cheque-presumption case -- scored 0.409 (just above
# JUDGMENT_SIMILARITY_THRESHOLD) against a question about cheating and
# criminal breach of trust in a partnership, purely on "loan"/"signature"
# vocabulary overlap, and was then quoted as "relevant judicial
# authority" in a drafted representation about an offence it has nothing
# to do with. A curated exclusion list, not a score-based fix, because
# the failure is categorical (wrong legal domain), not a matter of degree.
OUT_OF_CHAT_DOMAIN_CASE_NAMES = frozenset({
    "Rangappa v Sri Mohan",
    "Bir Singh v Mukesh Kumar",
    "Damodar S. Prabhu v Sayed Babalal H",
    "Kaveri Plastics v Mahdoom Bawa Bahrudeen Noorul",
    "Prakash Chimanlal Sheth v Jagruti Keyur Rajpopat",
    "Malabar Gold and Diamond Limited v Union of India",
    "Neelkanth Pharma Logistics Pvt. Ltd. v Union of India",
    "State of Maharashtra v Tapas D. Neogy",
})


# ---------------------------------------------------------------------
# REPLACE find_relevant_sections() with this version:
# ---------------------------------------------------------------------

def find_relevant_sections(query):
    """Higher-level function for BOTH statute and judgment lookup: returns
    a dict describing what was found, in one of four honest states --
    'no_match' (nothing cleared its applicable threshold), 'single_match'
    (exactly one section family cleared the threshold and they agree),
    'conflicting_matches' (multiple STATUTE sections cleared the
    threshold with DIFFERENT cognizable/bailable status -- the "rioting"
    case), or 'unavailable' (embeddings aren't set up at all). Never
    silently picks one match to hide a conflict.

    CHANGED 2026-08-28: statute and judgment matches are now filtered
    against SEPARATE thresholds (STATUTE_SIMILARITY_THRESHOLD=0.34,
    JUDGMENT_SIMILARITY_THRESHOLD=0.40), not one shared value. See the
    module-level comment above these constants for the full confirmed
    real-failure writeup (goat theft, Section 303, scored 0.3542 --
    below the old shared 0.40 threshold, now correctly caught). This
    was a deliberate, evidence-based split, not a blanket threshold
    lowering -- judgment matching keeps its prior, more conservative
    value unchanged, since no real judgment-matching failure has been
    found to justify loosening it.

    CONFIRMED REAL BUG (2026-08-27): this function previously filtered
    to statute matches ONLY (discarding every judgment match, however
    highly ranked), despite its use as the single retrieval entry point
    for chat_assistant.py's open-ended chat feature. Confirmed real
    case: for "is theft a serious crime that lets police arrest me right
    away?", Arnesh Kumar v State of Bihar scored HIGHEST of all 15
    results (0.407, ahead of every statute match) but was completely
    invisible to the chat feature -- it could only ever discuss
    cognizability from bare statute text, never surface the actual
    arrest-procedure case law that was the single best match. Fixed to
    also return judgment matches clearing the threshold, as a separate
    'judgment_matches' field -- the existing statute-only conflict logic
    is untouched, since that's correctly scoped to a narrower, real
    concern (statutes disagreeing on cognizable/bailable status), not a
    general "should judgments be included" question."""
    results = semantic_search(query)
    if results is None:
        return {"state": "unavailable"}

    statute_matches = [r for r in results if r["type"] == "statute" and r["score"] >= STATUTE_SIMILARITY_THRESHOLD]
    judgment_matches = [r for r in results if r["type"] == "judgment" and r["score"] >= JUDGMENT_SIMILARITY_THRESHOLD
                         and r.get("case_name") not in OUT_OF_CHAT_DOMAIN_CASE_NAMES]

    # Keep only the strongest blocks per type before anything downstream
    # (enrichment, conflict detection, prompt assembly) sees them -- see
    # the MATCH_SCORE_GAP / MAX_*_MATCHES_FOR_PROMPT note above.
    statute_matches = _cap_matches(statute_matches, MAX_STATUTE_MATCHES_FOR_PROMPT)
    judgment_matches = _cap_matches(judgment_matches, MAX_JUDGMENT_MATCHES_FOR_PROMPT)

    if not statute_matches and not judgment_matches:
        return {"state": "no_match", "results": results}

    # Pull each matched section's actual compliance data via the SAME
    # deterministic table used everywhere else in this project -- this
    # function's job ends at "which sections look relevant"; it does not
    # decide cognizability itself.
    try:
        from main import BNS_SECTION_DATA
    except ImportError:
        BNS_SECTION_DATA = {}

    enriched = []
    for m in statute_matches:
        sec_key = m["section_number"]
        # CONFIRMED REAL BUG (2026-08-27): a direct .get(sec_key) only
        # finds an EXACT match. BNS_SECTION_DATA keys 239 of 436 entries
        # (55%) by subsection (e.g. "191(2)", "191(3)"), not the bare
        # top-level number semantic search always returns (statute
        # chunks are split at the top-level section boundary only, per
        # chunk_corpus.py). Confirmed real case: "191" has no bare-key
        # entry at all -- only "191(2)" and "191(3)" exist, both
        # cognizable. A direct .get("191") silently returned None,
        # meaning this section's real compliance data was never actually
        # checked for conflicts. Fixed by pulling every subsection
        # variant of the matched bare number and treating them as this
        # match's full data set, same as retrieval.py's exact-lookup
        # code already does for the equivalent problem elsewhere.
        exact = BNS_SECTION_DATA.get(sec_key)
        subsection_variants = {
            k: v for k, v in BNS_SECTION_DATA.items()
            if k == sec_key or k.startswith(f"{sec_key}(")
        }
        if exact is not None and sec_key not in subsection_variants:
            subsection_variants[sec_key] = exact
        enriched.append({**m, "section_data": exact, "all_variants": subsection_variants})

    # A conflict is only checked across statute matches, since it's
    # specifically about disagreeing cognizable/bailable classifications
    # -- a concept that doesn't apply to judgment paragraphs the same way.
    #
    # CONFIRMED REAL FAILURE (2026-09-01, live): "police... arrested me...
    # saying that i stole a goat" retrieved Section 303 (theft, cognizable,
    # score ~0.44) AND -- spuriously -- Section 318 (cheating, whose
    # 318(2)/(3) are non-cognizable, score ~0.36). Checking cognizability
    # across EVERY match above the 0.34 threshold made {True, False} and
    # forced conflicting_matches, so a straightforward theft question got
    # the "the law forks, here are the scenarios" treatment plus a
    # duplicate hardcoded closer from app.py's conflict branch. A genuine
    # fork (e.g. "can police arrest me for cheating" -> 318(2) no vs
    # 318(4) yes) has the competing provisions as SUBSECTIONS OF THE SAME
    # top match, both scoring high -- not a high-relevance section vs a
    # low-relevance noise match. So conflict detection now only considers
    # matches within CONFLICT_SCORE_MARGIN of the top statute match.
    state = _conflict_state(enriched)

    return {"state": state, "matches": enriched, "judgment_matches": judgment_matches}


def _cap_matches(matches, max_keep, gap=MATCH_SCORE_GAP):
    """Trim a score-ordered match list to the strongest blocks: first drop
    anything more than `gap` below the top score, then keep at most
    `max_keep`. The top match is always kept. Split out from
    find_relevant_sections so it can be unit-tested without embeddings.
    `matches` must already be sorted by descending 'score' (semantic_search
    guarantees this)."""
    if len(matches) <= 1:
        return matches
    top_score = matches[0]["score"]
    within_gap = [m for m in matches if top_score - m["score"] <= gap]
    return within_gap[:max_keep]


def _conflict_state(enriched):
    """'conflicting_matches' iff the confident, closely-ranked statute
    matches genuinely disagree on cognizability; 'single_match'
    otherwise (including the no-statute-matches case). Split out from
    find_relevant_sections so the gating can be unit-tested without
    embeddings. `enriched` is score-ordered; each item has 'score' and
    'all_variants'."""
    if not enriched:
        return "single_match"
    top_score = enriched[0]["score"]
    conflict_pool = [
        e for e in enriched
        if e["score"] >= CONFLICT_MIN_SCORE and top_score - e["score"] <= CONFLICT_SCORE_MARGIN
    ]
    all_cognizable_values = set()
    for e in conflict_pool:
        for variant_data in e["all_variants"].values():
            all_cognizable_values.add(variant_data.get("cognizable"))
    return "conflicting_matches" if len(all_cognizable_values) > 1 else "single_match"


if __name__ == "__main__":
    if not _voyage_available:
        print("voyageai not installed -- run: pip install voyageai")
    elif not os.path.exists(EMBEDDINGS_PATH):
        print(f"{EMBEDDINGS_PATH} not found -- run embed_corpus.py first (requires VOYAGE_API_KEY).")
    else:
        test_queries = [
            "Can police arrest me directly for rioting?",
            "How can I sue my neighbour for a property dispute?",
            "asdkjaslkdj random gibberish text",
        ]
        for q in test_queries:
            print(f"\n=== Query: {q!r} ===")
            result = find_relevant_sections(q)
            print(f"State: {result['state']}")
            if result["state"] in ("single_match", "conflicting_matches"):
                for m in result["matches"]:
                    print(f"  {m['section_number']} (score={m['score']:.3f}): {m['text'][:80]!r}")
                    
    