
"""
citation_currency.py

Project 2: Legal-Currency Verification Agent -- first working slice.

WHAT THIS FILE IS FOR:
retrieval.py's JUDGMENT_CITATION_MAP answers "what did this case say."
This file answers a separate question that nothing in the project
previously checked in a structured way: "is that holding still good
law, or has it been renumbered/overruled/distinguished since." Project
1 caught two fabricated holdings and one unverified doctrinal-lineage
claim (see CORRECTION note in
corpus/state_of_maharashtra_v_tapas_d_neogy.json, 2026-09-01) purely by
a human re-reading primary text by hand. This file exists to make that
discipline a checked, structured field instead of prose a human has to
remember to re-derive every time.

THE NON-NEGOTIABLE PRINCIPLE, APPLIED HERE:
No code in this file decides whether a case is still good law. That
determination can ONLY be a curated, human-verified record -- exactly
the same discipline as JUDGMENT_CITATION_MAP's verified_note fields --
because "has any later, binding court overruled this" is not something
text pattern-matching or an LLM can safely decide. What this file DOES
compute mechanically is the narrower, genuinely deterministic fact of
whether the OLD statutory provision a case construed has been
renumbered under BNS/BNSS -- that's just a lookup against real statute
text (see get_statute_section() calls in each entry's history), not a
judgment call.

TWO SEPARATE DIMENSIONS OF "CURRENCY" -- DO NOT CONFLATE THEM:
1. Statute supersession: did the numbered provision this case
   construed get renumbered/repealed by the 2023 BNS/BNSS/BSA
   overhaul? Mechanical, checkable against real statute text.
2. Case-law treatment: has any later court overruled, distinguished,
   or (as found for Tapas D. Neogy, 2026-09-01) affirmatively
   continued to apply this holding? Requires actual sourced research
   (Indian Kanoon search + reading the citing text) -- never assumed,
   never inferred from silence.

STATUS VALUES:
- GOOD_LAW: no statute renumbering issue (constitutional holding, NI
  Act provision -- NI Act was NOT touched by the 2023 three-code
  overhaul -- or a case construing current BNS/BNSS text directly) and
  no known adverse case-law treatment.
- SUPERSEDED_BY_STATUTE: the specific numbered provision this case
  construed was renumbered/repealed by BNS/BNSS. Does NOT by itself
  mean the doctrine is dead -- see successor_treatment for whether
  later courts have carried it forward. Renumbering and abandonment
  are different facts; this status only asserts the former.
- OVERRULED: a later, binding court has explicitly held this case (or
  the specific holding cited) no longer applies. Not currently used by
  any entry below -- would require sourced evidence, same bar as
  GOOD_LAW's "no known adverse treatment" claim.
- DISTINGUISHED: a later court has narrowed this holding's application
  without rejecting it outright. Not currently used below, same
  evidentiary bar as OVERRULED.

NOT_YET_VERIFIED is deliberately NOT a status a curated entry ever
sets -- it is the default get_citation_currency() returns for any
doctrine_key with no entry at all, so that "nobody has checked this
yet" is always visible and never silently indistinguishable from
"checked and found fine."
"""

import logging

logger = logging.getLogger("citation_currency")


NOT_YET_VERIFIED = "NOT_YET_VERIFIED"


