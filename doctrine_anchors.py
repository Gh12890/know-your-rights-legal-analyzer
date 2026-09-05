"""
doctrine_anchors.py  (Fix 1, 2026-09-05)

The Lane B baseline showed that a whitelisted settled-doctrine question
does NOT reliably surface its own canonical judgment: the semantic search
ranked D.K. Basu ~#5 (below the trusted-panel floor) on a custodial-
torture question, put Shreya Singhal under the floor on a Section 66A
question, and missed Viraj Chetan Shah entirely on a Look-Out-Circular
question -- every one of those cases sitting in the corpus the whole time.

But when an issue maps to a settled-doctrine topic
(settled_doctrine_whitelist), we ALREADY know -- by hand, curated once --
which judgment(s) state that doctrine. So inject them directly as
candidates instead of hoping the reranker rediscovers them. Pure Python,
no model, no network -- the same curated-map discipline as
statute_doctrine_map.py / citation_currency.py / itact_section_status.py.

An anchored candidate still flows through the normal pipeline (paragraph
pinning, the one-sentence gloss, dedup against a fresh corpus/IK hit for
the same case). Anchoring only guarantees the canonical case is
CONSIDERED, and -- when the panel is shown (show_user) -- DISPLAYED and
ordered first. It never bypasses the verbatim-verification or the
"unverified, read it yourself" framing.
"""

from settled_doctrine_whitelist import _WHITELIST

# whitelist topic -> the corpus case_name(s) that state that doctrine, in
# the order they should appear in the panel. The strings MUST equal the
# `case_name` field of the embedded corpus records (test_doctrine_anchors
# checks every one against the live corpus).
DOCTRINE_ANCHOR_CASES = {
    "fir_copy_right": [
        "Youth Bar Association v Union of India",
    ],
    "arnesh_kumar_arrest_notice": [
        "Arnesh Kumar v State of Bihar",
        "Satender Kumar Antil v Central Bureau of Investigation (2026)",
    ],
    "grounds_of_arrest_communicated": [
        "Prabir Purkayastha v State (NCT of Delhi)",
        "Pankaj Bansal v Union of India",
        "Vihaan Kumar v State of Haryana",
    ],
    # KNOWN GAP (baseline finding #4): no corpus judgment for default bail
    # yet. Left explicit so it is obvious this is a gap, not an omission.
    "default_bail": [],
    "dk_basu_safeguards": [
        "D.K. Basu v State of West Bengal",
    ],
    "twenty_four_hour_production": [
        "Prabir Purkayastha v State (NCT of Delhi)",
        "Rakhi Mitra and Anr v State of West Bengal",
    ],
    "right_to_lawyer_on_arrest": [
        "D.K. Basu v State of West Bengal",
        "Prabir Purkayastha v State (NCT of Delhi)",
    ],
    "loc_validity_challenge": [
        "Viraj Chetan Shah v Union of India & Anr (& Connected Matters)",
    ],
    "itact_66a_struck_down": [
        "Shreya Singhal v Union of India",
    ],
}

assert set(DOCTRINE_ANCHOR_CASES) == set(_WHITELIST), (
    "DOCTRINE_ANCHOR_CASES must have an entry (possibly []) for every whitelist topic"
)

# At most this many anchor cases per topic -- keep the trusted panel from
# filling entirely with anchors and crowding out fresh judgments.
_MAX_ANCHORS_PER_TOPIC = 2


def _seed_record(case_name, _cache={}):
    """A representative embedded chunk of `case_name`, in the
    semantic-search record shape corpus_candidates builds a candidate
    'record' from. Only a SEED -- fetch_and_pin re-pools every chunk of the
    case and re-pins the best against the actual situation -- so any real
    chunk works; a substantive one is preferred over the 'preamble' header.
    Returns None if the case is not in the corpus."""
    if case_name in _cache:
        return dict(_cache[case_name]) if _cache[case_name] else None
    try:
        from semantic_retrieval import _load_corpus_embeddings
        corpus = _load_corpus_embeddings()
    except Exception:
        return None
    best = None
    for r in (corpus or {}).get("records", []):
        if r.get("type") != "judgment" or r.get("case_name") != case_name:
            continue
        if best is None:
            best = r
        elif str(best.get("paragraph_number")) == "preamble" \
                and str(r.get("paragraph_number")) != "preamble":
            best = r
    rec = None
    if best is not None:
        rec = {
            "type": "judgment",
            "chunk_id": best.get("chunk_id"),
            "case_name": case_name,
            "paragraph_number": best.get("paragraph_number"),
            "text": best.get("text") or "",
            "score": 0.0,   # the real content_score comes from fetch_and_pin
            "citation": best.get("citation") or "",
            "source_url": best.get("source_url"),
        }
    _cache[case_name] = rec
    return dict(rec) if rec else None


def anchor_candidates(coverage):
    """coverage: settled_doctrine_whitelist.coverage_report(issues).

    Returns a list of candidate dicts (the corpus-candidate shape, plus
    'doctrine_anchor' = the topic name) for the canonical judgment(s) of
    every issue that mapped to a settled-doctrine topic -- fired PER
    COVERED ISSUE, not gated on the whole question being covered (a
    partially-covered question still gets the canonical case into the
    'unverified, read it yourself' panel). [] when nothing maps or no
    mapped topic has an anchor.
    """
    if not coverage:
        return []
    by_case = {}
    for idx, pair in enumerate(coverage.get("by_issue", []) or []):
        topic = pair[1] if isinstance(pair, (list, tuple)) and len(pair) > 1 else None
        if not topic:
            continue
        for case_name in DOCTRINE_ANCHOR_CASES.get(topic, [])[:_MAX_ANCHORS_PER_TOPIC]:
            entry = by_case.get(case_name)
            if entry is None:
                rec = _seed_record(case_name)
                if rec is None:
                    continue
                entry = {
                    "source": "corpus",
                    "matched_issues": set(),
                    "queries": [],
                    "record": rec,
                    "doctrine_anchor": topic,
                }
                by_case[case_name] = entry
            entry["matched_issues"].add(idx)
    out = []
    for e in by_case.values():
        e["matched_issues"] = sorted(e["matched_issues"])
        out.append(e)
    return out


def merge_into_corpus_pool(corpus_pool, anchor_pool):
    """Fold anchor candidates into an existing corpus candidate pool,
    deduped by case name. If the pool already has the case (a fresh
    semantic hit), keep that record but tag it 'doctrine_anchor' and union
    the matched issues; otherwise append the anchor entry. Returns a new
    list; never mutates the pool's membership in place."""
    if not anchor_pool:
        return list(corpus_pool or [])

    def _name(c):
        return (c.get("record", {}).get("case_name") or "").strip().lower()

    out = list(corpus_pool or [])
    by_name = {_name(c): c for c in out if _name(c)}
    for a in anchor_pool:
        nm = _name(a)
        existing = by_name.get(nm)
        if existing is not None:
            existing["doctrine_anchor"] = a["doctrine_anchor"]
            mi = set(existing.get("matched_issues") or []) | set(a.get("matched_issues") or [])
            existing["matched_issues"] = sorted(mi)
        else:
            out.append(a)
            by_name[nm] = a
    return out
