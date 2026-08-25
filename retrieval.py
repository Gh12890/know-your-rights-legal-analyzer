
"""
Retrieval layer, Phase 1: exact lookup, not embeddings.

Two lookup functions:
  - get_statute_section(act, section_number): pulls a BNS/BNSS section's
    real text by its exact section number, from the already-sourced and
    chunked statute corpus.
  - get_judgment_paragraphs(case_key, paragraph_numbers): pulls specific
    paragraph(s) from a sourced judgment by exact paragraph number.

Neither uses embeddings or similarity search. Both are dictionary lookups
against pre-chunked corpus files, because main.py never needs "find me
something similar" -- it always cites an exact section number or an exact
doctrine it already knows the source of. See JUDGMENT_CITATION_MAP below
for the specific doctrine -> paragraph mappings, each individually verified
against the real chunked text before being added (not guessed).

This module has NO knowledge of compliance logic -- it only fetches real
source text. Whatever calls it (an LLM extraction step, or eventually a
compliance-check function wanting to show its source) is responsible for
reading and using that text. This keeps the deterministic-classification-
decides / LLM-only-extracts boundary intact: adding source text access
doesn't mean Python is inferring anything new from it.
"""

import json
import os


_STATUTE_CHUNK_FILES = {
    "BNS": "chunks/bharatiya_nyaya_sanhita_2023_chunks.json",
    "BNSS": "chunks/bharatiya_nagarik_suraksha_sanhita_2023_chunks.json",
}

_JUDGMENT_CHUNK_FILES = {
    "arnesh_kumar": "chunks/arnesh_kumar_v_state_of_bihar_chunks.json",
    "vihaan_kumar": "chunks/vihaan_kumar_v_state_of_haryana_chunks.json",
    "satender_kumar_antil_2026": "chunks/satender_kumar_antil_v_central_bureau_of_investigation_(2026)_chunks.json",
    "prabir_purkayastha": "chunks/prabir_purkayastha_v_state_(nct_of_delhi)_chunks.json",
    "dk_basu": "chunks/dk_basu_v_state_of_west_bengal_chunks.json",
    "nalsa": "chunks/national_legal_services_authority_v_union_of_india_chunks.json",
    "pankaj_bansal": "chunks/pankaj_bansal_v_union_of_india_chunks.json",
    "youth_bar_association": "chunks/youth_bar_association_v_union_of_india_chunks.json",
}

_statute_cache = {}
_judgment_cache = {}


def _load_statute_chunks(act):
    if act not in _STATUTE_CHUNK_FILES:
        return None
    if act not in _statute_cache:
        path = _STATUTE_CHUNK_FILES[act]
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        _statute_cache[act] = {c["section_number"]: c for c in chunks}
    return _statute_cache[act]


def _load_judgment_chunks(case_key):
    if case_key not in _JUDGMENT_CHUNK_FILES:
        return None
    if case_key not in _judgment_cache:
        path = _JUDGMENT_CHUNK_FILES[case_key]
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            _judgment_cache[case_key] = json.load(f)
    return _judgment_cache[case_key]


def get_statute_section(act, section_number):
    """Returns the real statute text for a section, keyed by BASE section
    number only (e.g. "106", not "106(2)") -- confirmed the chunker splits
    statutes at the top-level numbered-section boundary only, so a
    subsection-specific request returns the whole parent section's text,
    not just that subsection. Returns None if the act or section isn't
    found, never raises, so callers can treat a miss the same honest way
    the rest of this project treats "Cannot Determine" cases.

    act: "BNS" or "BNSS"
    section_number: e.g. "106", "106(2)" (subsection suffix is stripped
        automatically), "35"
    """
    chunks_by_section = _load_statute_chunks(act)
    if chunks_by_section is None:
        return None
    base = section_number.split("(")[0].strip()
    chunk = chunks_by_section.get(base)
    if chunk is None:
        return None
    return {
        "act": act,
        "section_number": base,
        "text": chunk["text"],
    }


