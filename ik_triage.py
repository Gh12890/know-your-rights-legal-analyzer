"""
ik_triage.py

Deterministic, no-network helpers for turning a raw Indian Kanoon search
hit into triage flags a human (or a later ranking step) can act on.

WHY THIS EXISTS: citation_currency_checker.py grew a good set of these
(court-tier labelling, IK date parsing, adverse-treatment keyword scan,
HTML strip) as module-private `_` functions. related_judgments.py (Lane B
of the chat) needs the same primitives. Rather than reach into another
module's private API, the shared, provider-shaped logic lives here.

NON-NEGOTIABLE, same as everywhere else in this project: nothing here is a
verdict. `adverse_markers` is a keyword flag FOR A HUMAN, never "this case
is bad law". `court_tier` is a label, not a filter. A missing/unparseable
field becomes None ("could not determine"), never a guess.

citation_currency_checker.py keeps its own copies for now (it is heavily
tested and stable); pointing it here is a separate, optional cleanup.
"""

import html as _html
import logging
import re
from datetime import date, datetime

logger = logging.getLogger("ik_triage")


# All three 2023 codes (BNS, BNSS, BSA) commenced on this date
# (S.O. 1749(E)/1750(E)/1767(E)). A citing judgment on/after it is
# positive evidence a court is applying a doctrine in the post-overhaul
# regime. Before it says nothing either way -- so this is a triage flag,
# never a search filter that would hide older adverse cases.
THREE_CODE_COMMENCEMENT = date(2024, 7, 1)


# Lowercased substrings appellate courts actually use when rejecting or
# narrowing a precedent. A match means "a human must read this hit before
# relying on it", NOT "this case is bad law" -- a hit saying "distinguished
# in Foo" might be distinguishing something else entirely, and a real
# overruling might use none of these. Substrings (not word boundaries) so
# "overrule"/"overruled"/"overruling" all catch on "overrul".
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
    "set aside",
    "reversed",
    "stayed by",
)


