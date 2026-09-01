
"""
audit_citation_currency.py

Project 2: coverage report for citation_currency.py.

Lists every doctrine_key in retrieval.py's JUDGMENT_CITATION_MAP against
its citation_currency.py status, so the NOT_YET_VERIFIED backlog is
always visible as an explicit list, not something to lose track of --
same discipline as HANDOFF_PROJECT2.md's own "explicitly tracked open
items" section. Run this after adding any new JUDGMENT_CITATION_MAP
entry to see what currency work is now outstanding.
"""

from retrieval import JUDGMENT_CITATION_MAP
from citation_currency import get_citation_currency, NOT_YET_VERIFIED


def audit() -> dict:
    """Returns {status: [doctrine_key, ...]} for every doctrine_key
    currently in JUDGMENT_CITATION_MAP."""
    by_status = {}
    for key in sorted(JUDGMENT_CITATION_MAP.keys()):
        record = get_citation_currency(key)
        by_status.setdefault(record["status"], []).append(key)
    return by_status


if __name__ == "__main__":
    by_status = audit()
    total = sum(len(v) for v in by_status.values())

    print(f"=== Citation currency audit: {total} doctrine_key(s) in JUDGMENT_CITATION_MAP ===\n")

    for status in ["GOOD_LAW", "SUPERSEDED_BY_STATUTE", "DISTINGUISHED", "OVERRULED", NOT_YET_VERIFIED]:
        keys = by_status.get(status, [])
        if not keys:
            continue
        print(f"{status} ({len(keys)}):")
        for key in keys:
            print(f"  - {key}")
        print()

    not_verified = by_status.get(NOT_YET_VERIFIED, [])
    if not_verified:
        print(
            f"BACKLOG: {len(not_verified)} doctrine_key(s) have no curated "
            f"currency record at all -- these surface with a NOT_YET_VERIFIED "
            f"caveat in the app but have had zero verification work done."
        )

    # Second, finer backlog: entries that DO have a curated record and a
    # settled statute dimension, but whose CASE-LAW-TREATMENT dimension is
    # not yet genuinely verified. Detected from the verified_note text --
    # a verified entry says "Both dimensions checked"; an unverified or
    # inconclusive one says "not yet checked" / "ATTEMPTED" / "inconclusive"
    # / "not yet genuinely verified".
    _DONE_MARKERS = ("both dimensions checked", "both dimensions verified")
    _PENDING_MARKERS = (
        "not yet checked", "not yet genuinely verified", "attempted",
        "inconclusive", "not yet independently verified",
    )
    treatment_pending = []
    for key in sorted(k for keys in by_status.values() for k in keys):
        note = (get_citation_currency(key).get("verified_note") or "").lower()
        if any(m in note for m in _DONE_MARKERS):
            continue
        if any(m in note for m in _PENDING_MARKERS):
            treatment_pending.append(key)

    if treatment_pending:
        print(
            f"\nCASE-LAW-TREATMENT DIMENSION NOT YET VERIFIED "
            f"({len(treatment_pending)}): these have a curated record and a "
            f"settled statute dimension, but whether later courts have "
            f"carried the doctrine forward (or doubted it) has not been "
            f"confirmed against a real citing-case search + a primary-text "
            f"read. Run: python citation_currency_checker.py <doctrine_key>"
        )
        for key in treatment_pending:
            print(f"  - {key}")
