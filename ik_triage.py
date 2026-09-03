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
