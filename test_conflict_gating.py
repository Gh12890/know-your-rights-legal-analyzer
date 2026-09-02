
"""
test_conflict_gating.py

Unit tests for semantic_retrieval._conflict_state -- Phase 5 of the
chat-quality plan.

CONFIRMED REAL FAILURE this guards against (2026-09-01, live): "police
came to my house and arrested me directly saying that i stole a goat"
retrieved Section 303 (theft, cognizable) at a weak ~0.44 AND -- as a
low-relevance noise match -- a cheating section whose subsections are
non-cognizable at ~0.36. The old check scanned cognizability across
EVERY match over the 0.34 retrieval threshold, saw {True, False}, and
forced 'conflicting_matches' -- so a plain theft question got the "the
law forks, here are the scenarios" treatment plus a duplicate hardcoded
closer from app.py's conflict branch.

_conflict_state now only compares matches that are BOTH confident
(>= CONFLICT_MIN_SCORE) AND within CONFLICT_SCORE_MARGIN of the top
statute match -- the shape a genuine fork actually has.

Run with: python test_conflict_gating.py
No API cost, no embeddings needed.
"""

from semantic_retrieval import _conflict_state, CONFLICT_MIN_SCORE, CONFLICT_SCORE_MARGIN

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


def _m(score, cognizable_by_variant):
    """A minimal enriched-match stand-in: just the two fields
    _conflict_state reads."""
    return {
        "score": score,
        "all_variants": {
            f"v{i}": {"cognizable": c} for i, c in enumerate(cognizable_by_variant)
        },
    }


COG = [True]
NONCOG = [False]
FORK = [False, True]  # a single section whose subsections disagree


check(_conflict_state([]) == "single_match",
      "no statute matches at all -> single_match, never crashes")

check(_conflict_state([_m(0.55, COG)]) == "single_match",
      "one confident match, no disagreement -> single_match")

# The goat case: strong-ish theft match + a low-relevance cheating noise match.
check(
    _conflict_state([_m(0.44, COG), _m(0.36, NONCOG)]) == "single_match",
    "REAL-SHAPED: cognizable top match + a non-cognizable NOISE match far below it "
    "-> single_match (the noise match is outside the conflict window)",
)

# Genuine fork: the competing provisions score high and close together
# (typically subsections of the same section).
check(
    _conflict_state([_m(0.52, FORK)]) == "conflicting_matches",
    "a single high-scoring section whose own subsections disagree -> conflicting_matches",
)
check(
    _conflict_state([_m(0.52, COG), _m(0.50, NONCOG)]) == "conflicting_matches",
    "two confident matches within the score margin that disagree -> conflicting_matches",
)

# Disagreement exists but the second provision is not confident enough.
check(
    _conflict_state([_m(CONFLICT_MIN_SCORE - 0.01, COG),
                     _m(CONFLICT_MIN_SCORE - 0.02, NONCOG)]) == "single_match",
    "both matches below CONFLICT_MIN_SCORE -> single_match even though they disagree",
)

# Disagreement, both confident, but too far apart in rank.
check(
    _conflict_state([_m(0.60, COG), _m(0.60 - CONFLICT_SCORE_MARGIN - 0.01, NONCOG)])
    == "single_match",
    "second match confident but outside CONFLICT_SCORE_MARGIN -> single_match",
)

# Just inside the margin: still compared.
check(
    _conflict_state([_m(0.60, COG), _m(0.60 - CONFLICT_SCORE_MARGIN + 0.005, NONCOG)])
    == "conflicting_matches",
    "second match just inside CONFLICT_SCORE_MARGIN of the top is still compared",
)


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("RESULT: ALL TESTS PASSED")
