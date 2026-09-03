
"""
ik_query_builder.py

Deterministic query construction for Indian Kanoon discovery searches.

ARCHITECTURE DECISION (2026-08-28) — READ BEFORE EXTENDING:
This is Option B from the 3-option discussion: queries are anchored to
DOCTRINES you already trust (the case_keys in retrieval.py's
JUDGMENT_CITATION_MAP), not to BNS/BNSS section numbers.

WHY NOT SECTION NUMBERS (Option A/C, deferred, not abandoned):
Since BNS is ~2 years old, Indian Kanoon's case-law corpus is
overwhelmingly indexed under IPC/CrPC section numbers and case names —
searching "BNS 103" returns almost nothing useful today. So a
section-anchored search needs the OLD number, which meant a concordance.
UPDATE 2026-09-02: that concordance now exists — statute_concordance.py
(to_new / to_old), built by build_statute_concordance.py from the two
NCRB "Corresponding Section Table" PDFs. Option A is now UNBLOCKED but
still deferred: build it only after Option B's real results show it's
needed — do not build it preemptively. When built, resolve BNS/BNSS ->
IPC/CrPC via statute_concordance and feed the old number to IK.

WHAT THIS FILE ACTUALLY DOES:
Takes a case_key already present in JUDGMENT_CITATION_MAP (e.g.
"arnesh_kumar", "dk_basu") and builds a real, targeted Indian Kanoon
search query to find OTHER judgments (mainly High Court) that cite or
apply that same doctrine — extending the Rakhi Mitra / Sri Manjunath
pattern (applying/illustrative precedent, not new rule-sources) to more
candidates, without having a human manually think of search terms each
time.

This does NOT decide relevance or trustworthiness of results — that's
Step 3 (the QA gate). This file only answers: "given a doctrine I
already trust, what's a good search query to find more judgments that
apply it?"
"""

import logging

logger = logging.getLogger("ik_query_builder")


class UnknownCaseKeyError(Exception):
    """Raised when a case_key has no entry in CASE_METADATA. Fail
    loudly — do not guess a query for a doctrine we don't have
    curated metadata for."""
    pass


class MissingCitationError(Exception):
    """Raised when a citation-anchored query is requested but no real,
    verified citation is recorded for that case_key. Never falls back
    to guessing a citation string — a wrong citation used as a search
    query would confidently search for the wrong thing."""
    pass