def get_judgment_paragraphs(case_key, paragraph_numbers, opinion_author=None):
    """Returns the real text of specific paragraph(s) from a sourced
    judgment. paragraph_numbers can be a single string/int or a list, to
    support doctrines that span more than one paragraph (confirmed real
    case: Arnesh Kumar's directions span fallback_12 and fallback_13).

    opinion_author: only needed for multi-opinion documents (confirmed
    real case: Vihaan Kumar has two -- pass "ABHAY S. OKA" or
    "KOTISWAR SINGH" to disambiguate; for single-opinion documents, leave
    as None).

    Returns None if the case isn't found. Returns a list of paragraph
    dicts (possibly empty, if none of the requested numbers exist) rather
    than raising, for the same honest-miss reason as get_statute_section.
    """
    chunks = _load_judgment_chunks(case_key)
    if chunks is None:
        return None

    if isinstance(paragraph_numbers, (str, int)):
        paragraph_numbers = [paragraph_numbers]
    wanted = set(str(p) for p in paragraph_numbers)

    results = []
    for c in chunks:
        if str(c["paragraph_number"]) not in wanted:
            continue
        if opinion_author is not None and c.get("opinion_author") != opinion_author:
            continue
        results.append({
            "case_name": c["case_name"],
            "citation": c["citation"],
            "paragraph_number": c["paragraph_number"],
            "opinion_author": c.get("opinion_author"),
            "text": c["text"],
        })
    return results


# ---------------------------------------------------------------------------
# Judgment citation map: doctrine -> exact source location.
#
# Each entry below was individually verified against the real chunked text
# before being added here -- not guessed from the case name or a general
# sense of what the case is "about". This is what lets main.py's existing
# citation strings (e.g. "D.K. Basu safeguards", "Youth Bar Association
# guidelines (a)-(c)") resolve to real, checkable source text on demand.
# ---------------------------------------------------------------------------

JUDGMENT_CITATION_MAP = {
    "arnesh_kumar_checklist": {
        "case_key": "arnesh_kumar",
        "paragraph_numbers": ["fallback_12", "fallback_13"],
        "opinion_author": None,
        "manual_override_text": (
            "All the State Governments to instruct its police officers not to automatically arrest "
            "when a case under Section 498-A of the IPC is registered but to satisfy themselves about "
            "the necessity for arrest under the parameters laid down above flowing from Section 41, "
            "Cr.PC;\n\n"
            "All police officers be provided with a check list containing specified sub-clauses under "
            "Section 41(1)(b)(ii);\n\n"
            "The police officer shall forward the check list duly filed and furnish the reasons and "
            "materials which necessitated the arrest, while forwarding/producing the accused before "
            "the Magistrate for further detention;\n\n"
            "The Magistrate while authorising detention of the accused shall peruse the report "
            "furnished by the police officer in terms aforesaid and only after recording its "
            "satisfaction, the Magistrate will authorise detention;\n\n"
            "The decision not to arrest an accused, be forwarded to the Magistrate within two weeks "
            "from the date of the institution of the case with a copy to the Magistrate which may be "
            "extended by the Superintendent of police of the district for the reasons to be recorded "
            "in writing;\n\n"
            "Notice of appearance in terms of Section 41A of Cr.PC be served on the accused within two "
            "weeks from the date of institution of the case, which may be extended by the "
            "Superintendent of Police of the District for the reasons to be recorded in writing;\n\n"
            "Failure to comply with the directions aforesaid shall apart from rendering the police "
            "officers concerned liable for departmental action, they shall also be liable to be "
            "punished for contempt of court to be instituted before High Court having territorial "
            "jurisdiction.\n\n"
            "We hasten to add that the directions aforesaid shall not only apply to the cases under "
            "Section 498-A of the I.P.C. or Section 4 of the Dowry Prohibition Act, the case in hand, "
            "but also such cases where offence is punishable with imprisonment for a term which may be "
            "less than seven years or which may extend to seven years; whether with or without fine."
        ),
        "verified_note": (
            "Confirmed: fallback_12 and fallback_13 are ~1500-char blind chunks (Arnesh Kumar's "
            "paragraph numbers did not survive PDF extraction -- see chunk_judgments.py notes), so the "
            "raw chunk boundaries include text before and after the actual checklist directions (the "
            "preceding paragraph on anticipatory bail volume, and the trailing instruction to circulate "
            "the judgment to Chief Secretaries). manual_override_text is a hand-trimmed exact excerpt of "
            "just the 7 checklist/timeline/consequence directions plus the 7-year applicability line, "
            "taken verbatim from the same source text -- no wording changed, only the surrounding "
            "context removed. This is the ONE entry in this map needing manual trimming; every other "
            "doctrine below has real paragraph-number boundaries and needs no override."
        ),
    },
    "dk_basu_safeguards": {
        "case_key": "dk_basu",
        "paragraph_numbers": ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11"],
        "opinion_author": None,
        "verified_note": (
            "Confirmed: paragraphs 2-11 are the eleven numbered requirements "
            "(memo of arrest, witness attestation, right to inform family, "
            "medical exam, etc.), matching check_dk_basu_memo's checks "
            "one-to-one -- e.g. para 2 = witness-attested memo, para 5 = "
            "family/friend informed, paras 7-8 = medical examination."
        ),
    },
    "vihaan_kumar_written_grounds": {
        "case_key": "vihaan_kumar",
        "paragraph_numbers": ["10"],
        "opinion_author": "ABHAY S. OKA",
        "verified_note": (
            "Confirmed: paragraph 10 (Oka, J.'s lead opinion) establishes "
            "the Article 22(1) written-grounds-of-arrest requirement, "
            "referencing Pankaj Bansal directly. opinion_author is required "
            "here since this document genuinely has two separate opinions "
            "(see chunk_judgments.py notes) and paragraph '10' only exists "
            "meaningfully within Oka's opinion."
        ),
    },
    "youth_bar_association_fir_copy_guidelines": {
        "case_key": "youth_bar_association",
        "paragraph_numbers": ["12"],
        "opinion_author": None,
        "verified_note": (
            "Confirmed: paragraph 12 contains the full lettered guideline "
            "list (a) through (k), including the accused's early-FIR-copy "
            "right (a)-(c) and the 24/48/72-hour online upload requirement "
            "(d), both cited by main.py's check_early_fir_copy_right and "
            "check_fir_uploaded_online functions."
        ),
    },
}


