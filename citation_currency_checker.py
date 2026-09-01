
"""
citation_currency_checker.py

Project 2, Step 3: the ORCHESTRATOR that turns "somebody should check
whether this citation is still good law" into a structured, repeatable
evidence-gathering run -- instead of a human remembering to do it by
hand, the way tapas_d_neogy_bank_account_as_property and
arnesh_kumar_checklist were done on 2026-09-01.

WHERE THIS SITS IN THE PIPELINE (do not blur these):
  Step 1  indiankanoon_client.py   -- authenticated HTTP transport only
  Step 2  ik_query_builder.py      -- deterministic query construction
  Step 3  THIS FILE                -- run the searches, triage the hits,
                                      write a REVIEW BUNDLE
  Step 4  a human                  -- reads the bundle, reads the real
                                      judgments it points at, and writes
                                      the curated CITATION_CURRENCY_MAP
                                      entry by hand

THE NON-NEGOTIABLE PRINCIPLE, APPLIED HERE:
Nothing in this file decides whether a case is still good law. It cannot
and must not. "Has a later binding court overruled this holding" is a
legal judgment that only a human reading the actual later judgment can
make -- exactly the bar CITATION_CURRENCY_MAP's own docstring sets. What
this file does is strictly narrower and genuinely mechanical:
  - run the Step 2 queries for a doctrine we already trust
  - pool and de-duplicate the candidate citing judgments
  - attach DETERMINISTIC triage flags to each candidate (is this the
    source case itself? is it dated after the 1 July 2024 three-code
    commencement? which court tier? does its snippet contain any of a
    fixed set of adverse-treatment phrases?)
  - write all of that to citation_currency_review/<doctrine_key>.json
    for a human to act on

The adverse-treatment phrase scan is a FLAG FOR A HUMAN TO READ, never a
verdict. A hit with "distinguished" in its snippet might be
distinguishing some other case entirely; a genuine overruling might use
none of the fixed phrases. The scan's only job is to make sure an
obvious adverse signal is never silently buried in result position 14.

WHAT THIS FILE DELIBERATELY DOES NOT DO:
  - fetch full judgment text (Rs 0.20/call). The bundle hands a human
    the tids and URLs; they pull the ones whose snippets look
    load-bearing. An opt-in enrichment hook (enrich_fn) exists for the
    cheap Rs 0.02 metainfo call, off by default.
  - write CITATION_CURRENCY_MAP. Ever. That is Step 4, by hand.
  - call any LLM.
  - touch the statute-supersession dimension. That one is already
    handled well by hand via retrieval.get_statute_section(); the
    IPC<->BNS concordance integration that would let it be automated is
    a separate, still-deferred item (see ik_query_builder.py's header).

COST: every gather_treatment_evidence() call with a real search_fn spends
real money -- one IK search per query variant per doctrine_key (usually
1-2). Run it deliberately, per doctrine_key, not in a loop over the whole
map without thinking. The mocked test suite
(test_citation_currency_checker.py) exercises every code path here at
zero cost.
"""

import json
import logging
import os
import re
from datetime import date, datetime, timezone

logger = logging.getLogger("citation_currency_checker")


# All three 2023 codes (BNS, BNSS, BSA) were brought into force on this
# date by S.O. 1749(E)/1750(E)/1767(E). A citing judgment dated on or
# after this is positive evidence that a court is still applying the
# doctrine in the post-overhaul regime -- the single most useful signal
# for the case-law-treatment dimension. Before this date tells us
# nothing either way about post-overhaul currency (but an OVERRULING at
# any date still matters -- that is why the date filter is a triage
# flag, not a search-query filter that would hide older adverse cases).
THREE_CODE_COMMENCEMENT = date(2024, 7, 1)


# Lowercased substrings. A match means "a human must read this hit
# before trusting the doctrine", NOT "this doctrine is bad law". Kept
# deliberately short and high-precision -- every phrase here is one that
# appellate courts actually use when rejecting or narrowing a precedent.
# Substrings (not word-boundary regexes) so "overrule"/"overruled"/
# "overruling" all match on "overrul".
ADVERSE_TREATMENT_MARKERS = (
    "overrul",
    "per incuriam",
    "no longer good law",
    "not good law",
    "does not lay down the correct",
    "does not lay down good law",
    "bad law",
    "distinguish",
    "doubted",
    "larger bench",
)


class DoctrineKeyNotFoundError(Exception):
    """The doctrine_key is not in retrieval.JUDGMENT_CITATION_MAP.
    Fail loudly -- this checker only runs for doctrines the project
    already curates, never for an arbitrary string."""


