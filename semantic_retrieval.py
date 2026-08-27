
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

# CONFIRMED REAL BUG (2026-08-27): unlike embed_corpus.py, this module
# never loaded .env, so VOYAGE_API_KEY never reached os.environ when this
# script (or anything importing it) ran standalone. voyageai.Client()
# then silently constructed with no key, every embed() call failed, and
# semantic_search's blanket "except Exception: return None" swallowed
# the real error -- producing a confusing "unavailable" state on every
# single query with no indication of why. Confirmed directly: the exact
# same API call succeeded when .env was loaded manually, and failed
# (returned None) when going through this module unmodified.
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
EMBEDDINGS_PATH = "embeddings/corpus_embeddings.json"

# Similarity threshold below which a match is NOT trusted -- confirmed
# starting point only, not empirically tuned yet (would need real query
# examples run against real embeddings to calibrate properly; this is a
# reasonable, conservative default per Voyage's own documented guidance
# that dot-product/cosine scores above ~0.75 generally indicate strong
# topical relevance for their models, with real variance by domain).
# MUST be revisited once real usage data exists -- do not treat 0.75 as
# validated, only as a safe starting point that errs toward "Cannot
# Determine" rather than a false-confident match.
SIMILARITY_THRESHOLD = 0.40
#Threshold level put at 0.40 down from 0.75. 1 means identical , pointing in same direction. 

# If multiple matches clear the threshold but disagree on a key legal
# attribute (e.g. different cognizable/bailable status for statute
# matches), surface that conflict explicitly rather than picking the
# top-ranked one. This gap defines "materially different" for the
# purposes of flagging a conflict.


# CALIBRATED AGAIN 2026-08-27: raised from 5 to 10 after a confirmed real
# failure. Question: "can police arrest directly for cheating?" -- the
# actual answering section (BNS 318, the cheating definition) ranked 6th
# at score 0.405, just above SIMILARITY_THRESHOLD, but outside the old
# top_k=5 window. It was therefore NEVER passed to the response
# generator, which correctly (and honestly) said it didn't have enough
# information -- but that honesty was a symptom of a retrieval-window
# bug, not a genuine corpus gap. Verified the wider window is safe: all
# 10 results for this query scored in a tight 0.38-0.43 cluster, every
# one genuinely topically relevant (arrest procedure and cheating
# sections), no noise introduced by widening.
TOP_MATCHES_TO_CONSIDER = 10

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


def find_relevant_sections(query):
    """Higher-level function for BOTH statute and judgment lookup: returns
    a dict describing what was found, in one of four honest states --
    'no_match' (nothing cleared SIMILARITY_THRESHOLD), 'single_match'
    (exactly one section family cleared the threshold and they agree),
    'conflicting_matches' (multiple STATUTE sections cleared the
    threshold with DIFFERENT cognizable/bailable status -- the "rioting"
    case), or 'unavailable' (embeddings aren't set up at all). Never
    silently picks one match to hide a conflict.

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

    statute_matches = [r for r in results if r["type"] == "statute" and r["score"] >= SIMILARITY_THRESHOLD]
    judgment_matches = [r for r in results if r["type"] == "judgment" and r["score"] >= SIMILARITY_THRESHOLD]

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
    all_cognizable_values = set()
    for e in enriched:
        for variant_data in e["all_variants"].values():
            all_cognizable_values.add(variant_data.get("cognizable"))

    state = "conflicting_matches" if len(all_cognizable_values) > 1 else "single_match"

    # If there are no statute matches at all (only judgments), there's
    # nothing to conflict-check -- still a genuine single_match state,
    # just with an empty "matches" list and judgment_matches carrying
    # the real content.
    if not enriched:
        state = "single_match"

    return {"state": state, "matches": enriched, "judgment_matches": judgment_matches}


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
                    
    