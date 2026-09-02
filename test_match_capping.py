
"""
test_match_capping.py

Unit tests for semantic_retrieval._cap_matches -- the retrieval-precision
follow-up to Phase 5 of the chat-quality plan.

WHAT THIS GUARDS: threshold filtering (0.34 statute / 0.40 judgment) lets
~18 blocks through for a typical situation question, most of them
topic-adjacent noise. _cap_matches trims each type's list to the strongest
few BEFORE enrichment / conflict detection / prompt assembly -- a relative
score-gap filter followed by an absolute cap, with the top match always
kept.

The load-bearing property: _cap_matches must never remove anything the
conflicting_matches gate would still compare (within CONFLICT_SCORE_MARGIN
0.03 of the top AND >= CONFLICT_MIN_SCORE 0.40) -- otherwise capping would
silently suppress genuine "the law forks here" answers.

Run with: python test_match_capping.py
No API cost, no embeddings needed.
"""

from semantic_retrieval import (
    _cap_matches,
    _conflict_state,
    MATCH_SCORE_GAP,
    MAX_STATUTE_MATCHES_FOR_PROMPT,
    MAX_JUDGMENT_MATCHES_FOR_PROMPT,
    CONFLICT_SCORE_MARGIN,
    CONFLICT_MIN_SCORE,
)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


def _m(score, **extra):
    return {"score": score, **extra}


def _scores(matches):
    return [round(m["score"], 4) for m in matches]


# ---- basic shape ----

check(_cap_matches([], 5) == [], "empty list -> empty list, never crashes")

only_one = [_m(0.41)]
check(_cap_matches(only_one, 5) == only_one,
      "single match -> returned unchanged (top match always kept)")

check(_cap_matches([_m(0.35)], 5) == [_m(0.35)],
      "single weak match -> still kept (nothing to compare it against)")


# ---- absolute cap ----

many_close = [_m(0.50 - 0.001 * i) for i in range(12)]  # all within the gap
capped = _cap_matches(many_close, MAX_STATUTE_MATCHES_FOR_PROMPT)
check(len(capped) == MAX_STATUTE_MATCHES_FOR_PROMPT,
      f"12 near-tied matches -> capped to MAX_STATUTE_MATCHES_FOR_PROMPT "
      f"({MAX_STATUTE_MATCHES_FOR_PROMPT})")
check(capped == many_close[:MAX_STATUTE_MATCHES_FOR_PROMPT],
      "absolute cap keeps the highest-scoring, in order")

capped_j = _cap_matches(many_close, MAX_JUDGMENT_MATCHES_FOR_PROMPT)
check(len(capped_j) == MAX_JUDGMENT_MATCHES_FOR_PROMPT,
      f"same list, judgment cap -> {MAX_JUDGMENT_MATCHES_FOR_PROMPT}")


# ---- relative score-gap filter ----

# One strong match, the rest a noise tail just above threshold.
goat_shaped = [_m(0.45), _m(0.365), _m(0.35), _m(0.342), _m(0.34)]
trimmed = _cap_matches(goat_shaped, MAX_STATUTE_MATCHES_FOR_PROMPT)
check(trimmed == [_m(0.45)],
      "REAL-SHAPED (goat theft): lone strong match at 0.45 + a 0.34-0.365 "
      "noise tail -> only the strong match survives the gap filter")

# A genuine multi-section cluster: several matches bunched near the top.
cluster = [_m(0.52), _m(0.50), _m(0.47), _m(0.30)]
kept = _cap_matches(cluster, MAX_STATUTE_MATCHES_FOR_PROMPT)
check(_scores(kept) == [0.52, 0.50, 0.47],
      "a genuine tight cluster (0.47-0.52) is kept whole; the 0.30 outlier is dropped")

# Comfortably inside the gap is kept; comfortably outside is dropped.
boundary = [_m(0.50), _m(0.50 - MATCH_SCORE_GAP + 0.01), _m(0.50 - MATCH_SCORE_GAP - 0.01)]
kept_b = _cap_matches(boundary, MAX_STATUTE_MATCHES_FOR_PROMPT)
check(_scores(kept_b) == [0.5, round(0.50 - MATCH_SCORE_GAP + 0.01, 4)],
      "match just inside MATCH_SCORE_GAP is kept; one just outside it is dropped")


# ---- the load-bearing invariant: capping never hides a real conflict ----

def _cm(score, cognizable_by_variant):
    return {
        "score": score,
        "all_variants": {
            f"v{i}": {"cognizable": c} for i, c in enumerate(cognizable_by_variant)
        },
    }


COG = [True]
NONCOG = [False]

# A genuine fork: two confident provisions within CONFLICT_SCORE_MARGIN.
fork = [_cm(0.52, COG), _cm(0.52 - CONFLICT_SCORE_MARGIN + 0.005, NONCOG)]
check(_conflict_state(fork) == "conflicting_matches",
      "sanity: the genuine-fork shape is a conflict before capping")
check(_conflict_state(_cap_matches(fork, MAX_STATUTE_MATCHES_FOR_PROMPT))
      == "conflicting_matches",
      "capping preserves a genuine fork (both provisions within the gap and the cap)")

# The widest a conflict can span (margin 0.03) is well inside the gap (0.08),
# so no in-window provision is ever gap-filtered out.
check(CONFLICT_SCORE_MARGIN < MATCH_SCORE_GAP,
      "CONFLICT_SCORE_MARGIN < MATCH_SCORE_GAP -> gap filter cannot drop a conflict peer")

# Fork buried behind a noise match that ranks first: after threshold
# filtering the conflict peers are items 0 and 1; a lone trailing noise
# match doesn't push them out of the cap.
fork_plus_noise = [_cm(0.55, COG), _cm(0.55 - CONFLICT_SCORE_MARGIN + 0.005, NONCOG),
                   _cm(0.40, COG)]
check(_conflict_state(_cap_matches(fork_plus_noise, MAX_STATUTE_MATCHES_FOR_PROMPT))
      == "conflicting_matches",
      "fork + a trailing weaker match -> still a conflict after capping")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("RESULT: ALL TESTS PASSED")
