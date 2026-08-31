
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
    "rakhi_mitra": "chunks/rakhi_mitra_and_anr_v_state_of_west_bengal_chunks.json",
    "sri_manjunath_mp": "chunks/sri_manjunath_m_p_v_state_of_karnataka_chunks.json",
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
#
# REQUIRED CHECK before adding any new entry: several sourced judgments
# contain genuine DUPLICATE paragraph numbers -- confirmed real cases
# include NALSA, Prabir Purkayastha, L. Muruganantham, Rakhi Mitra,
# Satender Kumar Antil 2026, Sri Manjunath M P, Prakash Ranjan, and even
# Vihaan Kumar's own Oka opinion (see judgment_qa.py's
# find_duplicate_paragraph_numbers docstring for the confirmed causes).
# Before mapping a doctrine to a paragraph number in one of these
# documents, run judgment_qa.py and confirm that specific number is NOT
# a duplicate for that document -- or if it is, confirm which occurrence
# is the document's own reasoning (not a quoted passage) before using it.
# get_judgment_paragraphs already handles an unverified duplicate safely
# (returns all matches rather than silently picking one), but a
# JUDGMENT_CITATION_MAP entry should point to a specific, human-checked
# occurrence, not rely on that fallback.
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
    
        "rakhi_mitra_arnesh_kumar_consequences": {
        # APPLYING/ILLUSTRATIVE PRECEDENT, NOT a rule-source -- this is a
        # Calcutta HC judgment restating and applying Arnesh Kumar's own
        # consequence rule, not creating new binding law. Per user framing
        # (2026-08-26): High Court judgments in this corpus mainly
        # reiterate/apply existing Supreme Court precedent. If ever
        # surfaced to a person, this should be presented as "here's how a
        # High Court applied the Arnesh Kumar consequence rule", clearly
        # subordinate to and never in place of the arnesh_kumar_checklist
        # entry above, which is the actual Supreme Court source.
        "case_key": "rakhi_mitra",
        "paragraph_numbers": ["18"],
        "opinion_author": None,
        "verified_note": (
            "Confirmed: paragraph 18 directly quotes and restates Arnesh Kumar paragraph 11's "
            "consequence rule (departmental action + contempt of court for non-compliance with the "
            "S.35(3)/S.41A notice requirement). This paragraph number is NOT one of Rakhi Mitra's own "
            "flagged duplicates (see judgment_qa.py's duplicate-paragraph check) -- confirmed unambiguous, "
            "single occurrence. NOTE: this document's own paragraph 11 (distinct from this doctrine) is a "
            "genuine duplicate -- do not confuse the two; paragraph 18 was chosen specifically because it "
            "carries no such ambiguity."
        ),
    },
    "sri_manjunath_arnesh_kumar_application": {
        # APPLYING/ILLUSTRATIVE PRECEDENT, NOT a rule-source -- same status
        # as rakhi_mitra_arnesh_kumar_consequences above. This Karnataka HC
        # judgment applies Arnesh Kumar's vague-allegation reasoning to
        # quash a specific S.498A-style proceeding; it does not create new
        # binding law. Subordinate to, never a substitute for, the
        # arnesh_kumar_checklist entry.
        "case_key": "sri_manjunath_mp",
        "paragraph_numbers": ["22", "27"],
        "opinion_author": None,
        "verified_note": (
            "Confirmed: paragraph 22 directly names and quotes Arnesh Kumar v State of Bihar "
            "(paragraphs 10, 11, 11.1-11.8). Paragraph 27 is the Court's own finding applying that "
            "doctrine to these specific facts ('baseless, general and sweeping allegations... abuse of "
            "process of law'), immediately followed by the formal quashing order at paragraph 28. Both "
            "22 and 27 confirmed NOT among this document's flagged duplicates (see judgment_qa.py) -- "
            "unambiguous, single occurrences each."
        ),
    },
    
    "tapas_d_neogy_bank_account_as_property": {
        "case_key": "tapas_d_neogy",
        "paragraph_numbers": ["fallback_4", "fallback_6"],
        "opinion_author": None,
        "verified_note": (
            "Confirmed via direct chunk inspection (2026-08-30): "
            "fallback_4 contains Section 102 CrPC's actual provisions as "
            "extracted and examined by the Court ('Coming now to the "
            "provisions of Section 102 of the Code of Criminal "
            "Procedure, the said provisions are extracted herein below "
            "in extenso'). fallback_6 contains the Court's own core "
            "reasoning on why a bank account qualifies as 'property' "
            "capable of seizure -- the money-becomes-unidentifiable-once-"
            "mixed analysis. Other fallback chunks in this document "
            "(fallback_7 through fallback_10) are the Court SURVEYING "
            "other courts' prior decisions before reaching its own "
            "conclusion -- useful context but not the holding itself, "
            "deliberately not cited here to keep the citation focused on "
            "the Court's own reasoning. Chunked via fixed_size_fallback "
            "since no genuine ascending paragraph-number sequence was "
            "found in this document -- confirmed via direct regex "
            "inspection, same limitation this corpus already accepts "
            "for Arnesh Kumar. judgment_qa.py flagged this document's "
            "caption/closing as unrecognised -- CONFIRMED FALSE POSITIVE "
            "(direct text check, 2026-08-30): both the opening and "
            "closing are genuine, complete, real judgment text; the QA "
            "tool's pattern-matching was calibrated against the "
            "PDF-extraction path's typical caption/closing format and "
            "does not yet recognise this document's real but "
            "differently-formatted caption/closing (sourced via the "
            "HTML/API path, not a downloaded PDF)."
        ),
    },
    "neelkanth_blanket_freeze_disproportionate": {
        "case_key": "neelkanth_pharma_logistics",
        "paragraph_numbers": ["11", "12"],
        "opinion_author": None,
        "verified_note": (
            "Confirmed via direct chunk inspection (2026-08-30): "
            "paragraph 11 states the core fact pattern (an account with "
            "a Rs. 93,50,05,208/- balance frozen entirely over an "
            "innocuous Rs. 200/- credit) and the Court's finding that "
            "there is nothing to suggest the petitioner is a suspect or "
            "accused. Paragraph 12 (FIRST occurrence -- see duplicate "
            "note below) is the Court's own direct holding that freezing "
            "the entire account, rather than preserving only the "
            "disputed Rs. 200/-, caused serious adverse financial "
            "consequences including dishonoured cheques and business "
            "disruption. IMPORTANT -- CONFIRMED REAL DUPLICATE "
            "(judgment_qa.py flagged this, verified by direct chunk "
            "comparison, 2026-08-30): paragraph '12' appears TWICE in "
            "this document's chunks. The SECOND occurrence "
            "('...doubtful if the amounts in question could be even "
            "recovered from the petitioners...proceeds of crime.') is "
            "NOT this Court's own reasoning -- it is the tail end of a "
            "quoted excerpt from Dr. Sajir v. Reserve Bank of India, "
            "2023 SCC OnLine Ker 9087, which this judgment quotes at "
            "length. Only the FIRST occurrence of paragraph 12 (this "
            "Court's own text) should be treated as Neelkanth's holding; "
            "retrieval.py's get_judgment_doctrine returns both "
            "occurrences by design (same honest-collision pattern used "
            "elsewhere in this project) -- any renderer surfacing this "
            "doctrine should make clear which fragment is being shown if "
            "both appear. SCOPE LIMITATION: this judgment does NOT "
            "engage with BNSS Sections 106/107's specific textual scheme "
            "(confirmed by direct text search) -- it argues purely from "
            "Article 21/proportionality principles, complementary to but "
            "distinct from Malabar Gold's BNSS-textual holding below."
        ),
    },
    "malabar_gold_section_106_107_textual_holding": {
        "case_key": "malabar_gold",
        "paragraph_numbers": ["fallback_22", "fallback_24"],
        "opinion_author": None,
        "verified_note": (
            "Confirmed via direct chunk inspection (2026-08-30): "
            "fallback_22 states that the Investigating Agency may "
            "proceed under Section 107 BNSS to debit-freeze or attach "
            "funds, framing this as the ONLY lawful route (as opposed to "
            "Section 106, which the Court holds is evidentiary-seizure-"
            "only). fallback_24 contains the Court's direct holding that "
            "'any blanket or disproportionate freezing of bank accounts' "
            "is impermissible absent the proper Section 107 procedure. "
            "OTHER RELEVANT CHUNKS NOT CITED HERE, noted for "
            "completeness: fallback_16, fallback_17, and fallback_19 "
            "also discuss the Section 106/107 distinction and reference "
            "Kartik Yogeshwar Chatur v. Union of India (Bombay HC, 2025 "
            "SCC OnLine Bom 4778, NOT independently sourced/verified in "
            "this corpus yet) -- fallback_16 and fallback_17 open with a "
            "quotation mark and appear to be quoting another source "
            "rather than this Court's own direct language, so were not "
            "selected as the primary citation. CONFIRMED DATA-QUALITY "
            "NOTE (2026-08-30): this document's fixed_size_fallback "
            "chunking has scattered a recurring Delhi HC digital-"
            "signature portal footer into multiple chunks throughout the "
            "document (confirmed at fallback_14, fallback_18, "
            "fallback_23) -- this appears to repeat multiple times "
            "within the source HTML, unlike the single-footer-per-page "
            "pattern this project's PDF-extraction pipeline already "
            "handles. Not a content-loss issue (the real holding text is "
            "fully intact in the chunks cited above), but worth knowing "
            "this footer-noise pattern exists for this HTML-sourced "
            "document specifically. judgment_qa.py flagged this "
            "document's caption/closing as unrecognised -- CONFIRMED "
            "FALSE POSITIVE (direct text check, 2026-08-30), same "
            "reasoning as Tapas D. Neogy's note above."
        ),
    },
    
    "rangappa_section_139_presumption_mandatory": {
        "case_key": "rangappa",
        "paragraph_numbers": [],
        "opinion_author": None,
        "verified_note": (
            "Case read in full 2026-08-30. Vital holding confirmed: Section "
            "139's presumption of a legally enforceable debt is mandatory, "
            "covers the debt's existence itself (not just signature), and "
            "shifts the burden to the accused to rebut on a preponderance of "
            "probabilities. EXACT PARAGRAPH NUMBERS NOT YET CONFIRMED via "
            "direct chunk inspection -- must be located before this entry is "
            "considered complete, same discipline already applied to every "
            "other entry in this map."
        ),
    },
    "bir_singh_blank_cheque_and_informal_loan": {
        "case_key": "bir_singh",
        "paragraph_numbers": [],
        "opinion_author": None,
        "verified_note": (
            "Case read in full 2026-08-30. Vital holding confirmed: a blank "
            "cheque voluntarily signed and later filled in still attracts "
            "the Section 139 presumption; an informal/'friendly loan' does "
            "not defeat the presumption. EXACT PARAGRAPH NUMBERS NOT YET "
            "CONFIRMED -- must be located before this entry is complete."
        ),
    },
    "damodar_prabhu_compounding_cost_scheme": {
        "case_key": "damodar_s_prabhu",
        "paragraph_numbers": [],
        "opinion_author": None,
        "verified_note": (
            "Case read in full 2026-08-30. Vital holding confirmed: "
            "graduated cost scheme for compounding (roughly 10%/15%/20% of "
            "cheque amount at trial court post-conviction / High Court / "
            "Supreme Court stages), payable to legal aid fund; compounding "
            "remains available at any stage. EXACT PARAGRAPH NUMBERS NOT "
            "YET CONFIRMED -- must be located before this entry is "
            "complete, specifically the paragraph(s) stating the actual "
            "percentage figures, since those are the operative numbers "
            "compute_settlement_cost_incentive needs to cite precisely."
        ),
    },
    "kaveri_plastics_security_cheque_maturity": {
        "case_key": "kaveri_plastics",
        "paragraph_numbers": [],
        "opinion_author": None,
        "verified_note": (
            "Case read in full 2026-08-30. Vital holding confirmed (first "
            "of two holdings in this judgment): a cheque given as security "
            "for a future/contingent liability does not attract Section "
            "138 if dishonoured before the liability matures; the "
            "'security cheque' label is not itself determinative -- what "
            "matters is whether the debt was due and payable at the time "
            "of dishonour. EXACT PARAGRAPH NUMBERS NOT YET CONFIRMED -- "
            "must be located before this entry is complete."
        ),
    },
    "kaveri_plastics_amount_specifically_demanded": {
        "case_key": "kaveri_plastics",
        "paragraph_numbers": ["14"],
        "opinion_author": None,
        "verified_note": (
            "Case read in full 2026-08-30, paragraph 14 SPECIFICALLY "
            "CONFIRMED via direct reading: this paragraph quotes Suman "
            "Sethi v Ajay K. Churiwal, (2000) 2 SCC 380, verbatim -- "
            "'demand has to be made for the said amount i.e. the cheque "
            "amount... Where in addition to the said amount there is also "
            "a claim by way of interest, cost etc.' Establishes that a "
            "demand notice must specifically demand the cheque amount "
            "itself; additional amounts (interest, costs) mentioned "
            "alongside it do NOT by themselves invalidate the notice, "
            "provided the cheque amount remains specifically and severably "
            "demanded. Suman Sethi's own separate judgment was NOT "
            "independently fetched -- this project cites its holding via "
            "this verbatim quotation, per explicit 2026-08-30 decision."
        ),
    },
    "prakash_chimanlal_sheth_jurisdiction": {
        "case_key": "prakash_chimanlal_sheth",
        "paragraph_numbers": [],
        "opinion_author": None,
        "verified_note": (
            "Case read in full 2026-08-30. Vital holding confirmed: a "
            "Section 138 complaint must be filed where the cheque was "
            "presented for collection and dishonoured, per Section 142(2) "
            "NI Act and the Constitution Bench framework in Dashrath "
            "Rupsingh Rathod v State of Maharashtra (2014). EXACT "
            "PARAGRAPH NUMBERS NOT YET CONFIRMED -- must be located before "
            "this entry is complete."
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
        