# Human-curated metadata per case_key, kept DELIBERATELY SEPARATE from
# JUDGMENT_CITATION_MAP in retrieval.py rather than added to it, since
# that map's job is chunk/paragraph lookup for already-embedded text,
# not search-query construction. Mixing concerns there would blur what
# that file is for.
#
# Each entry needs enough real identifying information to build a
# search query that will actually find the right judgment and its
# citing progeny — not just the case_key slug, which is an internal
# name, not a search term IK's corpus would recognize.
#
# VERIFIED against retrieval.py's real JUDGMENT_CITATION_MAP structure
# (case_key values matched exactly, 2026-08-28). Only 7 case_keys exist
# there; L. Muruganantham is NOT yet in JUDGMENT_CITATION_MAP per the
# handoff (it's SC-tier but described as "confirmed, tagged" without a
# doctrine key wired yet) — omitted here until it's actually wired.
CASE_METADATA = {
    "arnesh_kumar": {
        "case_name": "Arnesh Kumar vs State of Bihar",
        "citation": "(2014) 8 SCC 273",
        "court": "Supreme Court",
        "year": 2014,
        "doctrine_short": "arrest guidelines under Section 41 CrPC",
    },
    "dk_basu": {
        "case_name": "D.K. Basu vs State of West Bengal",
        "citation": "(1997) 1 SCC 416",  # [Certain] — the standard
                                          # citation for the D.K. Basu
                                          # safeguards. Decided 18 Dec
                                          # 1996, reported in the 1997
                                          # SCC volume. As of 2026-09-01
                                          # the corpus record agrees
                                          # (it previously carried the
                                          # 1 Aug 1997 monitoring order's
                                          # "(1997) 6 SCC 642" -- see
                                          # that record's notes).
        "court": "Supreme Court",
        "year": 1996,  # decision year, not citation-volume year
        "doctrine_short": "arrest and detention safeguards",
    },
    "vihaan_kumar": {
        "case_name": "Vihaan Kumar vs State of Haryana",
        "citation": None,  # [Guessing] — no stable SCC print citation
                            # found yet (Feb 2025 decision, likely too
                            # recent). Confirm from your own corpus
                            # source PDF if it's needed for real use.
        "court": "Supreme Court",
        "year": 2025,  # [Certain] — confirmed via SC Monthly Digest,
                        # Feb 2025, bench included Justice Abhay S. Oka
                        # (matches retrieval.py's opinion_author field —
                        # strong cross-check this is the right case).
        "doctrine_short": "written grounds of arrest Article 22(1)",
    },
    "youth_bar_association": {
        "case_name": "Youth Bar Association of India vs Union of India",
        "citation": "(2016) 9 SCC 473",  # RESOLVED 2026-09-01: this
                            # citation appears verbatim in a real citing
                            # judgment, Abhihita Misra v State of U.P.
                            # (Allahabad HC, 10 Nov 2025, IK tid
                            # 174371940): "Youth Bar Association of India
                            # vs. Union of India and Another 2016 (9) SCC
                            # 473 has held that the copies of the F.I.R.s
                            # should be uploaded on the police website".
        "court": "Supreme Court",
        "year": 2016,  # [Certain] — confirmed via real IK search
                        # result 2026-08-28: top hit "Youth Bar
                        # Association Of India vs Union Of India . on
                        # 7 September, 2016 [Supreme Court - Daily
                        # Orders]". Two other 2016 entries also appear
                        # (2 May 2016 daily order), consistent with a
                        # single case having multiple order dates
                        # before final disposal.
        "doctrine_short": "FIR copy upload and accused FIR copy right",
        "extra_search_queries": [
            # The party name alone returns only this PIL's own monitoring
            # orders. These phrase queries surfaced the real applying
            # judgments (Abhihita Misra, Rabden Sherpa, Rabin Burman,
            # Saurav Das, ...) on the first try, 2026-09-01.
            '"Youth Bar Association" FIR uploaded police website',
            'Youth Bar Association "copy of the first information report" website 24 hours',
        ],
    },
    "tapas_d_neogy": {
        "case_name": "State of Maharashtra vs Tapas D. Neogy",
        "citation": "(1999) 7 SCC 685",
        "court": "Supreme Court",
        "year": 1999,
        "doctrine_short": "bank account as 'property' under old CrPC S.102 / BNSS S.106",
        # ADDED 2026-09-01 (Project 2, citation_currency.py worked example):
        # a real search using this case_name + "106 107 BNSS" surfaced
        # Khilji Mohsinahmed Mustakali v Assistant Director of
        # Enforcement (Bombay HC, 5 Dec 2025, IK tid 30125115), which
        # cites this case's paragraph 12 as continuing good law post-BNSS.
        # See citation_currency.py's tapas_d_neogy_bank_account_as_property
        # entry for the full verification record.
    },

    # -----------------------------------------------------------------
    # ADDED 2026-09-01 (Project 2, citation_currency_checker.py): the
    # remaining case_keys in retrieval.JUDGMENT_CITATION_MAP, so the
    # case-law-treatment checker can build a query for every curated
    # doctrine, not just the original five.
    #
    # PROVENANCE: case_name and citation for each were taken from that
    # case's own corpus/*.json record's fields as of 2026-09-01 (the
    # project's own sourced primary), NOT independently re-derived. They
    # inherit exactly the confidence those records carry -- which is not
    # absolute: the corpus record for D.K. Basu gives "(1997) 6 SCC 642"
    # while this file's older, separately-sourced dk_basu entry above
    # gives "(1997) 1 SCC 416". That discrepancy is unresolved and left
    # visible on purpose rather than papered over. Where the corpus
    # record had no clean reporter/neutral citation (the two Delhi HC
    # writ petitions), citation is None and the case-name query carries
    # the search on its own.
    # -----------------------------------------------------------------
    "rangappa": {
        "case_name": "Rangappa v Sri Mohan",
        "citation": "(2010) 11 SCC 441",
        "court": "Supreme Court",
        "year": 2010,
        "doctrine_short": "S.139 NI Act presumption is mandatory and covers debt existence",
    },
    "bir_singh": {
        "case_name": "Bir Singh v Mukesh Kumar",
        "citation": "(2019) 4 SCC 197",
        "court": "Supreme Court",
        "year": 2019,
        "doctrine_short": "S.139 NI Act presumption attaches even to a blank / undated cheque",
    },
    "damodar_s_prabhu": {
        "case_name": "Damodar S. Prabhu v Sayed Babalal H",
        "citation": "(2010) 5 SCC 663",
        "court": "Supreme Court",
        "year": 2010,
        "doctrine_short": "graduated compounding-cost scheme for S.138 NI Act settlement",
    },
    "kaveri_plastics": {
        "case_name": "Kaveri Plastics v Mahdoom Bawa Bahrudeen Noorul",
        "citation": None,  # corpus record has only "2025 INSC (Supreme
                            # Court, 19 September 2025)" -- not a clean
                            # neutral citation, so no citation-anchored
                            # query. Distinctive case name carries it.
        "court": "Supreme Court",
        "year": 2025,
        "doctrine_short": "S.138 demand notice must specifically and severably state the cheque amount",
    },
    "prakash_chimanlal_sheth": {
        "case_name": "Prakash Chimanlal Sheth v Jagruti Keyur Rajpopat",
        "citation": "2025 INSC 897",
        "court": "Supreme Court",
        "year": 2025,
        "doctrine_short": "territorial jurisdiction for a S.138 complaint (S.142(2) NI Act)",
    },
    "neelkanth_pharma_logistics": {
        "case_name": "Neelkanth Pharma Logistics Pvt. Ltd. v Union of India",
        "citation": None,  # corpus record has only the docket
                            # "W.P.(C) 17905/2024, decided 20 February
                            # 2025". Case-name query only.
        "court": "Delhi High Court",
        "year": 2025,
        "doctrine_short": "proportionality limit on blanket account freezes (Article 21)",
    },
    "malabar_gold": {
        "case_name": "Malabar Gold and Diamond Limited v Union of India",
        "citation": None,  # corpus record has only the docket
                            # "W.P.(C) 4198/2025, decided 16 January
                            # 2026". Case-name query only.
        "court": "Delhi High Court",
        "year": 2026,
        "doctrine_short": "Sections 106/107 BNSS textual scheme for police freezing of accounts",
    },
    "rakhi_mitra": {
        "case_name": "Rakhi Mitra and Anr v State of West Bengal",
        "citation": "2025:CHC-AS:1826",
        "court": "Calcutta High Court",
        "year": 2025,
        "doctrine_short": "restates Arnesh Kumar's S.41A non-compliance consequences",
    },
    "sri_manjunath_mp": {
        "case_name": "Sri Manjunath M P v State of Karnataka",
        "citation": "2026:KHC:2726",
        "court": "Karnataka High Court",
        "year": 2026,
        "doctrine_short": "applies Arnesh Kumar arrest-notice guidelines to specific facts",
    },
}