class MissingCaseMetadataError(Exception):
    """The doctrine_key resolves to a case_key that has no entry in
    ik_query_builder.CASE_METADATA, so no search query can be built.
    Fail loudly with the exact case_key to add, rather than guessing a
    query from the internal slug."""


def _resolve_case_key(doctrine_key: str) -> str:
    """doctrine_key -> case_key, via the SAME map retrieval.py and
    citation_currency.py key off. Raises DoctrineKeyNotFoundError for an
    unknown key -- never returns a guess."""
    from retrieval import JUDGMENT_CITATION_MAP

    entry = JUDGMENT_CITATION_MAP.get(doctrine_key)
    if entry is None:
        raise DoctrineKeyNotFoundError(
            f"'{doctrine_key}' is not in retrieval.JUDGMENT_CITATION_MAP. "
            f"Known doctrine_keys: {sorted(JUDGMENT_CITATION_MAP.keys())}"
        )
    return entry["case_key"]


def _parse_ik_date(raw):
    """IK's search results carry publishdate as an ISO 'YYYY-MM-DD'
    string (unverified against a live response as of 2026-09-01 -- the
    indiankanoon_client.search docstring only promises 'tid' and
    'title'). Handles ISO first, then a couple of common Indian
    day-first formats, then gives up and returns None. NEVER raises and
    NEVER guesses a date -- an unparseable date becomes None, which the
    triage logic treats as 'unknown', not as 'old'."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d %B %Y", "%d %B, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    logger.info("citation_currency_checker: could not parse IK date %r", raw)
    return None


def _classify_court_tier(docsource):
    """Best-effort court-tier label from IK's 'docsource' field (e.g.
    'Supreme Court of India', 'Bombay High Court', 'Delhi District
    Court'). Returns 'supreme_court', 'high_court', 'other', or
    'unknown' when the field is absent. This is a convenience label for
    a human skimming the bundle, not a load-bearing filter."""
    if not docsource or not isinstance(docsource, str):
        return "unknown"
    low = docsource.lower()
    if "supreme court" in low:
        return "supreme_court"
    if "high court" in low:
        return "high_court"
    return "other"


def _strip_html(text):
    """IK's search results embed <b>...</b> highlight tags (and HTML
    entities) in the title and snippet fields. Strip tags and unescape
    entities so downstream text handling sees plain text. Not an
    HTML-structure parse -- a flat tag strip is all that's needed for
    these one-line fragments."""
    if not text or not isinstance(text, str):
        return ""
    import html as _html

    return _html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _normalise_title(text):
    """Lowercase, strip HTML, strip punctuation, collapse whitespace,
    and drop the trailing ' on <date>' that IK appends to search-result
    titles ('Arnesh Kumar vs State Of Bihar on 2 July, 2014'). Used only
    for the fuzzy source-case match -- deliberately lossy."""
    if not text:
        return ""
    text = _strip_html(text)
    text = re.sub(r"\bon\s+\d{1,2}\s+\w+,?\s+\d{4}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    text = re.sub(r"\bvs?\b|\bversus\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_source_case(candidate_title, candidate_year, source_meta):
    """True only when a search hit IS (very likely) the source judgment
    itself, not a judgment that merely names it.

    Two clauses, both required:
      1. the normalised candidate title STARTS WITH the full normalised
         source case name (a citing judgment's IK-derived title reads
         '13. In Rangappa vs Sri Mohan (2010) 11 SCC 441 ...' -- it does
         not start with the case name);
      2. the candidate's publication year equals the source case's known
         year from CASE_METADATA. If the candidate has no parseable
         year, this clause fails closed -> not flagged as the source.

    Clause 2 is what the first live run (2026-09-01, rangappa) proved
    necessary: several Delhi District Court judgments from 2018-2023
    carry titles that begin 'Rangappa vs Sri Mohan Reported In ...' yet
    are obviously not the 2010 Supreme Court source case. Without the
    year check, clause 1 alone still mislabelled them.

    Source-case hits are KEPT in the bundle (finding the real source
    is a useful sanity signal) but excluded from the citing count."""
    src_norm = _normalise_title(source_meta.get("case_name", ""))
    if not src_norm:
        return False
    if not _normalise_title(candidate_title).startswith(src_norm):
        return False
    source_year = source_meta.get("year")
    if source_year is None:
        return False
    return candidate_year == source_year


def _snippet_of(doc):
    """The best available human-readable snippet from an IK search hit,
    across the field names IK has used ('headline', 'fragment',
    'doc'). Returns '' if none is present."""
    for field in ("headline", "fragment", "doc", "snippet"):
        val = doc.get(field)
        if val and isinstance(val, str):
            return _strip_html(val)
    return ""


def _find_adverse_markers(*texts):
    """Sorted list of ADVERSE_TREATMENT_MARKERS that appear (as a
    plain lowercased substring) anywhere in the given texts. Empty list
    is the common, reassuring case."""
    haystack = " ".join(t.lower() for t in texts if t)
    return sorted(m for m in ADVERSE_TREATMENT_MARKERS if m in haystack)


def _triage_candidate(doc, source_meta, today):
    """Attach the deterministic triage flags to one raw IK search hit.
    Pure function of the hit plus the source case's CASE_METADATA plus
    'today' -- no network, no judgment. Every 'is it X' flag is True /
    False / None, where None means 'the data needed to decide is
    missing', never a guess."""
    tid = doc.get("tid")
    title = _strip_html(doc.get("title") or doc.get("doc_title") or "")
    pub_date = _parse_ik_date(doc.get("publishdate") or doc.get("date"))
    snippet = _snippet_of(doc)

    if pub_date is None:
        post_commencement = None
    else:
        post_commencement = pub_date >= THREE_CODE_COMMENCEMENT

    return {
        "tid": tid,
        "title": title,
        "url": f"https://indiankanoon.org/doc/{tid}/" if tid else None,
        "court": doc.get("docsource"),
        "court_tier": _classify_court_tier(doc.get("docsource")),
        "publish_date": pub_date.isoformat() if pub_date else None,
        "is_source_case": _looks_like_source_case(
            title, pub_date.year if pub_date else None, source_meta
        ),
        "post_three_code_commencement": post_commencement,
        "adverse_treatment_markers": _find_adverse_markers(title, snippet),
        "snippet": snippet[:600],
    }


