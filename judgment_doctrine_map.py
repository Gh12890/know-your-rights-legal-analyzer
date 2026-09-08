"""
judgment_doctrine_map.py

The judgment-law counterpart of statute_doctrine_map.py.

WHY THIS EXISTS (2026-09-08):
The chat answer engine (chat_assistant.answer_question) gets its case law
ONLY from semantic_retrieval.find_relevant_sections -> semantic_search,
filtered against JUDGMENT_SIMILARITY_THRESHOLD (0.40). For a long,
narrative, multi-issue question -- the kind a frightened person actually
types -- voyage-law-2 similarity is weak: a real user query about being
"arrested for cheating and breach of trust" in a "trading partnership"
with "signatures I never signed" scored EVERY genuinely-relevant judgment
(Vijay Kumar Ghai, Usha Chakraborty, Satishchandra Ratanlal Shah on
civil-dispute-dressed-as-crime; Prabir Purkayastha / Arnesh Kumar on the
arrest itself) at ~0.25-0.33, well under 0.40 -- while a cheque-bounce
case (Rangappa) scored 0.407 on "loan"/"signature" vocabulary overlap and
had to be suppressed by name (see semantic_retrieval.OUT_OF_CHAT_DOMAIN_
CASE_NAMES). Net effect: the answer surfaced NO judgment at all, even
though the corpus holds exactly the right cases.

statute_doctrine_map.py already solves this class of gap for STATUTE
sections. This module does the same for JUDGMENTS: keyword-triggered,
hand-verified doctrine -> specific paragraph(s) of a specific judgment,
resolved through retrieval.get_judgment_paragraphs (real text, never
hardcoded here). Same "all words in a trigger group must appear somewhere
in the message" matching as statute_doctrine_map / doctrine_matcher.

SCOPE: this only feeds the chat answer's retrieved-text pool. It does not
touch main.py's compliance checks or Lane B's related-judgments panel
(which has its own doctrine-anchor mechanism).

EVERY paragraph reference below was read in the actual chunk file before
being added -- the slugs (e.g. "36_civil_dispute_vs_cheating") are the
chunker's own paragraph_number values for these seeded judgments.
"""

import logging

logger = logging.getLogger("judgment_doctrine_map")

# Caps to keep a multi-trigger query (arrest + cheating + FIR-refusal) from
# flooding the prompt. Entries earlier in the map win. Per-entry cap keeps
# one talkative doctrine from crowding out the others.
_MAX_ANCHORED_PARAGRAPHS = 6
_MAX_PARAGRAPHS_PER_ENTRY = 2