def build_doctrine_query(case_key: str, use_citation: bool = False) -> str:
    """
    Build a deterministic Indian Kanoon search query to find judgments
    (typically High Court) that cite and apply the given doctrine.

    Query strategy: search for the case name directly by default. Real
    testing (2026-08-28, 4 real doctrines) showed this works well for
    distinctive names (Arnesh Kumar: exact source judgment ranked #1
    of 9131) but poorly for generic ones (D.K. Basu vs State of West
    Bengal: real judgment ranked #3, unrelated cases with generic
    "State" matches ranked #1-2 — a party name plus "State" is not a
    distinctive string against millions of criminal judgments).

    Args:
        case_key: must be a key in CASE_METADATA (which is itself a
            subset of retrieval.py's JUDGMENT_CITATION_MAP case_keys).
        use_citation: if True, builds a citation-anchored query instead
            of a case-name query (e.g. '"(1997) 1 SCC 416"' instead of
            'D.K. Basu vs State of West Bengal'). Citations are highly
            distinctive strings and should rank the real judgment much
            higher for generic case names. Requires CASE_METADATA[key]
            ['citation'] to be set — raises if it's None, since a
            fabricated citation string would be worse than no query at
            all (it would confidently search for something wrong).

    Returns:
        A search query string, ready to pass to
        indiankanoon_client.search().

    Raises:
        UnknownCaseKeyError if case_key isn't in CASE_METADATA.
        MissingCitationError if use_citation=True but no citation is
            recorded for this case_key.
    """
    if case_key not in CASE_METADATA:
        raise UnknownCaseKeyError(
            f"'{case_key}' has no entry in CASE_METADATA. Known keys: "
            f"{sorted(CASE_METADATA.keys())}. Add a verified entry "
            f"before building queries for a new doctrine."
        )

    metadata = CASE_METADATA[case_key]

    if use_citation:
        citation = metadata.get("citation")
        if not citation:
            raise MissingCitationError(
                f"'{case_key}' has no citation recorded in CASE_METADATA "
                f"(citation=None). Cannot build a citation-anchored "
                f"query. Either add the real citation (verify against "
                f"your own sourced PDF, don't guess), or call this "
                f"function with use_citation=False to fall back to a "
                f"case-name query."
            )
        query = citation
    else:
        query = metadata["case_name"]

    logger.info(
        "Built query for case_key=%r (use_citation=%s): %r (doctrine: %s)",
        case_key, use_citation, query, metadata["doctrine_short"]
    )

    return query