# ---------------------------------------------------------------------------
# Keyed by doctrine_key -- the SAME keys used in retrieval.py's
# JUDGMENT_CITATION_MAP -- not case_key, since two doctrine_keys pointing
# at the same case_key (e.g. Kaveri Plastics' two entries) can construe
# different provisions with different currency facts.
# ---------------------------------------------------------------------------
CITATION_CURRENCY_MAP = {

    "arnesh_kumar_checklist": {
        "status": "SUPERSEDED_BY_STATUTE",
        "interpreted_provision": {"act": "CrPC (old)", "section": "41(1)(b)(ii), 41A"},
        "successor_provision": {"act": "BNSS", "section": "35(1)(b)(ii), 35(3)-(6)"},
        "successor_treatment": (
            "FULL VERIFICATION DONE 2026-09-01 (second worked example, "
            "after tapas_d_neogy). Statute mapping: retrieval."
            "get_statute_section('BNSS','35') fetched and confirmed its "
            "text matches old S.41(1)(b)(ii)'s necessity-of-arrest "
            "parameters ('reason to believe... arrest is necessary... to "
            "prevent... further offence... proper investigation... "
            "record... reasons in writing') and old S.41A's notice-of-"
            "appearance scheme almost verbatim (BNSS 35(3): 'issue a "
            "notice directing the person... to appear'; 35(5): compliance "
            "bars arrest absent recorded reasons). Case-law treatment: a "
            "live Indian Kanoon search (query anchored to case name + "
            "'BNSS 35 notice appearance') surfaced B Vijayalaxmi v State "
            "of Telangana (Telangana HC, 24 July 2026, IK tid 20163394, "
            "https://indiankanoon.org/doc/20163394/) -- over two years "
            "after BNSS's July 2024 commencement -- in which the Court "
            "DIRECTLY orders police to 'issue a notice under Section "
            "35(3) of BNSS... following the guidelines issued by the "
            "Hon'ble Supreme Court in the case of Arnesh Kumar Vs. State "
            "of Bihar.' This is a real court actively applying the "
            "checklist to the renumbered provision, not treating it as "
            "superseded/obsolete. The search's other top results (Md "
            "Imran, Jakku Venu, Salluri Mahesh and others, all Telangana "
            "HC, 2025-2026) suggest this is routine practice in that "
            "court, not an isolated citation -- only one was fetched and "
            "read in full; the others were not independently confirmed."
        ),
        "verified_note": (
            "Full statute-mapping AND case-law-treatment verification "
            "done 2026-09-01 -- second entry in this map with both "
            "dimensions checked."
        ),
        "last_checked_date": "2026-09-01",
    },

    "rakhi_mitra_arnesh_kumar_consequences": {
        "status": "SUPERSEDED_BY_STATUTE",
        "interpreted_provision": {"act": "CrPC (old)", "section": "41A"},
        "successor_provision": {"act": "BNSS", "section": "35(3)-(6)"},
        "successor_treatment": (
            "Mirrors arnesh_kumar_checklist's status AND its now-verified "
            "case-law treatment -- this is a High Court judgment "
            "restating Arnesh Kumar's own S.41A consequence rule, not an "
            "independent holding, so its currency tracks the primary "
            "doctrine's, including the B Vijayalaxmi v State of Telangana "
            "evidence recorded there. Not independently re-searched under "
            "its own case name."
        ),
        "verified_note": "Inherits arnesh_kumar_checklist's full verification, 2026-09-01.",
        "last_checked_date": "2026-09-01",
    },

    "sri_manjunath_arnesh_kumar_application": {
        "status": "SUPERSEDED_BY_STATUTE",
        "interpreted_provision": {"act": "CrPC (old)", "section": "41, 41A"},
        "successor_provision": {"act": "BNSS", "section": "35"},
        "successor_treatment": (
            "Same as rakhi_mitra_arnesh_kumar_consequences -- applies "
            "Arnesh Kumar's doctrine to specific facts rather than "
            "creating independent law; currency tracks the primary entry, "
            "including its now-verified case-law treatment. Not "
            "independently re-searched under its own case name."
        ),
        "verified_note": "Inherits arnesh_kumar_checklist's full verification, 2026-09-01.",
        "last_checked_date": "2026-09-01",
    },

    "dk_basu_safeguards": {
        "status": "GOOD_LAW",
        "interpreted_provision": None,
        "successor_provision": {"act": "BNSS", "section": "48 (family/friend notification)"},
        "successor_treatment": (
            "D.K. Basu's holding derives from Article 21/22, not from "
            "construing a pre-existing numbered section -- it PRECEDED and "
            "prompted statutory codification (first CrPC S.50A/41B/41C via "
            "2008 amendment, now BNSS 48). retrieval.get_statute_section"
            "('BNSS','48') fetched 2026-09-01: text opens 'shall forthwith "
            "give the information regarding such arrest... to any of his "
            "relatives, friends' -- direct textual match to the family/"
            "friend-notification safeguard. Since the constitutional "
            "holding doesn't depend on any single section's number, "
            "GOOD_LAW regardless of the renumbering. Not yet checked "
            "for adverse case-law treatment."
        ),
        "verified_note": "Statute cross-reference verified 2026-09-01. Case-law-treatment dimension not yet checked.",
        "last_checked_date": "2026-09-01",
    },

    "vihaan_kumar_written_grounds": {
        "status": "GOOD_LAW",
        "interpreted_provision": None,
        "successor_provision": {"act": "BNSS", "section": "47 (grounds of arrest)"},
        "successor_treatment": (
            "Article 22(1) constitutional holding -- the arrest itself "
            "referenced old-CrPC-style section numbers (S.50A appears in "
            "this judgment's own text, confirmed via grep 2026-09-01; "
            "BNSS did not carry the 'A' suffix numbering forward, so this "
            "indicates the underlying arrest predates BNSS's July 2024 "
            "commencement even though the judgment itself was decided "
            "2025). BNSS 47 ('shall forthwith communicate... full "
            "particulars of the offence... or other grounds for such "
            "arrest') is the direct successor of the old grounds-of-"
            "arrest requirement this case's constitutional holding "
            "reinforces. GOOD_LAW since Article 22(1) itself is untouched "
            "by statute renumbering. Not yet checked for adverse "
            "case-law treatment."
        ),
        "verified_note": "Statute cross-reference verified 2026-09-01. Case-law-treatment dimension not yet checked.",
        "last_checked_date": "2026-09-01",
    },

    "youth_bar_association_fir_copy_guidelines": {
        "status": "GOOD_LAW",
        "interpreted_provision": None,
        "successor_provision": None,
        "successor_treatment": (
            "Article 21-based FIR-access guideline, not tied to a single "
            "repealed numbered section -- no statute-renumbering issue. "
            "Not yet checked for adverse case-law treatment."
        ),
        "verified_note": "No repealed provision at the core of this holding; statute-supersession dimension not applicable.",
        "last_checked_date": "2026-09-01",
    },

    "tapas_d_neogy_bank_account_as_property": {
        "status": "SUPERSEDED_BY_STATUTE",
        "interpreted_provision": {"act": "CrPC (old)", "section": "102"},
        "successor_provision": {"act": "BNSS", "section": "106"},
        "successor_treatment": (
            "WORKED EXAMPLE -- full verification done 2026-09-01. Statute "
            "mapping: retrieval.get_statute_section('BNSS','106') fetched "
            "and confirmed VERBATIM-IDENTICAL in substance to the old "
            "CrPC S.102 text this judgment itself quotes in extenso "
            "('may seize any property which may be alleged or suspected "
            "to have been stolen, or which may be found under "
            "circumstances which create suspicion of the commission of "
            "any offence') -- a straight renumbering, not a substantive "
            "rewrite. Case-law treatment: a prior version of this "
            "project's corpus notes claimed Neelkanth Pharma Logistics "
            "and Malabar Gold both 'trace back to' this case -- CONFIRMED "
            "FALSE via direct grep of both corpus files for 'Neogy'/"
            "'Tapas' (zero matches in either), retracted 2026-09-01 (see "
            "corpus/state_of_maharashtra_v_tapas_d_neogy.json). REPLACED "
            "with real evidence: a live Indian Kanoon search (2026-09-01, "
            "query anchored to case name + '106 107 BNSS') surfaced "
            "Khilji Mohsinahmed Mustakali v Assistant Director of "
            "Enforcement (Bombay HC, 5 Dec 2025, IK tid 30125115, "
            "https://indiankanoon.org/doc/30125115/) -- decided over a "
            "year after BNSS's July 2024 commencement -- which explicitly "
            "cites this case's paragraph 12 holding as continuing good "
            "law for the bank-account-as-property analysis. This is "
            "genuine, sourced, post-BNSS positive citing treatment, not "
            "an inference. Not yet added to the embedded corpus (separate "
            "chunking/embedding pipeline, out of scope for this check)."
        ),
        "verified_note": (
            "Full statute-mapping AND case-law-treatment verification "
            "done 2026-09-01 -- the only entry in this map with both "
            "dimensions checked, as the Project 2 worked example."
        ),
        "last_checked_date": "2026-09-01",
    },

    "neelkanth_blanket_freeze_disproportionate": {
        "status": "GOOD_LAW",
        "interpreted_provision": None,
        "successor_provision": None,
        "successor_treatment": (
            "Argues purely from Article 21/proportionality; confirmed "
            "(retrieval.py's own verified_note, and independently by grep "
            "2026-09-01) that this judgment does NOT engage BNSS 106/107's "
            "text at all. No statute-renumbering issue since no specific "
            "repealed provision sits at the core of the holding. Not yet "
            "checked for adverse case-law treatment."
        ),
        "verified_note": "No repealed provision at the core of this holding; statute-supersession dimension not applicable.",
        "last_checked_date": "2026-09-01",
    },

    "malabar_gold_section_106_107_textual_holding": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "BNSS", "section": "106, 107"},
        "successor_provision": None,
        "successor_treatment": (
            "Directly construes CURRENT BNSS 106/107 text (confirmed via "
            "grep of the corpus file, which mentions 'Section 106' and "
            "'Section 107' explicitly; decided 16 Jan 2026, well after "
            "BNSS commencement). This IS the current law, not a holding "
            "under a repealed provision -- no supersession question can "
            "arise. Not yet checked for adverse case-law treatment (e.g. "
            "whether any higher court has since reviewed this Delhi HC "
            "ruling)."
        ),
        "verified_note": "Constructs current statute text directly; supersession dimension not applicable by definition.",
        "last_checked_date": "2026-09-01",
    },

    "rangappa_section_139_presumption_mandatory": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "139"},
        "successor_provision": None,
        "successor_treatment": (
            "The Negotiable Instruments Act was NOT part of the 2023 "
            "three-code overhaul (BNS replaces IPC, BNSS replaces CrPC, "
            "BSA replaces the Evidence Act -- the NI Act is a separate "
            "act, untouched). No statute-renumbering issue can arise for "
            "any NI Act citation in this corpus. Not yet checked for "
            "adverse case-law treatment."
        ),
        "verified_note": "NI Act unaffected by BNS/BNSS/BSA; supersession dimension not applicable by definition.",
        "last_checked_date": "2026-09-01",
    },

    "bir_singh_blank_cheque_and_informal_loan": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "139"},
        "successor_provision": None,
        "successor_treatment": "Same reasoning as rangappa_section_139_presumption_mandatory -- NI Act citation, not touched by BNS/BNSS.",
        "verified_note": "NI Act unaffected by BNS/BNSS/BSA; supersession dimension not applicable by definition.",
        "last_checked_date": "2026-09-01",
    },

    "damodar_prabhu_compounding_cost_scheme": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "138, 147"},
        "successor_provision": None,
        "successor_treatment": "Same reasoning as rangappa_section_139_presumption_mandatory -- NI Act citation, not touched by BNS/BNSS.",
        "verified_note": "NI Act unaffected by BNS/BNSS/BSA; supersession dimension not applicable by definition.",
        "last_checked_date": "2026-09-01",
    },

    "kaveri_plastics_amount_specifically_demanded": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "138"},
        "successor_provision": None,
        "successor_treatment": "Same reasoning as rangappa_section_139_presumption_mandatory -- NI Act citation, not touched by BNS/BNSS.",
        "verified_note": "NI Act unaffected by BNS/BNSS/BSA; supersession dimension not applicable by definition.",
        "last_checked_date": "2026-09-01",
    },

    "prakash_chimanlal_sheth_jurisdiction": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "142(2)"},
        "successor_provision": None,
        "successor_treatment": "Same reasoning as rangappa_section_139_presumption_mandatory -- NI Act citation, not touched by BNS/BNSS.",
        "verified_note": "NI Act unaffected by BNS/BNSS/BSA; supersession dimension not applicable by definition.",
        "last_checked_date": "2026-09-01",
    },
}