def get_judgment_doctrine(doctrine_key):
    """Convenience wrapper: resolves a doctrine key from
    JUDGMENT_CITATION_MAP directly to its real source text, so callers
    don't need to know the underlying case_key/paragraph_numbers/
    opinion_author details. Returns None if the doctrine key isn't mapped.

    If the map entry has a manual_override_text (confirmed real need: only
    arnesh_kumar_checklist, whose blind fallback chunks include irrelevant
    surrounding text), that hand-trimmed excerpt is returned instead of the
    raw chunk lookup -- still the case's own real words, just without the
    extra context a human wouldn't want repeated on every check."""
    entry = JUDGMENT_CITATION_MAP.get(doctrine_key)
    if entry is None:
        return None

    if "manual_override_text" in entry:
        chunks = get_judgment_paragraphs(entry["case_key"], entry["paragraph_numbers"], opinion_author=entry["opinion_author"])
        case_name = chunks[0]["case_name"] if chunks else None
        citation = chunks[0]["citation"] if chunks else None
        return [{
            "case_name": case_name,
            "citation": citation,
            "paragraph_number": "checklist (excerpted)",
            "opinion_author": None,
            "text": entry["manual_override_text"],
        }]

    return get_judgment_paragraphs(
        entry["case_key"],
        entry["paragraph_numbers"],
        opinion_author=entry["opinion_author"],
    )


if __name__ == "__main__":
    print("=== Statute lookup test ===")
    r = get_statute_section("BNSS", "106(2)")
    print(f"BNSS 106(2) -> base section 106, {len(r['text']) if r else 0} chars" if r else "NOT FOUND")

    print("\n=== Judgment doctrine lookup test ===")
    for key in JUDGMENT_CITATION_MAP:
        result = get_judgment_doctrine(key)
        total_chars = sum(len(p["text"]) for p in result) if result else 0
        print(f"{key}: {len(result) if result else 0} paragraph(s), {total_chars} chars")
        