def parse_ik_date(raw):
    """IK carries publish dates as an ISO 'YYYY-MM-DD' string in most
    responses; some records use Indian day-first forms. Try ISO first,
    then a few day-first formats, then give up with None. NEVER raises,
    NEVER guesses -- an unparseable date is None, which downstream treats
    as 'unknown', not 'old'."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d %B %Y", "%d %B, %Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    logger.info("ik_triage: could not parse IK date %r", raw)
    return None


def classify_court_tier(docsource):
    """Best-effort tier label from IK's 'docsource' ('Supreme Court of
    India', 'Bombay High Court', 'Delhi District Court', ...). Returns
    'supreme_court' | 'high_court' | 'other' | 'unknown'. A label for
    ranking and for a human skimming, not a load-bearing filter."""
    if not docsource or not isinstance(docsource, str):
        return "unknown"
    low = docsource.lower()
    if "supreme court" in low:
        return "supreme_court"
    if "high court" in low:
        return "high_court"
    return "other"


_COURT_TIER_RANK = {"supreme_court": 3, "high_court": 2, "other": 1, "unknown": 0}


def court_tier_rank(tier):
    """Numeric weight for a tier label, for deterministic ranking."""
    return _COURT_TIER_RANK.get(tier, 0)


def strip_html(text):
    """Flat tag strip + entity unescape for IK's one-line title/snippet
    fragments (which embed <b>...</b> highlight tags). Not a structural
    HTML parse -- ik_text_cleaner does that for full documents."""
    if not text or not isinstance(text, str):
        return ""
    return _html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def normalise_title(text):
    """Lowercase, strip HTML + punctuation, drop 'vs'/'versus' and the
    trailing ' on <date>' IK appends to search-result titles. Deliberately
    lossy -- for fuzzy title matching only."""
    if not text:
        return ""
    text = strip_html(text)
    text = re.sub(r"\bon\s+\d{1,2}\s+\w+,?\s+\d{4}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    text = re.sub(r"\bvs?\b|\bversus\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def snippet_of(doc):
    """The best available human-readable fragment from an IK search hit,
    across the field names IK has used. '' if none is present."""
    if not isinstance(doc, dict):
        return ""
    for field in ("headline", "fragment", "doc", "snippet"):
        val = doc.get(field)
        if val and isinstance(val, str):
            return strip_html(val)
    return ""


def find_adverse_markers(*texts):
    """Sorted list of ADVERSE_TREATMENT_MARKERS appearing (as a plain
    lowercased substring) in any of `texts`. Empty is the common,
    reassuring case."""
    haystack = " ".join(t.lower() for t in texts if t)
    return sorted(m for m in ADVERSE_TREATMENT_MARKERS if m in haystack)


# ---------------------------------------------------------------------------
# Document-finality classification (2026-09-04) -- CONFIRMED REAL FAILURE:
# "Attapuram Bharath Reddy vs The State Of Telangana" was surfaced by Lane
# B, ranked, and USER-CONFIRMED into related_judgments_approved.json (which
# feeds drafted legal representations as an "authority") -- but its only
# pinned paragraph was a 'PetArg' (petitioner's argument) begging "the
# petitioner be enlarged on bail". It is a bail application, not a
# judgment/finding of any court. This is the deterministic Stage-C gate
# from the reviewed IK-filtering design doc, refined against what this
# project actually has available (see live-judgment-retrieval-plan memory
# for the full critique):
#
# WHY NOT A DOCTYPE OR TITLE FILTER: confirmed empirically, not assumed.
#   - IK's `doctypes:` operator (see ik_query_builder.py) is a COURT-SOURCE
#     filter ("highcourts"/"supremecourt"), not a finality filter -- a bail
#     order from a High Court is still "judgments"-doctype.
#   - Attapuram's real title, "...vs The State Of Telangana on 25 March,
#     2026", carried NO bail/interlocutory keyword at all. The only tell
#     was in the fetched paragraph body.
#   - A body-text regex for "I.A. No. <n>" was tried and REJECTED: it
#     false-positived on NALSA v Union of India (a landmark, genuinely
#     final SC judgment) at paragraph 7 -- "Shri T. Srinivasa Murthy,
#     learned counsel appearing in I.A. No. 2 of 2013, submitted that..."
#     is identifying which intervener's counsel spoke, not the whole
#     judgment's own disposal. A passing citation-number mention is not
#     document identity.
#
# WHY THE CONJUNCTION (structure absence AND disposal phrase), not either
# alone: PROCEDURAL_DISPOSAL_MARKERS phrases were validated against every
# chunk in the 22-case gold corpus (all bare "bail"/"released on bail"
# style phrases dropped after "released on bail" false-positived on
# Vihaan Kumar v State of Haryana para 9 -- QUOTING Article 22/CrPC S.41's
# own text about the RIGHT to be released on bail, not a court granting
# it) -- the phrases below scored ZERO hits across the whole corpus, but a
# phrase alone still can't distinguish "this document's own operative
# order is a bail grant" from "this document discusses bail as a legal
# topic" (Arnesh Kumar's entire subject IS arrest/bail guidelines). The
# reasoning-structure check is the other half: a genuine judgment on a
# point of law -- even one that discusses bail throughout, like Arnesh
# Kumar -- has real Analysis/Precedent/CDiscource/Issue/Conclusion
# structure somewhere; a bare procedural disposal typically does not.
# Flagging requires BOTH signals to agree, so neither alone can trigger a
# false positive on real precedent.
#
# NOT YET LIVE-VALIDATED: built and unit-tested against real corpus text
# (the negative controls) and the real, verbatim Attapuram paragraph (the
# positive control) -- but not yet run against a fresh live IK fetch,
# since Attapuram itself was already removed rather than re-fetched (this
# project's own discipline: don't spend real IK credits to re-confirm an
# already-established finding). Treat as a well-founded heuristic pending
# confirmation on the next real "unverified" run, not a proven-in-
# production filter.
# ---------------------------------------------------------------------------

# Mirrors related_judgments._STRUCTURE_BONUS's keys -- kept as an
# independent copy (not imported) since related_judgments.py imports FROM
# this module, not the other way around; see that dict if the two ever
# need to be kept in sync after a change.
REASONING_STRUCTURE_TAGS = frozenset({"Analysis", "Precedent", "CDiscource", "Issue", "Conclusion"})

# Dispositive-shaped phrasing only -- the court's own operative order or a
# party's prayer FOR that specific order, never a bare mention of "bail"
# as a legal concept (which a genuine arrest/bail-doctrine judgment like
# Arnesh Kumar uses throughout). Every phrase here was checked against the
# full 22-case gold corpus (chunks/*.json, judgment files only) and
# produced ZERO matches -- see the module-level note above for the two
# real false positives (Vihaan Kumar, NALSA) that shaped this list.
PROCEDURAL_DISPOSAL_MARKERS = (
    "is enlarged on bail",
    "be enlarged on bail",
    "the bail application is allowed",
    "the bail application is dismissed",
    "the bail application is rejected",
    "bail application stands allowed",
    "bail application stands dismissed",
    "the anticipatory bail application",
    "anticipatory bail is allowed",
    "anticipatory bail is rejected",
    "anticipatory bail is granted",
    "anticipatory bail is dismissed",
    "the interlocutory application is allowed",
    "the interlocutory application is dismissed",
    "the present bail application",
    "this bail application",
    "this criminal miscellaneous petition",
    "the criminal miscellaneous petition",
    "petitioner is granted bail",
    "petitioner is released on bail",
    "petitioner shall be released on bail",
    "accused is released on bail",
    "accused is granted bail",
    "bail petition is disposed of",
    "bail application is disposed of",
    "prayed that the petitioner be enlarged on bail",
    "prayed that the petitioner be released on bail",
)


def find_procedural_disposal_markers(*texts):
    """Sorted list of PROCEDURAL_DISPOSAL_MARKERS appearing (as a plain
    lowercased substring) in any of `texts`. Same shape as
    find_adverse_markers -- a flag, checked in combination with structure
    data by classify_document_finality, never treated as a verdict by
    itself.

    CONFIRMED REAL BUG, caught by this function's own test against the
    real Attapuram paragraph text: a fetched judgment paragraph's raw text
    carries mid-SENTENCE double-newlines from PDF extraction (confirmed
    real: "...it is prayed that the\\n\\npetitioner be enlarged on
    bail."), so a multi-word marker phrase never appears as a plain
    contiguous substring in the raw text even though it plainly reads that
    way to a human. Whitespace (any run, including newlines) is collapsed
    to a single space before matching -- find_adverse_markers does not
    need this (it runs on IK's own short single-line snippets, which don't
    carry this artifact), but a full fetched paragraph does."""
    haystack = " ".join(re.sub(r"\s+", " ", t).lower() for t in texts if t)
    return sorted(m for m in PROCEDURAL_DISPOSAL_MARKERS if m in haystack)


def classify_document_finality(paragraphs):
    """Deterministic Stage-C signal: is this fetched document LIKELY a
    bare procedural disposal (bail / interlocutory application) rather
    than a judgment with real legal reasoning?

    paragraphs: the full list of paragraph dicts for ONE fetched IK
    document (each with at least 'text' and optionally 'structure') --
    e.g. related_judgments.fetch_and_pin's `pools[idx]`, the FULL pool
    before any vocabulary pre-filter (disposal language, like the section-
    citing sentence that motivated the section-alignment check, is often
    in a paragraph that shares no vocabulary with the user's situation and
    would never reach a filtered subset).

    Returns:
        {
          "is_procedural_order": True | False | None,
          "has_reasoning_structure": True | False | None,
          "disposal_markers": [str, ...],
        }

    is_procedural_order is True ONLY when BOTH:
      - has_reasoning_structure is explicitly False (IK returned real
        structure tags for this document -- so we have a genuine signal
        -- and NONE of them are in REASONING_STRUCTURE_TAGS), AND
      - at least one PROCEDURAL_DISPOSAL_MARKERS phrase is present.

    has_reasoning_structure is None (not False) when NO paragraph carries
    ANY structure tag at all -- i.e. IK returned no structural
    classification for this document, so "no reasoning tags found" would
    be indistinguishable from "we have no signal either way". Never
    guess: missing data stays unknown, exactly like every other None in
    this module. is_procedural_order is also None in that case, even if
    disposal language is present -- a phrase alone was shown (see the
    module note) to be an insufficient signal by itself.

    Pure function, no network, never raises."""
    paras = [p for p in (paragraphs or []) if isinstance(p, dict)]
    structures = [p.get("structure") for p in paras if p.get("structure")]

    if not structures:
        has_reasoning_structure = None
    else:
        has_reasoning_structure = any(s in REASONING_STRUCTURE_TAGS for s in structures)

    markers = find_procedural_disposal_markers(*(p.get("text") or "" for p in paras))

    is_procedural_order = (
        (has_reasoning_structure is False) and bool(markers)
    ) if has_reasoning_structure is not None else None

    return {
        "is_procedural_order": is_procedural_order,
        "has_reasoning_structure": has_reasoning_structure,
        "disposal_markers": markers,
    }


def title_matches_any(title, known_names):
    """True if a normalised IK `title` looks like one of `known_names`
    (e.g. the project's 22 already-in-corpus judgments). Match is:
    every content word of a known name appears in the title, in order-
    independent fashion, AND the known name is at least two words (so a
    one-word name can't over-match). Used to DROP corpus cases from
    live results -- the user already has those, verified."""
    t = set(normalise_title(title).split())
    if not t:
        return False
    for name in known_names or []:
        parts = normalise_title(name).split()
        if len(parts) >= 2 and all(p in t for p in parts):
            return True
    return False


def triage_hit(doc, *, corpus_case_names=(), today=None):
    """Attach deterministic flags to one raw IK search hit. Pure function
    of the hit + the list of corpus case names + today. Every flag is
    True / False / None (None = data to decide is missing), never a guess.

        {
          "tid", "title", "url", "court", "court_tier",
          "publish_date" (ISO str or None),
          "is_corpus_case" (bool),
          "post_three_code_commencement" (bool | None),
          "adverse_markers" (list[str]),
          "snippet" (str, <=600 chars),
        }
    """
    today = today or date.today()
    tid = doc.get("tid") if isinstance(doc, dict) else None
    title = strip_html((doc.get("title") or doc.get("doc_title") or "") if isinstance(doc, dict) else "")
    pub = parse_ik_date((doc.get("publishdate") or doc.get("date")) if isinstance(doc, dict) else None)
    snippet = snippet_of(doc)
    docsource = doc.get("docsource") if isinstance(doc, dict) else None

    return {
        "tid": tid,
        "title": title,
        "url": f"https://indiankanoon.org/doc/{tid}/" if tid else None,
        "court": docsource,
        "court_tier": classify_court_tier(docsource),
        "publish_date": pub.isoformat() if pub else None,
        "is_corpus_case": title_matches_any(title, corpus_case_names),
        "post_three_code_commencement": (pub >= THREE_CODE_COMMENCEMENT) if pub else None,
        "adverse_markers": find_adverse_markers(title, snippet),
        "snippet": snippet[:600],
    }