def gather_treatment_evidence(
    doctrine_key,
    *,
    max_results_per_query=20,
    search_fn=None,
    enrich_fn=None,
    today=None,
):
    """Run a full case-law-treatment discovery pass for one doctrine_key
    and return a REVIEW BUNDLE dict (see write_review_bundle for the
    on-disk form).

    doctrine_key: a key of retrieval.JUDGMENT_CITATION_MAP.

    search_fn: callable(query:str, page_num:int)->dict, matching
        indiankanoon_client.search. Injected so the test suite can run
        every path here for free. Defaults to the real (paid) client.

    enrich_fn: optional callable(tid:str)->dict for the cheap Rs 0.02
        metainfo call, used to backfill court/date on hits whose search
        record lacked them. Off by default -- pass
        indiankanoon_client.get_document_metainfo to enable.

    today: date, defaults to date.today(). Injected for deterministic
        tests of the post-commencement flag.

    Raises DoctrineKeyNotFoundError / MissingCaseMetadataError before
    spending any API call.
    """
    from ik_query_builder import CASE_METADATA, build_doctrine_queries, UnknownCaseKeyError

    today = today or date.today()
    case_key = _resolve_case_key(doctrine_key)

    if case_key not in CASE_METADATA:
        raise MissingCaseMetadataError(
            f"doctrine_key '{doctrine_key}' resolves to case_key "
            f"'{case_key}', which has no entry in "
            f"ik_query_builder.CASE_METADATA. Add a verified entry there "
            f"(real case name + citation, checked against the corpus JSON, "
            f"not guessed) before running the checker for this doctrine."
        )

    if search_fn is None:
        from indiankanoon_client import search as search_fn

    metadata = CASE_METADATA[case_key]
    source_case_name = metadata["case_name"]
    source_meta = {"case_name": source_case_name, "year": metadata.get("year")}

    try:
        queries = build_doctrine_queries(case_key)
    except UnknownCaseKeyError as exc:  # pragma: no cover - guarded above
        raise MissingCaseMetadataError(str(exc)) from exc

    seen_tids = set()
    candidates = []
    queries_run = []

    for query in queries:
        raw = search_fn(query, 0)
        docs = raw.get("docs", []) if isinstance(raw, dict) else []
        queries_run.append({
            "query": query,
            "found": raw.get("found") if isinstance(raw, dict) else None,
            "docs_returned": len(docs),
        })
        for doc in docs[:max_results_per_query]:
            tid = doc.get("tid")
            if tid is not None and tid in seen_tids:
                continue
            if tid is not None:
                seen_tids.add(tid)

            if enrich_fn is not None and not (doc.get("publishdate") and doc.get("docsource")):
                try:
                    meta = enrich_fn(tid)
                    doc = {**meta, **{k: v for k, v in doc.items() if v}}
                except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
                    logger.info("enrich_fn failed for tid=%s: %s", tid, exc)

            candidates.append(_triage_candidate(doc, source_meta, today))

    citing = [c for c in candidates if not c["is_source_case"]]
    post_commencement = [c for c in citing if c["post_three_code_commencement"] is True]
    with_adverse = [c for c in citing if c["adverse_treatment_markers"]]
    source_hits = [c for c in candidates if c["is_source_case"]]

    summary = (
        f"{len(citing)} candidate citing judgment(s) found "
        f"({len(post_commencement)} dated on/after the 1 July 2024 three-code "
        f"commencement, {len(with_adverse)} with adverse-treatment language in "
        f"the snippet). Source case {'appeared' if source_hits else 'did NOT appear'} "
        f"in the results. A HUMAN must now read the flagged judgments and write "
        f"the CITATION_CURRENCY_MAP entry -- this bundle decides nothing."
    )

    return {
        "doctrine_key": doctrine_key,
        "case_key": case_key,
        "source_case_name": source_case_name,
        "source_citation": metadata.get("citation"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "today": today.isoformat(),
        "queries_run": queries_run,
        "counts": {
            "candidates_total": len(candidates),
            "citing_candidates": len(citing),
            "post_commencement": len(post_commencement),
            "with_adverse_markers": len(with_adverse),
            "source_case_hits": len(source_hits),
        },
        "summary": summary,
        "candidates": candidates,
        "disclaimer": (
            "Evidence only. No field in this bundle is a determination "
            "that the doctrine is or is not good law. adverse_treatment_"
            "markers is a keyword flag for human review, not a verdict."
        ),
    }


def write_review_bundle(bundle, out_dir="citation_currency_review"):
    """Write a bundle from gather_treatment_evidence to
    <out_dir>/<doctrine_key>.json and return the path. Overwrites any
    previous bundle for the same doctrine_key -- a re-run is meant to
    replace, not accumulate."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{bundle['doctrine_key']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, ensure_ascii=False)
    logger.info("wrote review bundle: %s", path)
    return path


def _print_bundle(bundle):
    print(f"\n=== {bundle['doctrine_key']}  ({bundle['source_case_name']}) ===")
    print(bundle["summary"])
    for cand in bundle["candidates"]:
        tags = []
        if cand["is_source_case"]:
            tags.append("SOURCE CASE")
        if cand["post_three_code_commencement"] is True:
            tags.append("post-1-Jul-2024")
        elif cand["post_three_code_commencement"] is None:
            tags.append("date-unknown")
        if cand["adverse_treatment_markers"]:
            tags.append("ADVERSE: " + ", ".join(cand["adverse_treatment_markers"]))
        tag_str = f"  [{' | '.join(tags)}]" if tags else ""
        print(f"  - {cand['court_tier']:>13}  {cand['publish_date'] or '????-??-??'}  "
              f"{(cand['title'] or '')[:70]}{tag_str}")
        print(f"      {cand['url']}")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Gather case-law-treatment evidence for a doctrine_key (REAL Indian Kanoon calls -- costs money).",
    )
    parser.add_argument("doctrine_key", nargs="?", help="a key of retrieval.JUDGMENT_CITATION_MAP")
    parser.add_argument("--all", action="store_true", help="run for every doctrine_key (spends one+ IK search per key)")
    parser.add_argument("--enrich", action="store_true", help="also make the cheap metainfo call to backfill court/date")
    parser.add_argument("--out-dir", default="citation_currency_review")
    args = parser.parse_args()

    if not args.doctrine_key and not args.all:
        parser.error("give a doctrine_key or --all")

    from retrieval import JUDGMENT_CITATION_MAP

    enrich_fn = None
    if args.enrich:
        from indiankanoon_client import get_document_metainfo as enrich_fn

    keys = sorted(JUDGMENT_CITATION_MAP.keys()) if args.all else [args.doctrine_key]
    for key in keys:
        try:
            bundle = gather_treatment_evidence(key, enrich_fn=enrich_fn)
        except (DoctrineKeyNotFoundError, MissingCaseMetadataError) as exc:
            print(f"\n=== {key} ===\n  SKIPPED: {exc}")
            continue
        path = write_review_bundle(bundle, out_dir=args.out_dir)
        _print_bundle(bundle)
        print(f"  -> {path}")