def build_doctrine_queries(case_key: str) -> list:
    """
    Build ALL available query variants for a case_key, in priority
    order, for callers that want to try multiple queries and combine
    results rather than commit to just one.

    This exists specifically because real testing showed a single
    query strategy isn't reliably good enough: case-name queries work
    great for distinctive names (Arnesh Kumar) and poorly for generic
    ones (D.K. Basu). Rather than guess which category a new case_key
    falls into, Step 3's QA gate can search on EVERY available variant
    and pool the candidate results, which is more robust for a tool
    where users ask arbitrary real-world questions and a missed
    citation is a real cost, not just a minor inconvenience.

    Returns:
        List of query strings, in priority order: the case-name query
        (always, index 0), then the citation query if a citation is
        recorded, then any hand-curated 'extra_search_queries' for this
        case_key. The extras exist for doctrines whose party name is too
        generic for discovery -- confirmed real case (2026-09-01):
        'Youth Bar Association of India vs Union of India' returned only
        that PIL's own monitoring orders, never the High Court judgments
        that actually apply its FIR-upload guideline; a doctrine-phrase
        query ('"Youth Bar Association" FIR uploaded police website')
        surfaced them immediately.

    Raises:
        UnknownCaseKeyError if case_key isn't in CASE_METADATA.
    """
    queries = [build_doctrine_query(case_key, use_citation=False)]

    metadata = CASE_METADATA[case_key]  # already validated by the call above
    if metadata.get("citation"):
        queries.append(build_doctrine_query(case_key, use_citation=True))

    for extra in metadata.get("extra_search_queries", []):
        if extra and extra not in queries:
            queries.append(extra)

    return queries


def list_available_case_keys() -> list:
    """
    Returns the case_keys this module currently has metadata for, so
    a caller (or you, manually) can see what's available to search
    for without opening this file.
    """
    return sorted(CASE_METADATA.keys())


# ---------------------------------------------------------------------------
# ISSUE-anchored queries (Option A, finally built -- 2026-09-03).
#
# The doctrine-anchored queries above find the citing progeny of a case we
# ALREADY trust. These build a query for an arbitrary issue a chat user
# described -- anchored on (a) a verbatim fact phrase from their message,
# (b) the pre-2024 IPC/CrPC section number (Indian Kanoon's corpus is
# overwhelmingly indexed under the old numbers), (c) any doctrine name.
#
# Still not a relevance judgement: this only answers "given an issue, what
# is a reasonable IK search string?". related_judgments.py pools the
# results across a user's several issues and reranks them against the full
# message; that is where relevance is actually decided.
# ---------------------------------------------------------------------------

import re as _re

_PHRASE_CLEAN_RE = _re.compile(r'["“”‘’]')


def _clean_phrase(text: str) -> str:
    """Strip the quote characters IK's phrase syntax would choke on and
    collapse whitespace. Keeps letters, digits, spaces, hyphens."""
    text = _PHRASE_CLEAN_RE.sub("", text or "")
    text = _re.sub(r"[^\w\s\-]", " ", text)
    return _re.sub(r"\s+", " ", text).strip()


def _section_numbers_from_labels(labels: list) -> list:
    """['CrPC 41A', 'CrPC 41'] -> ['41A', '41'] (deduped, order kept)."""
    out = []
    for lbl in labels or []:
        parts = str(lbl).split()
        if parts:
            num = parts[-1]
            if num not in out:
                out.append(num)
    return out


# Filler words that carry no search signal -- dropped from issue-keyword
# extraction and trimmed off the front of an over-long fact phrase.
_QUERY_STOPWORDS = frozenset("""
a an the this that these those and or but of to in on at by for with as is are
was were be been being he she it they them his her their my our your i we me us
you not no nor so then than there here have has had do does did about after over
under from into out up down will would can could within was were on around
last month year years time still even though yet been being
""".split())


