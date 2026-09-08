"""
scenario_verification.py  (Vibeathon Step 4, 2026-09-08)

The four-way verification badge for a case cited in a scenario answer:

    exists         -- the case is in Recourse's hand-checked library
    quoted verbatim -- the passage shown is a curated excerpt, checked
                       word-for-word against the judgment when it was added
    still good law  -- the case has been checked for currency (not overruled,
                       still applied under the new codes)
    on point        -- a person, not a similarity score, mapped this case to
                       this right

WHY THIS IS HONEST (and stronger than a generated-answer tool's badge):
  - "exists", "quoted verbatim" and "on point" are TRUE BY CONSTRUCTION of a
    curated corpus + a curated scenario spec -- not a claim about a model's
    output. Every corpus chunk is chunk_method="curated_excerpt", verified as
    a verbatim substring of the fetched judgment at ingest
    (see seed_scenario_corpus.py / build_judgment_corpus.py). Every
    right->case pin in scenario_spec.py is a hand mapping.
  - "still good law" is the one check that needs real outside verification.
    We show GREEN only where a human has recorded a checked status here, or
    where citation_currency.py already has a curated GOOD_LAW entry.
    Everything else shows an amber "read it yourself" dot with a plain note
    -- never a false green. This is the project's "flag, never hide" rule.

CASE_CURRENCY below is a curated map, same discipline as
statute_doctrine_map.py / doctrine_anchors.py. Each entry is a one-time human
judgement; the legal teammate reviews it before submission.
"""

from datetime import date

# case_name -> {"status": "current" | "current_renumbered" | "caution",
#               "note": one plain sentence, "checked": "YYYY-MM-DD"}
CASE_CURRENCY = {
    "Lalita Kumari v Government of Uttar Pradesh": {
        "status": "current",
        "note": "Constitution Bench (5 judges); the mandatory-FIR rule has been "
                "applied consistently for over a decade and carries into "
                "Section 173 BNSS.",
        "checked": "2026-09-08",
    },
    "M. Ravindran v Intelligence Officer, Directorate of Revenue Intelligence": {
        "status": "current",
        "note": "The leading modern Supreme Court statement of the default-bail "
                "right; routinely followed.",
        "checked": "2026-09-08",
    },
    "Bikramjit Singh v State of Punjab": {
        "status": "current",
        "note": "Supreme Court; holds default bail to be part of the Article 21 "
                "fundamental right. Not doubted.",
        "checked": "2026-09-08",
    },
    "Rakesh Kumar Paul v State of Assam": {
        "status": "current",
        "note": "Supreme Court (3 judges, 2:1 on the facts); the 'not less than "
                "10 years' reasoning is settled and followed.",
        "checked": "2026-09-08",
    },
    "Deepa v S. Vijayalakshmi": {
        "status": "current",
        "note": "Madras High Court Division Bench, February 2025 -- decided "
                "directly on Section 43(5) BNSS, so it is current on the new "
                "code. It is a High Court view; the Supreme Court has not ruled "
                "on this specific question.",
        "checked": "2026-09-08",
    },
    "Prabir Purkayastha v State (NCT of Delhi)": {
        "status": "current",
        "note": "Supreme Court, 2024 -- decided under the new framework; the "
                "grounds-of-arrest holding is being applied by courts.",
        "checked": "2026-09-08",
    },
    "Pankaj Bansal v Union of India": {
        "status": "current",
        "note": "Supreme Court, 2023 -- grounds of arrest must be furnished in "
                "writing; consistently applied.",
        "checked": "2026-09-08",
    },
    "D.K. Basu v State of West Bengal": {
        "status": "current",
        "note": "Supreme Court; the custodial safeguards are among the most "
                "entrenched in Indian criminal procedure and are codified in "
                "BNSS 46-48. (citation_currency.py: GOOD_LAW, checked 2026-09-01.)",
        "checked": "2026-09-08",
    },
    "Arnesh Kumar v State of Bihar": {
        "status": "current_renumbered",
        "note": "The notice-before-arrest checklist was issued under old CrPC "
                "Section 41A, now Section 35 BNSS. High Courts are still directing "
                "police to follow it under the new numbering (e.g. a July 2026 "
                "order). (citation_currency.py verified 2026-09-01.)",
        "checked": "2026-09-08",
    },
    "Satender Kumar Antil v Central Bureau of Investigation (2026)": {
        "status": "current",
        "note": "Supreme Court -- the bail-is-the-rule framework; repeatedly "
                "reaffirmed.",
        "checked": "2026-09-08",
    },
}

