
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

TWO AUDIENCES, TWO FIELDS (added 2026-09-01, after real UI testing):
'successor_treatment' is a detailed VERIFICATION TRAIL -- dates, IK tid
numbers, source URLs, phrases like "worked example" -- written for a
developer auditing this record, or for an LLM to read and paraphrase
(chat_assistant.py's prompt injection feeds it to the model, which has
already been observed producing good plain-language phrasing from it).
It is NOT meant to be shown to an end user of this "Know Your Rights"
tool verbatim -- confirmed a real problem via live testing: the app's
UI caveat was rendering this whole technical writeup directly in a
st.caption, which reads as internal audit notes, not something a
layperson asking about their arrest should see.
'user_facing_note' is the fix: one or two plain sentences, no
jargon, no internal identifiers (IK tids, dates-of-work, doctrine_key
names), safe to render directly to a user. app.py's caveat renderers
use this field; chat_assistant.py's LLM-prompt injection keeps using
successor_treatment, since the model already does its own (observed
good) paraphrasing there. GOOD_LAW entries set this to None since
their caveat is never rendered at all.
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
        "user_facing_note": (
            "This guideline was issued under an older section of the law "
            "that has since been renumbered as BNSS Section 35. Courts "
            "are still applying it under the new numbering — a July 2026 "
            "High Court order directed police to follow it."
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
        "user_facing_note": (
            "This case restates a Supreme Court rule (from Arnesh Kumar v "
            "State of Bihar) issued under an older section of the law, "
            "since renumbered as BNSS Section 35 — courts continue to "
            "apply it under the new numbering."
        ),
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
        "user_facing_note": (
            "This case applies a Supreme Court rule (from Arnesh Kumar v "
            "State of Bihar) issued under an older section of the law, "
            "since renumbered as BNSS Section 35 — courts continue to "
            "apply it under the new numbering."
        ),
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
            "GOOD_LAW regardless of the renumbering. "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 via "
            "citation_currency_checker.py: 17 candidate citing judgments, "
            "ZERO with adverse-treatment language (the D.K. Basu "
            "safeguards are among the most entrenched in Indian criminal "
            "procedure). One read in full: Sushrita Saren v State of West "
            "Bengal (Calcutta HC, 22 Apr 2025, IK tid 183221162), which "
            "cites D.K. Basu as a 'by now celebrated decision' on "
            "custodial torture/death and applies it post-commencement. "
            "CITATION NOTE: that citing judgment cites D.K. Basu as "
            "'(1997) 1 SCC 416' -- matching ik_query_builder.CASE_METADATA, "
            "NOT this project's corpus record, which has '(1997) 6 SCC "
            "642'. The wild-standard citation appears to be (1997) 1 SCC "
            "416; the corpus 'citation' field is likely wrong and should "
            "be checked (may be confusing the main 1996 judgment with a "
            "later order)."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: constitutional "
            "holding, unaffected by renumbering; BNSS 48 is the codified "
            "successor. Case-law treatment: verified via the checker + "
            "Sushrita Saren v State of WB (Calcutta HC, 22 Apr 2025) -- "
            "no adverse treatment. FLAG: corpus citation '(1997) 6 SCC "
            "642' conflicts with the wild-standard '(1997) 1 SCC 416'."
        ),
        "user_facing_note": None,
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
            "by statute renumbering. "
            "CASE-LAW-TREATMENT DIMENSION checked 2026-09-01 via "
            "citation_currency_checker.py: 9 candidate citing judgments, "
            "all post-commencement, ZERO with adverse-treatment language "
            "in the snippet. One read in full: Dr. Vaishali Jagannath "
            "Jamdar v State of Maharashtra (Bombay HC, 12 Aug 2025, IK "
            "tid 174603316), which relies on Vihaan Kumar (SLP (Crl) "
            "13320/2024, decided 07.02.2025) for the Article 22(1) "
            "holding that non-communication of grounds of arrest may "
            "render the arrest illegal, and applies it. "
            "IMPORTANT LIVE CAVEAT found in that same judgment (para 14): "
            "'the issue whether such compliance is required in each and "
            "every case is referred before the larger Bench, but at "
            "present the observation of the Hon'ble Apex Court in Vihaan "
            "Kumar... holds the field.' So the SCOPE of the written-"
            "grounds requirement (every case vs. some) is under a pending "
            "larger-bench reference as of mid-2025; the core holding is "
            "still good law to apply now. The checker's snippet-only "
            "adverse scan did NOT surface this ('larger bench' was in the "
            "body, not the headline) -- caught by the human read. This is "
            "a genuine watch item, not a downgrade."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: Article 22(1) "
            "holding, unaffected by renumbering; BNSS 47 is the successor. "
            "Case-law treatment: verified via the checker + Dr. Vaishali "
            "Jamdar v State of Maharashtra (Bombay HC, 12 Aug 2025) -- no "
            "adverse treatment, BUT a larger-bench reference is pending "
            "on whether the requirement applies in every case. Core "
            "holding 'holds the field' meanwhile. Re-check when the "
            "larger Bench reports."
        ),
        "user_facing_note": None,
        "last_checked_date": "2026-09-01",
    },

    "youth_bar_association_fir_copy_guidelines": {
        "status": "GOOD_LAW",
        "interpreted_provision": None,
        "successor_provision": None,
        "successor_treatment": (
            "STATUTE DIMENSION: Article 21-based FIR-access guideline, "
            "not tied to a single repealed numbered section -- no "
            "statute-renumbering issue. Also now partly reinforced by "
            "BNSS practice on FIR publication. "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 (second "
            "pass). The first pass was INCONCLUSIVE -- the case-name "
            "query returned only this PIL's own monitoring orders. Fixed "
            "by adding doctrine-phrase queries to "
            "ik_query_builder.CASE_METADATA['youth_bar_association']"
            "['extra_search_queries'] (e.g. '\"Youth Bar Association\" FIR "
            "uploaded police website'); citation_currency_checker.py now "
            "pools those too. The re-run returned 28 candidates, 5 dated "
            "on/after 1 July 2024, ZERO with adverse-treatment language. "
            "Two read in full: (1) Abhihita Misra v State of U.P. "
            "(Allahabad HC, 10 Nov 2025, IK tid 174371940) -- cites "
            "'Youth Bar Association of India vs. Union of India and "
            "Another 2016 (9) SCC 473', applies the FIR-upload + "
            "accused's-copy directions including the sensitive-offence "
            "carve-out; (2) Rabden Sherpa v State of Sikkim (Sikkim HC, "
            "7 Apr 2026, IK tid 177654854) -- examines the guideline and "
            "notes a further 15 Jan 2026 Supreme Court order (PUCL v "
            "State of Maharashtra) building on it. Live, positive, "
            "post-commencement treatment. CITATION RESOLVED: (2016) 9 "
            "SCC 473 (confirmed against Abhihita Misra), was None before."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: not applicable "
            "(Article 21 holding). Case-law treatment: verified on the "
            "second pass (after adding doctrine-phrase queries) + two "
            "citing judgments read in full (Abhihita Misra, Allahabad HC "
            "Nov 2025; Rabden Sherpa, Sikkim HC Apr 2026) -- no adverse "
            "treatment, active post-commencement application. Citation "
            "resolved to (2016) 9 SCC 473."
        ),
        "user_facing_note": None,
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
        "user_facing_note": (
            "This case was decided under an older section of the law "
            "that has since been renumbered as BNSS Section 106. A "
            "December 2025 High Court ruling confirms it is still being "
            "cited as good law under the current provision."
        ),
        "last_checked_date": "2026-09-01",
    },

    "neelkanth_blanket_freeze_disproportionate": {
        "status": "GOOD_LAW",
        "interpreted_provision": None,
        "successor_provision": None,
        "successor_treatment": (
            "STATUTE DIMENSION: argues purely from Article 21/"
            "proportionality; confirmed (retrieval.py's own verified_note, "
            "and independently by grep 2026-09-01) that this judgment does "
            "NOT engage BNSS 106/107's text at all. No statute-renumbering "
            "issue since no specific repealed provision sits at the core. "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 via "
            "citation_currency_checker.py: 10 candidate citing judgments, "
            "all post-commencement (2025-2026), ZERO with adverse-"
            "treatment language. One read in full: V-Mart Retail Limited "
            "v Nodal Cyber Cell Officer (Madras HC, 3 Nov 2025, IK tid "
            "36272070), which cites 'Neelkanth Pharma Logistics Private "
            "Limited v. Union of India... reported in 2025 SCC Del 1055' "
            "for the finding that account-freezing by banks at the "
            "instance of investigating agencies is often done with 'no "
            "proper system in place', and permits the petitioner to "
            "operate the account -- positive applied treatment, and part "
            "of a visible line of HC decisions (B. Seenivasan, and "
            "others) doing the same. CITATION NOTE: a real reporter "
            "citation surfaced -- '2025 SCC OnLine Del 1055' -- better "
            "than this project's docket-only 'W.P.(C) 17905/2024'."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: not applicable "
            "(Article 21 proportionality holding). Case-law treatment: "
            "verified via the checker + V-Mart Retail v Nodal Cyber Cell "
            "(Madras HC, 3 Nov 2025) -- positive post-commencement "
            "application, no adverse treatment. Citation upgrade "
            "available: 2025 SCC OnLine Del 1055."
        ),
        "user_facing_note": None,
        "last_checked_date": "2026-09-01",
    },

    "malabar_gold_section_106_107_textual_holding": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "BNSS", "section": "106, 107"},
        "successor_provision": None,
        "successor_treatment": (
            "STATUTE DIMENSION: directly construes CURRENT BNSS 106/107 "
            "text (confirmed via grep of the corpus file; decided 16 Jan "
            "2026, well after BNSS commencement). This IS the current "
            "law, not a holding under a repealed provision -- no "
            "supersession question can arise. "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 via "
            "citation_currency_checker.py: 10 candidate citing judgments, "
            "all post-commencement (mostly 2026), ZERO with adverse-"
            "treatment language. One read in full: M/S Lumicity "
            "Semiconductor Pvt. Ltd. v State of Haryana (Punjab & Haryana "
            "HC, 10 Jul 2026, IK tid 152086861), which cites 'Malabar "
            "Gold and Diamond Ltd. & Ors. V/s Union of India & Ors., "
            "2026 SCC OnLine Del 297', applies its directions on "
            "defreezing where the S.107 BNSS procedure was not followed, "
            "and lists it alongside a cross-High-Court line (Headstar "
            "Global v State of Kerala, 2025 SCC OnLine Ker 3546; Geeta "
            "Kampani v State of Maharashtra, 2026 SCC OnLine Bom 2937). "
            "Malabar Gold is being treated as leading authority on the "
            "BNSS 106/107 textual scheme, not doubted. CITATION NOTE: a "
            "real reporter citation surfaced -- '2026 SCC OnLine Del "
            "297' -- better than this project's docket-only 'W.P.(C) "
            "4198/2025'. No higher-court review located."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: not applicable "
            "(construes current BNSS text). Case-law treatment: verified "
            "via the checker + M/S Lumicity Semiconductor v State of "
            "Haryana (P&H HC, 10 Jul 2026) -- treated as leading "
            "authority across multiple High Courts, no adverse treatment. "
            "Citation upgrade available: 2026 SCC OnLine Del 297."
        ),
        "user_facing_note": None,
        "last_checked_date": "2026-09-01",
    },

    "rangappa_section_139_presumption_mandatory": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "139"},
        "successor_provision": None,
        "successor_treatment": (
            "STATUTE DIMENSION: the Negotiable Instruments Act was NOT "
            "part of the 2023 three-code overhaul (BNS replaces IPC, BNSS "
            "replaces CrPC, BSA replaces the Evidence Act -- the NI Act "
            "is a separate act, untouched). No statute-renumbering issue "
            "can arise for any NI Act citation in this corpus. "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 via "
            "citation_currency_checker.py (first doctrine run through it "
            "end-to-end): a live Indian Kanoon discovery search on both "
            "query variants ('Rangappa v Sri Mohan' and '(2010) 11 SCC "
            "441') returned 19 candidate citing judgments, 10 of them "
            "dated on/after the 1 July 2024 three-code commencement, and "
            "ZERO with any adverse-treatment language (overruled / per "
            "incuriam / doubted / larger bench / distinguished) in the "
            "snippet. One was fetched and read in full: M/S S.S. "
            "Production v Tr. Pavithran Prasanth (Supreme Court, 1 Oct "
            "2024, IK tid 125822205, https://indiankanoon.org/doc/125822205/) "
            "-- decided ~3 months post-commencement -- which applies "
            "Rangappa's paragraphs 39-40 (preponderance-of-probabilities "
            "rebuttal standard for the S.139 presumption), cites it again "
            "alongside Basalingappa v Mudibasappa on the post-evidence "
            "burden, and dismisses the complainant's SLP on that basis. "
            "This is real, sourced, post-commencement positive citing "
            "treatment by the Supreme Court itself. The other post-"
            "commencement hits (mainly Himachal Pradesh and Delhi High "
            "Court, 2024-2025) were not individually fetched; the older "
            "District Court hits from the citation-string query are "
            "routine applications, not adverse."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: NI Act "
            "unaffected by BNS/BNSS/BSA, supersession not applicable by "
            "definition. Case-law treatment: verified via "
            "citation_currency_checker.py + one SC judgment read in full "
            "(S.S. Production, 1 Oct 2024) -- no adverse treatment found, "
            "active post-commencement SC application confirmed."
        ),
        "user_facing_note": None,
        "last_checked_date": "2026-09-01",
    },

    "bir_singh_blank_cheque_and_informal_loan": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "139"},
        "successor_provision": None,
        "successor_treatment": (
            "STATUTE DIMENSION: NI Act not touched by the 2023 three-code "
            "overhaul (see rangappa_section_139_presumption_mandatory). "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 via "
            "citation_currency_checker.py: a live search on both query "
            "variants returned a large candidate set, ~9 dated on/after "
            "the 1 July 2024 commencement, ZERO with adverse-treatment "
            "language. One read in full: Kanwar Negi v Rajesh Kumar "
            "(Himachal Pradesh HC, 26 Sep 2024, IK tid 125730662, "
            "2024:HHC:9138), which quotes Bir Singh v Mukesh Kumar paras "
            "20/33/36 directly for the holdings that the S.139 "
            "presumption is a presumption of law and that it 'takes "
            "effect even in a situation where the accused contends that a "
            "blank cheque leaf was voluntarily signed and handed over' -- "
            "the exact doctrine this entry tracks, applied positively "
            "post-commencement."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: NI Act "
            "unaffected. Case-law treatment: verified via the checker + "
            "Kanwar Negi v Rajesh Kumar (HP HC, 26 Sep 2024) read in "
            "full -- no adverse treatment, positive post-commencement HC "
            "application confirmed."
        ),
        "user_facing_note": None,
        "last_checked_date": "2026-09-01",
    },

    "damodar_prabhu_compounding_cost_scheme": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "138, 147"},
        "successor_provision": None,
        "successor_treatment": (
            "STATUTE DIMENSION: NI Act not touched by the 2023 three-code "
            "overhaul (see rangappa_section_139_presumption_mandatory). "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 via "
            "citation_currency_checker.py: live search returned a large "
            "candidate set, several dated on/after 1 July 2024, ZERO with "
            "adverse-treatment language. One read in full: Balkrishan "
            "Chibber v Shri Rup Ram (Himachal Pradesh HC, 9 Aug 2024, IK "
            "tid 89600829), which quotes and applies Damodar S. Prabhu's "
            "paras 18-19 compounding-cost guidelines ('The purpose of "
            "laying down the Guidelines in Damodar S. Prabhu is explained "
            "in the said judgment itself...') -- positive post-"
            "commencement application of the graduated-cost scheme this "
            "entry tracks."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: NI Act "
            "unaffected. Case-law treatment: verified via the checker + "
            "Balkrishan Chibber v Shri Rup Ram (HP HC, 9 Aug 2024) read "
            "in full -- no adverse treatment, positive post-commencement "
            "HC application confirmed."
        ),
        "user_facing_note": None,
        "last_checked_date": "2026-09-01",
    },

    "kaveri_plastics_amount_specifically_demanded": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "138"},
        "successor_provision": None,
        "successor_treatment": (
            "STATUTE DIMENSION: NI Act not touched by the 2023 three-code "
            "overhaul (see rangappa_section_139_presumption_mandatory). "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 via "
            "citation_currency_checker.py: live search returned 10 "
            "candidates, all 2025-2026 (the source SC judgment is Sept "
            "2025), ZERO with adverse-treatment language in the snippet. "
            "One read in full: Ms Pharmaceuticals v Nityam Pharma (Delhi "
            "HC, 10 Jul 2026, IK tid 87610412), which engages the rule "
            "substantively and DISTINGUISHES it on the facts -- Kaveri "
            "Plastics concerned a notice demanding roughly double the "
            "cheque amount via a typographical error, whereas a demand "
            "for LESS than the cheque amount is not caught. Distinguishing "
            "on facts is not adverse to the holding's validity; the rule "
            "stands and its scope is being worked out. NOTE: the checker's "
            "snippet-only adverse scan did not flag 'distinguishable' "
            "because it appears in the body, not the headline -- a known "
            "limitation, caught here by the human read the bundle is "
            "designed to prompt. CITATION CLEANUP: this record's "
            "'citation' field ('2025 INSC (Supreme Court, 19 September "
            "2025)') is incomplete -- the real neutral citation is 2025 "
            "INSC 1133 (Gavai CJI, Anjaria J.), affirming the Delhi HC "
            "below (cited in the wild as Mahdoom Bawa Bahrudeen Noorul v "
            "Kaveri Plastics, (2024) 02 Del CK 0095). Same litigation, "
            "different stages -- not a contradiction."
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: NI Act "
            "unaffected. Case-law treatment: verified via the checker + "
            "Ms Pharmaceuticals v Nityam Pharma (Delhi HC, 10 Jul 2026) "
            "read in full -- distinguished on facts, not doubted; holding "
            "intact. Corpus 'citation' field should be corrected to "
            "'2025 INSC 1133'."
        ),
        "user_facing_note": None,
        "last_checked_date": "2026-09-01",
    },

    "prakash_chimanlal_sheth_jurisdiction": {
        "status": "GOOD_LAW",
        "interpreted_provision": {"act": "Negotiable Instruments Act", "section": "142(2)"},
        "successor_provision": None,
        "successor_treatment": (
            "STATUTE DIMENSION: NI Act not touched by the 2023 three-code "
            "overhaul (see rangappa_section_139_presumption_mandatory). "
            "CASE-LAW-TREATMENT DIMENSION verified 2026-09-01 via "
            "citation_currency_checker.py: live search on both query "
            "variants returned ~15 candidates, most dated on/after 1 July "
            "2024, ZERO with adverse-treatment language. One read in "
            "full: Rajinder Singh Gandhi v Kunal Arora (Delhi District "
            "Court, 30 Oct 2025, IK tid 121787167), a S.138 territorial-"
            "jurisdiction revision where the petitioner relies on "
            "'Prakash Chimanlal Sheth v. Jagruti Keyur Rajpopat {2025 "
            "INSC 897}' on exactly the S.142(2) point this entry tracks, "
            "and the court engages it alongside M/s Shri Sendhur Agro "
            "{2025 INSC 328}. Positive applied treatment; the neutral "
            "citation '2025 INSC 897' is confirmed correct against this "
            "citing judgment. (The checker also surfaced an earlier "
            "Bombay HC judgment of 5 Mar 2024 and an SC order of 23 Jul "
            "2024 in the same matter -- procedural history, not adverse.)"
        ),
        "verified_note": (
            "Both dimensions checked 2026-09-01. Statute: NI Act "
            "unaffected. Case-law treatment: verified via the checker + "
            "Rajinder Singh Gandhi v Kunal Arora (Delhi DC, 30 Oct 2025) "
            "read in full -- positive post-commencement application on "
            "the S.142(2) jurisdiction point; '2025 INSC 897' confirmed."
        ),
        "user_facing_note": None,
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
            "user_facing_note": "This case hasn't been checked for legal currency yet.",
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
            "user_facing_note": "This case hasn't been checked for legal currency yet.",
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
            "user_facing_note": "This citation's legal currency hasn't been independently checked yet.",
            "last_checked_date": None,
        }
    return entry


if __name__ == "__main__":
    from retrieval import JUDGMENT_CITATION_MAP

    print("=== Citation currency coverage ===")
    for key in sorted(JUDGMENT_CITATION_MAP.keys()):
        record = get_citation_currency(key)
        print(f"{key}: {record['status']}")