def _keywords(text: str, n: int = 5) -> list:
    """The first `n` content words of `text` (lowercased, stopwords and
    pure numbers dropped, order kept, deduped)."""
    out = []
    for w in _re.findall(r"[a-z]+", (text or "").lower()):
        if w in _QUERY_STOPWORDS or len(w) < 3:
            continue
        if w not in out:
            out.append(w)
        if len(out) >= n:
            break
    return out


def _trim_phrase(phrase: str, max_words: int = 5) -> str:
    """A phrase query only matches if it appears verbatim in a judgment;
    an 8-10 word layman phrase almost never does. Drop leading and
    trailing filler, then keep at most `max_words` words -- a shorter
    distinctive run is far more likely to hit (and the keyword+section
    companion query from build_issue_queries is the real workhorse)."""
    words = _clean_phrase(phrase).split()
    while words and words[0].lower() in _QUERY_STOPWORDS:
        words.pop(0)
    while words and words[-1].lower() in _QUERY_STOPWORDS:
        words.pop()
    words = words[:max_words]
    while words and words[-1].lower() in _QUERY_STOPWORDS:
        words.pop()
    return " ".join(words)


def build_issue_query(anchor: dict, *, courts: str = "supremecourt,highcourts",
                      fromdate: str = None, include_phrase: bool = True) -> str:
    """One Indian Kanoon `formInput` string for a single issue anchor
    (from related_judgments.build_anchors).

    anchor: {"issue", "hook_phrase", "new_sections", "old_sections",
             "doctrine_hooks"}
    courts: value for the `doctypes:` filter, or "" / None to omit it.
    fromdate: "DD-MM-YYYY" for a `fromdate:` recency bias, or None.
    include_phrase: if True, lead with a trimmed verbatim fact phrase;
        if False, a broader query -- issue keywords + doctrine + sections
        (the phrase-anchored query often returns nothing).

    Returns a plain query string. Never raises on a well-formed anchor.
    """
    parts = []

    if include_phrase:
        phrase = _trim_phrase(anchor.get("hook_phrase", ""))
        if phrase and len(phrase.split()) >= 2:
            parts.append(f'"{phrase}"')
    else:
        # keyword signal from the model's clean neutral issue description
        parts.extend(_keywords(anchor.get("issue", ""), n=5))

    for lbl in (anchor.get("doctrine_hooks") or [])[:2]:
        # Drop a subsection parenthetical ("Article 22(1)" -> "Article 22").
        cleaned = _clean_phrase(_re.sub(r"\s*\([^)]*\)", "", lbl))
        if not cleaned:
            continue
        # Quote a multi-word CASE NAME ("D K Basu") -- a phrase match is
        # what you want there. Leave a bare provision reference
        # ("Article 22", "Section 50") UNQUOTED: quoting it made every
        # preventive-detention constitutional judgment a top hit in the
        # first Phase-1b trial.
        is_provision_ref = bool(_re.match(r"(?i)(article|section|s\.?)\s+\d", cleaned))
        if len(cleaned.split()) >= 2 and not is_provision_ref:
            parts.append(f'"{cleaned}"')
        else:
            parts.append(cleaned)

    # Old (IPC/CrPC) numbers first -- most of IK's corpus is indexed under
    # them -- then the new. Kept SHORT: a query stuffed with numbers
    # matches on citation lists, not on the point of law.
    secnums = _section_numbers_from_labels(
        (anchor.get("old_sections") or [])[:2] + (anchor.get("new_sections") or [])[:1]
    )
    parts.extend(secnums)

    if not parts:
        parts.extend(_keywords(anchor.get("issue", ""), n=5) or ["criminal", "procedure"])

    query = " ".join(p for p in parts if p).strip()
    if courts:
        query += f" doctypes:{courts}"
    if fromdate:
        query += f" fromdate:{fromdate}"

    logger.info("built issue query: %r", query)
    return query


def build_issue_queries(anchor: dict, **kwargs) -> list:
    """Two queries for one issue: the trimmed-phrase query (precise, often
    zero hits) and the keyword+section query (broad, always something).
    Both run -- the phrase query, when it hits, tends to hit well; the
    keyword query is the safety net. Deduped. Callers pool the results
    across queries and issues, then dedupe by tid before ranking."""
    queries = []
    phrase = _trim_phrase(anchor.get("hook_phrase", ""))
    if phrase and len(phrase.split()) >= 2:
        queries.append(build_issue_query(anchor, include_phrase=True, **kwargs))

    broad = build_issue_query(anchor, include_phrase=False, **kwargs)
    if broad and broad not in queries:
        queries.append(broad)

    return queries or [build_issue_query(anchor, include_phrase=False, **kwargs)]