# Order matters: for someone already in custody the arrest-safeguard
# doctrines are the most urgent, so they come first and win the cap.
JUDGMENT_DOCTRINE_MAP = {
    # ---- the arrest itself ---------------------------------------------
    "grounds_of_arrest_must_be_furnished_in_writing": {
        "case_key": "prabir_purkayastha",
        "paragraph_numbers": ["30", "49"],
        "opinion_author": None,
        "trigger_groups": [
            ("arrested",), ("was arrested",), ("been arrested",),
            ("arrested me",), ("in the lock-up",), ("in lockup",),
            ("in custody",), ("police custody",),
            ("grounds", "arrest"), ("not told", "why"), ("nobody told", "why"),
            ("didn't tell", "why"), ("no reason", "arrest"),
            ("not shown", "documents"), ("haven't shown", "documents"),
            ("not shown", "grounds"),
        ],
        "context_note": (
            "In Prabir Purkayastha v State (NCT of Delhi) 2024 INSC 414 the "
            "Supreme Court held that the grounds of arrest must be "
            "communicated to the arrested person IN WRITING, that there is a "
            "real difference between the 'reasons for arrest' (formal, "
            "common to every arrest) and the 'grounds of arrest' (the "
            "specific facts and material that led to THIS arrest), and that "
            "an arrest memo which does not convey the grounds does not "
            "satisfy the requirement. Where the written grounds were not "
            "furnished before remand, the arrest and the remand were "
            "declared invalid and the accused was ordered released. The "
            "same principle was laid down for Article 22(1) generally in "
            "Pankaj Bansal v Union of India (2023) and reiterated in Vihaan "
            "Kumar v State of Haryana (2025)."
        ),
        "verified_note": (
            "Paras 30 (communicate grounds in writing) and 49 ('reasons' vs "
            "'grounds' distinction) read verbatim in "
            "chunks/prabir_purkayastha_v_state_(nct_of_delhi)_chunks.json. "
            "Added 2026-09-08."
        ),
    },
    "arrest_must_be_necessary_not_automatic": {
        "case_key": "arnesh_kumar",
        "paragraph_numbers": ["fallback_8", "fallback_10"],
        "opinion_author": None,
        "trigger_groups": [
            ("arrested", "cheating"), ("arrested", "breach of trust"),
            ("arrested", "318"), ("arrested", "316"),
            ("arrested", "420"), ("arrested", "406"),
            ("arrested", "theft"), ("arrested", "stole"),
            ("arrested", "stealing"), ("arrested", "hurt"),
            ("arrested", "assault"), ("arrested", "forgery"),
            ("arrested", "minor"), ("arrested", "small"),
            ("arrested", "directly"), ("arrested", "straight away"),
            ("arrested", "without", "notice"), ("no notice", "arrest"),
            ("arrest", "not necessary"), ("automatically", "arrest"),
            ("came to my house", "arrested"), ("came to our house", "arrested"),
            ("in the lock-up", "cheating"), ("in lockup", "cheating"),
        ],
        "context_note": (
            "In Arnesh Kumar v State of Bihar (2014) 8 SCC 273 the Supreme "
            "Court held that for an offence punishable with up to seven "
            "years the police may not arrest automatically: they must first "
            "be satisfied, on the parameters in Section 41 CrPC (now "
            "Section 35 BNSS), that arrest is NECESSARY -- to prevent a "
            "further offence, for proper investigation, to prevent tampering "
            "with evidence or intimidation of witnesses, or to secure the "
            "person's attendance -- and must record those reasons in "
            "writing. The Magistrate authorising detention must independently "
            "record satisfaction that the arrest was necessary before "
            "allowing further custody. Cheating and criminal breach of "
            "trust in their common forms fall within this band."
        ),
        "verified_note": (
            "fallback_8 (necessity conditions) and fallback_10 (Magistrate's "
            "recorded satisfaction) read verbatim in "
            "chunks/arnesh_kumar_v_state_of_bihar_chunks.json. The narrower "
            "7-direction checklist (fallback_12/13) is separately mapped as "
            "'arnesh_kumar_checklist' in retrieval.JUDGMENT_CITATION_MAP. "
            "Added 2026-09-08."
        ),
    },
    "twenty_four_hour_production_and_custodial_safeguards": {
        "case_key": "dk_basu",
        "paragraph_numbers": ["2", "5", "7"],
        "opinion_author": None,
        "trigger_groups": [
            ("beaten", "custody"), ("beaten", "lockup"), ("beaten", "lock-up"),
            ("beat", "custody"), ("hit", "custody"), ("slapped", "lockup"),
            ("tortur", "custody"), ("handcuff",), ("kept awake",),
            ("arrested", "medical"), ("arrested", "doctor"),
            ("arrested", "injured"), ("arrest memo",), ("no memo",),
        ],
        "context_note": (
            "The D.K. Basu v State of West Bengal (1997) 1 SCC 416 "
            "safeguards require, among other things, an arrest memo attested "
            "by a witness and countersigned by the arrestee (para 2), that a "
            "relative or friend be informed of the arrest and the place of "
            "custody (para 5), and that the arrestee be medically examined "
            "at the time of arrest with injuries recorded (paras 7-8). "
            "Breach of these is a serious matter to place before the "
            "Magistrate at the first production, and can found a claim for "
            "compensation."
        ),
        "verified_note": (
            "Paras 2/5/7 read verbatim in "
            "chunks/dk_basu_v_state_of_west_bengal_chunks.json; they map "
            "one-to-one to check_dk_basu_memo (see "
            "retrieval.JUDGMENT_CITATION_MAP 'dk_basu_safeguards'). "
            "Added 2026-09-08."
        ),
    },
    # ---- civil / commercial dispute given a criminal colour --------------
    "civil_dispute_criminalised_as_cheating_or_cbt": {
        "case_key": "vijay_kumar_ghai",
        "paragraph_numbers": ["36_civil_dispute_vs_cheating"],
        "opinion_author": None,
        "trigger_groups": [
            ("cheating", "partnership"), ("cheating", "partner"),
            ("cheating", "business"), ("cheating", "firm"),
            ("cheating", "loan"), ("cheating", "joint"),
            ("cheating", "cousin"), ("cheating", "commercial"),
            ("cheating", "contract"), ("cheating", "money", "dispute"),
            ("breach of trust", "partnership"), ("breach of trust", "partner"),
            ("breach of trust", "business"), ("breach of trust", "firm"),
            ("breach of trust", "loan"), ("breach of trust", "joint"),
            ("breach of trust", "contract"), ("breach of trust", "money"),
            ("420", "partnership"), ("406", "partnership"),
            ("cheating", "owed"), ("cheating", "repay"),
            ("false", "fir", "business dispute"),
            ("civil dispute", "criminal"), ("civil matter", "fir"),
        ],
        "context_note": (
            "In Vijay Kumar Ghai v State of West Bengal (2022) 7 SCC 124 the "
            "Supreme Court quashed an FIR alleging cheating (Section 420 "
            "IPC) and criminal breach of trust (Section 405) arising from a "
            "business/investment dispute, holding that the ingredients of "
            "those offences were simply not made out on the complaint's own "
            "averments and that a commercial dispute had been given the "
            "colour of a criminal offence. The relevance here: a partnership "
            "or loan dispute does not become 'cheating' or 'criminal breach "
            "of trust' just because money is owed or a deal went wrong -- "
            "the police and eventually the court must find dishonest "
            "intention and the specific ingredients of each offence, and "
            "where they are absent the criminal proceeding is liable to be "
            "quashed by the High Court under Section 528 BNSS (Section 482 "
            "CrPC). This is context, not a verdict on any particular case."
        ),
        "verified_note": (
            "Para slug '36_civil_dispute_vs_cheating' read verbatim in "
            "chunks/vijay_kumar_ghai_v_state_of_west_bengal_chunks.json "
            "(the file's single chunk). Citation (2022) 7 SCC 124 per the "
            "chunk's citation field. Added 2026-09-08."
        ),
    },
    "breach_of_contract_is_not_criminal_breach_of_trust": {
        "case_key": "satishchandra_ratanlal_shah",
        "paragraph_numbers": ["13_breach_of_trust_ingredients", "15_caution_against_criminalizing_civil_disputes"],
        "opinion_author": None,
        "trigger_groups": [
            ("breach of trust", "contract"), ("breach of trust", "business"),
            ("breach of trust", "partner"), ("breach of trust", "firm"),
            ("breach of trust", "loan"), ("breach of trust", "deal"),
            ("406", "contract"), ("406", "business"),
            ("misappropriat", "partner"), ("misappropriat", "business"),
            ("entrust", "partner"), ("entrust", "business"),
            ("criminal breach of trust", "money"),
        ],
        "context_note": (
            "In Satishchandra Ratanlal Shah v State of Gujarat (2019) 9 SCC "
            "148 the Supreme Court held that criminal breach of trust "
            "(Section 405/406 IPC; now Section 316 BNS) requires that "
            "property was actually ENTRUSTED to the accused and then "
            "dishonestly misappropriated -- a failure to repay a debt or "
            "honour a contract, without entrustment and dishonest "
            "misappropriation, is a civil wrong, not this offence. The "
            "Court repeated its consistent caution against criminalising "
            "civil disputes such as breach of contractual obligations."
        ),
        "verified_note": (
            "Para slugs '13_breach_of_trust_ingredients' and "
            "'15_caution_against_criminalizing_civil_disputes' read "
            "verbatim in chunks/satishchandra_ratanlal_shah_v_state_of_"
            "gujarat_chunks.json. Added 2026-09-08."
        ),
    },
    "cheating_needs_dishonest_intent_from_the_outset": {
        "case_key": "satishchandra_ratanlal_shah",
        "paragraph_numbers": ["14_cheating_vs_breach_of_contract"],
        "opinion_author": None,
        "trigger_groups": [
            ("cheating", "loan"), ("cheating", "contract"),
            ("cheating", "promise"), ("cheating", "repay"),
            ("cheating", "deal"), ("cheating", "agreement"),
            ("cheated", "loan"), ("cheated", "business"),
            ("420", "contract"), ("defraud", "contract"),
        ],
        "context_note": (
            "On the distinction between a mere breach of contract and the "
            "offence of cheating, the Supreme Court in Satishchandra "
            "Ratanlal Shah held that it turns on the intention at the time "
            "of the inducement: cheating requires that the accused had a "
            "fraudulent or dishonest intention AT THE OUTSET, when the other "
            "person was induced to part with property or act. A later "
            "failure to perform, or a business loss, does not by itself "
            "show that earlier dishonest intention and is not cheating."
        ),
        "verified_note": (
            "Para slug '14_cheating_vs_breach_of_contract' read verbatim in "
            "the same chunk file. Added 2026-09-08."
        ),
    },
    "fir_quashing_ingredients_not_made_out": {
        "case_key": "usha_chakraborty",
        "paragraph_numbers": [
            "breach_of_trust_406_bare_retention_insufficient",
            "cheating_420_deception_chain_not_explained",
            "civil_dispute_can_coexist_with_genuine_crime_converse_test",
        ],
        "opinion_author": None,
        "trigger_groups": [
            ("fir", "cheating", "business"), ("fir", "breach of trust", "business"),
            ("false", "cheating", "partner"), ("false", "cheating", "loan"),
            ("cheating", "breach of trust", "dispute"),
            ("arrested", "cheating", "breach of trust"),
            ("quash", "cheating"), ("quash", "fir", "business"),
        ],
        "context_note": (
            "In Usha Chakraborty v State of West Bengal (2023) the Supreme "
            "Court, quashing an FIR that had bundled cheating, criminal "
            "breach of trust and forgery charges out of a property/family "
            "dispute, went through each offence and held that the FIR did "
            "not spell out the essential ingredients of any of them -- for "
            "criminal breach of trust, bare retention of property is not "
            "enough without entrustment and dishonest misappropriation; for "
            "cheating, the FIR must explain the chain of deception. It also "
            "applied the Paramjeet Batra test: a dispute that is "
            "essentially civil should not be allowed to be pursued as a "
            "crime, though a genuine offence embedded in a civil dispute "
            "can still be investigated."
        ),
        "verified_note": (
            "Para slugs read verbatim in chunks/usha_chakraborty_v_state_of_"
            "west_bengal_chunks.json (11-chunk file). Added 2026-09-08."
        ),
    },
    # ---- FIR not registered -------------------------------------------
    "fir_registration_is_mandatory_lalita_kumari": {
        "case_key": "lalita_kumari",
        "paragraph_numbers": [
            "111_i_ii_registration_mandatory_no_preliminary_inquiry",
            "111_iv_v_duty_to_register_and_scope_of_preliminary_inquiry",
        ],
        "opinion_author": None,
        "trigger_groups": [
            ("won't register",), ("wont register",), ("will not register",),
            ("not registering",), ("didn't register",), ("did not register",),
            ("refuse", "register"), ("refusing", "register"), ("refused", "register"),
            ("refuse", "fir"), ("refusing", "fir"), ("refused", "fir"),
            ("won't", "fir"), ("not lodge",), ("won't lodge",),
            ("refusing", "complaint"), ("won't take", "complaint"),
            ("no fir",), ("zero fir",), ("fir", "not", "registered"),
        ],
        "context_note": (
            "In Lalita Kumari v Government of Uttar Pradesh (2014) 2 SCC 1 a "
            "Constitution Bench held that registration of an FIR under "
            "Section 154 CrPC (now Section 173 BNSS) is MANDATORY once the "
            "information discloses a cognizable offence, and the officer has "
            "no discretion to hold a preliminary inquiry into whether the "
            "information is true. A preliminary inquiry is permissible only "
            "in a narrow set of categories -- matrimonial/family disputes, "
            "commercial offences, medical negligence, corruption, and cases "
            "with abnormal unexplained delay -- and even then only to check "
            "whether the information discloses a cognizable offence, not its "
            "veracity, and it must be closed within a fixed period. Action "
            "lies against an officer who does not register a cognizable "
            "offence."
        ),
        "verified_note": (
            "Para slugs read verbatim in "
            "chunks/lalita_kumari_v_government_of_uttar_pradesh_chunks.json "
            "(seeded 2026-09-08, para 111 holding directions). Added "
            "2026-09-08 alongside statute_doctrine_map's BNSS 173/175 "
            "entries."
        ),
    },
    # ---- default bail ------------------------------------------------
    "default_bail_is_an_indefeasible_right": {
        "case_key": "m_ravindran",
        "paragraph_numbers": ["18_1_filing_the_application_is_availing_the_right"],
        "opinion_author": None,
        "trigger_groups": [
            ("chargesheet", "days"), ("charge sheet", "days"),
            ("no chargesheet",), ("haven't filed", "chargesheet"),
            ("hasn't filed", "chargesheet"), ("not filed", "chargesheet"),
            ("default bail",), ("statutory bail",),
            ("60 days", "custody"), ("90 days", "custody"),
            ("still", "investigating", "custody"),
        ],
        "context_note": (
            "In M. Ravindran v Intelligence Officer, DRI (2021) 2 SCC 485 "
            "and Bikramjit Singh v State of Punjab (2020) 10 SCC 616 the "
            "Supreme Court held that the right to default bail -- release on "
            "bail when the chargesheet is not filed within 60 or 90 days -- "
            "is not a mere statutory right but part of the fundamental right "
            "under Article 21, and it becomes indefeasible the moment the "
            "accused files an application for it after the period expires "
            "and is prepared to furnish bail. Filing the application is "
            "'availing' the right; it cannot be defeated by the prosecution "
            "then filing the chargesheet or seeking an extension."
        ),
        "verified_note": (
            "M. Ravindran para '18_1_filing_the_application_is_availing_the_"
            "right' and (context) Bikramjit Singh para "
            "'29_default_bail_is_a_fundamental_right_under_article_21' read "
            "verbatim in their chunk files. Added 2026-09-08."
        ),
    },
}