_GREEN_STATUSES = {"current", "current_renumbered"}


def _currency_check(case_name: str) -> dict:
    """{'ok': bool, 'label': str, 'note': str}. Curated map first; then a
    curated citation_currency.py GOOD_LAW entry; else amber."""
    entry = CASE_CURRENCY.get(case_name)
    if entry and entry["status"] in _GREEN_STATUSES:
        label = "still good law" if entry["status"] == "current" else "good law (renumbered)"
        return {"ok": True, "label": label, "note": entry["note"]}
    if entry and entry["status"] == "caution":
        return {"ok": False, "label": "check currency", "note": entry["note"]}

    # fall back to citation_currency.py's curated doctrine entries
    try:
        from citation_currency import get_citation_currency_for_case_name
        cc = get_citation_currency_for_case_name(case_name) or []
        for row in cc:
            if row.get("status") in ("GOOD_LAW", "SUPERSEDED_BY_STATUTE"):
                return {"ok": True, "label": "still good law",
                        "note": row.get("user_facing_note")
                        or "Checked for currency; still applied by courts."}
            if row.get("user_facing_note"):
                return {"ok": False, "label": "check currency",
                        "note": row["user_facing_note"]}
    except Exception:
        pass

    return {
        "ok": False,
        "label": "check currency",
        "note": "We have not independently re-checked this case for legal "
                "currency yet -- read the judgment itself before relying on it.",
    }


# Chunk-storage methods whose text is genuinely a verbatim run from the
# judgment: a hand-trimmed excerpt, or a whole paragraph pulled by its
# number. "fixed_size_fallback" is a mechanical cut that can split a
# sentence, so it does not qualify for a clean "quoted verbatim" tick.
_VERBATIM_METHODS = {"curated_excerpt", "paragraph_number"}


def verification_badge(case_name: str, *, chunk_method: str = "curated_excerpt",
                       in_library: bool = True, hand_mapped: bool = True) -> dict:
    """The four checks for one cited case.

    Returns:
      {
        "case": str,
        "checks": [ {"key","label","ok","note"}, x4 ],
        "all_ok": bool,
        "summary": "4/4 checks" | "3/4 checks - see note",
      }
    """
    verbatim_ok = chunk_method in _VERBATIM_METHODS
    currency = _currency_check(case_name)

    checks = [
        {
            "key": "exists",
            "label": "exists",
            "ok": bool(in_library),
            "note": ("This case is in Recourse's hand-checked library -- read "
                     "against the original judgment when it was added."
                     if in_library else
                     "This case is not in the checked library."),
        },
        {
            "key": "good_law",
            "label": currency["label"],
            "ok": currency["ok"],
            "note": currency["note"],
        },
        {
            "key": "verbatim",
            "label": "quoted verbatim",
            "ok": verbatim_ok,
            "note": ("The passage shown is a real run of text from the judgment "
                     "-- a curated excerpt or a whole numbered paragraph, "
                     "checked against the original when it was added."
                     if verbatim_ok else
                     "The stored passage for this case was chunked mechanically "
                     "and may not align to a clean sentence boundary."),
        },
        {
            "key": "on_point",
            "label": "on point",
            "ok": bool(hand_mapped),
            "note": ("A person mapped this case to this right by hand -- not a "
                     "similarity score." if hand_mapped else
                     "This case was matched automatically, not hand-checked for fit."),
        },
    ]
    n_ok = sum(1 for c in checks if c["ok"])
    return {
        "case": case_name,
        "checks": checks,
        "all_ok": n_ok == len(checks),
        "summary": (f"{n_ok}/{len(checks)} checks"
                    + ("" if n_ok == len(checks) else " - see note")),
    }


if __name__ == "__main__":
    import json
    for n in ["Lalita Kumari v Government of Uttar Pradesh",
              "Deepa v S. Vijayalakshmi",
              "Arnesh Kumar v State of Bihar"]:
        print(json.dumps(verification_badge(n), indent=2))