_case_name_to_case_key_cache = None


def _build_case_name_to_case_key() -> dict:
    """Reverse index: real case_name (as it appears on every embedded
    chunk -- confirmed identical to the corpus JSON's own case_name
    field, 2026-09-01) -> case_key (the short alias JUDGMENT_CITATION_MAP
    uses). Built from retrieval.py's own _JUDGMENT_CHUNK_FILES registry
    and each case's first real chunk, rather than hardcoded here a
    second time, so it can never drift out of sync with the real data.
    Cached at module level since this never changes at runtime."""
    global _case_name_to_case_key_cache
    if _case_name_to_case_key_cache is not None:
        return _case_name_to_case_key_cache

    from retrieval import _JUDGMENT_CHUNK_FILES, _load_judgment_chunks

    mapping = {}
    for case_key in _JUDGMENT_CHUNK_FILES:
        chunks = _load_judgment_chunks(case_key)
        if chunks:
            case_name = chunks[0].get("case_name")
            if case_name:
                mapping[case_name] = case_key
    _case_name_to_case_key_cache = mapping
    return mapping


def get_citation_currency_for_case_name(case_name: str) -> list:
    """Entry point for the CHAT path (semantic_retrieval.py's
    judgment_matches carry a case_name, not a doctrine_key -- chat
    questions are answered from open-ended embedding search, not a
    curated doctrine lookup, so there's no doctrine_key to look up
    directly). Resolves case_name -> case_key -> every doctrine_key
    JUDGMENT_CITATION_MAP has for that case, and returns ALL of their
    currency records -- a case can carry more than one doctrine_key
    with potentially different currency facts, and picking just one
    would hide that, same honest-collision principle as Neelkanth's
    duplicate-paragraph handling in retrieval.py.

    Returns a list of currency dicts, each tagged with its doctrine_key
    (or None if no doctrine_key/case_key could be resolved at all --
    this happens for corpus judgments that were embedded but never
    given a curated JUDGMENT_CITATION_MAP entry, e.g. Pankaj Bansal,
    NALSA, Prabir Purkayastha as of 2026-09-01 -- a DIFFERENT, and in
    some ways more basic, gap than 'doctrine known but currency not
    yet checked'). Never returns an empty list -- always at least one
    record, so a caller can always show SOMETHING rather than silently
    treating an unmapped case as equivalent to good law."""
    case_key = _build_case_name_to_case_key().get(case_name)

    if case_key is None:
        return [{
            "doctrine_key": None,
            "status": NOT_YET_VERIFIED,
            "interpreted_provision": None,
            "successor_provision": None,
            "successor_treatment": None,
            "verified_note": (
                f"'{case_name}' does not resolve to any case_key this "
                f"project tracks in JUDGMENT_CITATION_MAP -- this "
                f"judgment may be embedded in the corpus without ever "
                f"having been given a curated doctrine entry at all."
            ),
            "last_checked_date": None,
        }]

    from retrieval import JUDGMENT_CITATION_MAP

    matching_doctrine_keys = [
        key for key, entry in JUDGMENT_CITATION_MAP.items()
        if entry["case_key"] == case_key
    ]

    if not matching_doctrine_keys:
        return [{
            "doctrine_key": None,
            "status": NOT_YET_VERIFIED,
            "interpreted_provision": None,
            "successor_provision": None,
            "successor_treatment": None,
            "verified_note": (
                f"'{case_name}' resolves to case_key '{case_key}' but no "
                f"JUDGMENT_CITATION_MAP entry currently uses that case_key."
            ),
            "last_checked_date": None,
        }]

    results = []
    for doctrine_key in matching_doctrine_keys:
        record = dict(get_citation_currency(doctrine_key))
        record["doctrine_key"] = doctrine_key
        results.append(record)
    return results


def get_citation_currency(doctrine_key: str) -> dict:
    """Main entry point. Returns the currency record for doctrine_key.

    NEVER returns None and never raises for an unknown key -- absence
    of a curated record is itself a fact worth surfacing (nobody has
    checked this citation's currency yet), not something to hide by
    returning nothing. Callers should always get a dict with a
    'status' key back.
    """
    entry = CITATION_CURRENCY_MAP.get(doctrine_key)
    if entry is None:
        logger.info(
            "citation_currency: doctrine_key=%r has no curated currency "
            "record -- returning explicit NOT_YET_VERIFIED default.",
            doctrine_key,
        )
        return {
            "status": NOT_YET_VERIFIED,
            "interpreted_provision": None,
            "successor_provision": None,
            "successor_treatment": None,
            "verified_note": (
                "No currency verification has been performed yet for "
                "this citation."
            ),
            "last_checked_date": None,
        }
    return entry


if __name__ == "__main__":
    from retrieval import JUDGMENT_CITATION_MAP

    print("=== Citation currency coverage ===")
    for key in sorted(JUDGMENT_CITATION_MAP.keys()):
        record = get_citation_currency(key)
        print(f"{key}: {record['status']}")
