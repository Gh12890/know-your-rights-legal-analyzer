
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

    superseded = by_status.get("SUPERSEDED_BY_STATUTE", [])
    unconfirmed_treatment = [
        k for k in superseded
        if "NOT YET INDEPENDENTLY VERIFIED" in (get_citation_currency(k).get("successor_treatment") or "")
    ]
    if unconfirmed_treatment:
        print(
            f"\nSTATUTE-MAPPING DONE, CASE-LAW TREATMENT NOT YET CHECKED "
            f"({len(unconfirmed_treatment)}): renumbering is confirmed for "
            f"these, but whether courts have actually carried the doctrine "
            f"forward under the new section has not been verified via a "
            f"real citing-case search (only tapas_d_neogy_bank_account_as_"
            f"property has had that done so far):"
        )
        for key in unconfirmed_treatment:
            print(f"  - {key}")