def match_judgment_doctrine(question: str) -> list:
    """Return the keys of JUDGMENT_DOCTRINE_MAP entries whose trigger groups
    match `question`. Same logic as statute_doctrine_map.match_statute_
    doctrine: a group matches if ALL its words appear anywhere in the
    lower-cased question."""
    if not question or not question.strip():
        return []
    q = question.lower()
    matched = []
    for key, entry in JUDGMENT_DOCTRINE_MAP.items():
        for group in entry["trigger_groups"]:
            if all(word in q for word in group):
                matched.append(key)
                logger.info("judgment_doctrine_map: matched %r on group=%r", key, group)
                break
    return matched


def get_judgment_doctrine_override(question: str) -> list:
    """Main entry point for chat_assistant. Given the user's message,
    resolve every matching doctrine to real judgment-paragraph text and
    return a list of match dicts shaped like semantic_search's judgment
    matches, so they merge straight into the same retrieved-text pool:

        {case_name, citation, paragraph_number, text, context_note,
         source: "curated_judgment_override"}

    Deduped by (case_name, paragraph_number); capped at
    _MAX_ANCHORED_PARAGRAPHS total. Never raises: a doctrine whose chunk
    file or paragraph cannot be resolved is logged and skipped.
    """
    from retrieval import get_judgment_paragraphs

    results = []
    seen = set()
    for key in match_judgment_doctrine(question):
        entry = JUDGMENT_DOCTRINE_MAP[key]
        paras = get_judgment_paragraphs(
            entry["case_key"], entry["paragraph_numbers"],
            opinion_author=entry.get("opinion_author"),
        )
        if not paras:
            logger.warning(
                "judgment_doctrine_map: %r -> get_judgment_paragraphs(%r, %r) "
                "returned nothing; skipping", key, entry["case_key"],
                entry["paragraph_numbers"],
            )
            continue
        # keep the map's own paragraph order, not the chunk-file order
        order = {str(pn): i for i, pn in enumerate(entry["paragraph_numbers"])}
        paras.sort(key=lambda pp: order.get(str(pp.get("paragraph_number")), 99))
        for p in paras[:_MAX_PARAGRAPHS_PER_ENTRY]:
            sig = (p.get("case_name"), str(p.get("paragraph_number")))
            if sig in seen:
                continue
            seen.add(sig)
            results.append({
                "case_name": p.get("case_name"),
                "citation": p.get("citation"),
                "paragraph_number": p.get("paragraph_number"),
                "opinion_author": p.get("opinion_author"),
                "text": p.get("text"),
                "context_note": entry["context_note"],
                "type": "judgment",
                "source": "curated_judgment_override",
            })
            if len(results) >= _MAX_ANCHORED_PARAGRAPHS:
                return results
    return results
