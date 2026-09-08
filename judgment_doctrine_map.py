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
# flooding the prompt. Paragraphs are gathered round-robin -- one per matched
# doctrine first, then second paragraphs -- so every relevant CASE gets in
# before any case gets a second paragraph. Entries earlier in the map win
# ties. Per-entry cap keeps one talkative doctrine from crowding out others.
_MAX_ANCHORED_PARAGRAPHS = 8
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
        # Arnesh Kumar is the safeguard for EVERY arrest for an offence up
        # to 7 years -- fire it whenever an arrest has actually happened,
        # not only for a hard-coded list of offence words. The context_note
        # is self-limiting ("for an offence punishable with up to seven
        # years"), so it does no harm on a genuinely serious-offence
        # answer.
        "trigger_groups": [
            ("arrested",), ("was arrested",), ("been arrested",),
            ("arrested me",), ("have arrested me",), ("i am arrested",),
            ("in the lock-up",), ("in the lockup",), ("in lock-up",),
            ("in lockup",), ("in police custody",), ("police custody",),
            ("in custody",), ("still in custody",), ("held in custody",),
            ("arrested", "days"), ("custody", "days"),
            ("directly arrested",), ("arrested", "straight away"),
            ("arrested", "without", "notice"), ("no notice", "arrest"),
            ("arrest", "not necessary"), ("automatically", "arrest"),
            ("came to my house", "arrested"), ("came to our house", "arrested"),
        ],
        "context_note": (
            "In Arnesh Kumar v State of Bihar (2014) 8 SCC 273 the Supreme "
            "Court held that for an offence punishable with up to seven "
            "years (this covers most property offences, cheating, criminal "
            "breach of trust, kidnapping under BNS 137(2), and hurt) the "
            "police may not arrest automatically: they must first be "
            "satisfied, on the parameters in Section 41 CrPC (now Section 35 "
            "BNSS), that arrest is NECESSARY -- to prevent a further "
            "offence, for proper investigation, to prevent tampering with "
            "evidence or intimidation of witnesses, or to secure the "
            "person's attendance -- and must record those reasons in "
            "writing. The Magistrate authorising detention must "
            "independently record satisfaction that the arrest was "
            "necessary before allowing further custody."
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
    "notice_is_the_rule_arrest_is_the_exception_bnss": {
        "case_key": "satender_kumar_antil_2026",
        "paragraph_numbers": ["31", "33"],
        "opinion_author": None,
        "trigger_groups": [
            ("arrested",), ("was arrested",), ("been arrested",),
            ("arrested me",), ("have arrested me",),
            ("in the lock-up",), ("in the lockup",), ("in lock-up",),
            ("in lockup",), ("in police custody",), ("police custody",),
            ("in custody",), ("still in custody",),
            ("arrested", "days"), ("custody", "days"),
            ("arrested", "directly"), ("arrested", "without", "notice"),
            ("no notice", "arrest"), ("arrest", "not necessary"),
            ("35(3)",), ("41a",), ("41-a",),
            ("came to my house", "arrested"), ("straight to arrest",),
            ("should have got a notice",),
        ],
        "context_note": (
            "In Satender Kumar Antil v CBI, 2026 INSC 115 (order dated "
            "15 January 2026) the Supreme Court, interpreting the new "
            "Bharatiya Nagarik Suraksha Sanhita, held plainly that for an "
            "offence punishable with imprisonment up to seven years a NOTICE "
            "under Section 35(3) of the BNSS is the RULE and an arrest under "
            "Section 35(6) is the EXCEPTION. Its conclusions: an arrest is a "
            "statutory discretion, never mandatory; the officer must ask "
            "whether arrest is a necessity before making it; even where the "
            "Section 35(1)(b) conditions exist, the arrest must not be made "
            "unless it is 'absolutely warranted'; and the power to arrest "
            "after a notice has issued is 'not a matter of routine, but an "
            "exception'. This is the current-code restatement of Arnesh "
            "Kumar."
        ),
        "verified_note": (
            "Paras 31 and 33 (the court's own holding and its lettered "
            "conclusions) read verbatim in chunks/satender_kumar_antil_v_"
            "central_bureau_of_investigation_(2026)_chunks.json; both are "
            "x1 (paras 24 and 32 in this file are duplicated because it "
            "quotes the 2022 Satender Kumar Antil and Arnesh Kumar inline -- "
            "deliberately not used). Citation 2026 INSC 115. case_key is "
            "'satender_kumar_antil_2026' -- the hardcoded key in "
            "retrieval._JUDGMENT_CHUNK_FILES (auto-register skips a file "
            "already registered under any key). Added 2026-09-08."
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
    "consequence_of_arresting_without_the_notice_or_recorded_reasons": {
        "case_key": "rakhi_mitra",
        "paragraph_numbers": ["18", "21"],
        "opinion_author": None,
        "trigger_groups": [
            ("arrested", "before"), ("arrested", "without", "notice"),
            ("no notice", "arrest"), ("didn't give", "notice"),
            ("straight away", "arrested"), ("same night", "arrested"),
            ("same day", "arrested"), ("directly arrested",),
            ("didn't record", "reasons"), ("no reasons", "recorded"),
            ("arrested", "before", "show"), ("arrested", "couldn't", "show"),
            ("arrest", "not necessary"), ("should have", "notice"),
        ],
        "context_note": (
            "In Rakhi Mitra v State of West Bengal, 2025:CHC-AS:1826 the "
            "Calcutta High Court held that where the police arrest a person "
            "for an offence punishable with up to seven years WITHOUT first "
            "serving a Section 35(3) BNSS (formerly Section 41-A CrPC) "
            "notice and without recording why the arrest was necessary, the "
            "arrest violates the mandate of Arnesh Kumar and Satender Kumar "
            "Antil. The consequences it identified: the officer is liable "
            "to departmental action and to be proceeded against for "
            "contempt of court; and, on the facts before it, the Court "
            "quashed the criminal proceedings against the petitioners for "
            "that non-compliance. A person arrested this way can put the "
            "non-service of notice and the absence of recorded reasons "
            "before the Magistrate at the first production."
        ),
        "verified_note": (
            "Para 18 (the Arnesh Kumar consequences holding) and para 21 "
            "(non-compliance found on the case diary) read verbatim in "
            "chunks/rakhi_mitra_and_anr_v_state_of_west_bengal_chunks.json; "
            "both x1 (paras 8/27/29 in this file are duplicated because it "
            "quotes Arnesh Kumar / Satender Kumar Antil inline -- not "
            "used). Citation 2025:CHC-AS:1826. Added 2026-09-08."
        ),
    },
    # ---- right to marry a partner of one's own choice ----------------
    "adult_free_to_marry_of_choice_false_kidnapping_case": {
        "case_key": "lata_singh",
        "paragraph_numbers": [
            "major_free_to_marry_no_offence_made_out",
            "false_criminal_case_is_abuse_of_process",
            "right_of_a_major_to_marry_of_choice_and_police_protection_direction",
        ],
        "opinion_author": None,
        "trigger_groups": [
            ("kidnap", "wife"), ("kidnap", "my wife"), ("kidnap", "my own wife"),
            ("kidnapping", "wife"), ("kidnapped", "wife"),
            ("kidnap", "adult"), ("kidnapping", "adult"), ("kidnapped", "adult"),
            ("kidnap", "she is a major"), ("kidnap", "major"),
            ("married", "against", "wishes"), ("marriage", "against", "family"),
            ("marriage", "against", "wishes"),
            ("inter-caste", "marriage"), ("inter caste", "marriage"),
            ("inter-religious", "marriage"), ("different caste", "marriage"),
            ("her family", "kidnap"), ("her family", "complaint", "married"),
            ("she came with me", "own"), ("came with me", "willingly"),
            ("left with me", "voluntarily"), ("her own free will",),
            ("she", "told the police", "voluntarily"),
            ("honour killing",), ("honor killing",),
            ("366",), ("366a",), ("368",),
            ("elopement",), ("eloped",),
        ],
        "context_note": (
            "In Lata Singh v State of Uttar Pradesh, (2006) 5 SCC 475 the "
            "petitioner's brothers -- furious that she had married outside "
            "her caste -- lodged a false kidnapping report against her "
            "husband and his relatives, several of whom were arrested and "
            "jailed. The Supreme Court held: an adult woman is a major and "
            "is 'free to marry anyone she likes or live with anyone she "
            "likes'; there is no bar to an inter-caste marriage; and on "
            "those facts 'we cannot see what offence was committed by the "
            "petitioner, her husband or her husband's relatives'. It "
            "quashed the entire criminal case as 'an abuse of the process "
            "of the Court' brought only because she married outside her "
            "caste, and directed the police across the country to protect "
            "such couples from harassment, threats and violence and to "
            "proceed instead against those who harass them. The right of "
            "two consenting adults to marry a partner of their own choice "
            "has since been affirmed as part of Article 21 (Shafin Jahan v "
            "Asokan K.M.; Shakti Vahini v Union of India)."
        ),
        "verified_note": (
            "Slugs 'major_free_to_marry_no_offence_made_out', "
            "'false_criminal_case_is_abuse_of_process' and "
            "'right_of_a_major_to_marry_of_choice_and_police_protection_"
            "direction' seeded + verbatim-verified from IK doc 1364215 "
            "(seed_lata_singh.py) 2026-09-08 into "
            "chunks/lata_singh_v_state_of_uttar_pradesh_chunks.json; "
            "embedded into corpus_embeddings.json the same day. Citation "
            "(2006) 5 SCC 475."
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
    "bhajan_lal_seven_categories_for_quashing_an_fir": {
        # The standalone State of Haryana v Bhajan Lal judgment is NOT a
        # separate file in this corpus; its seven categories are captured
        # verbatim (with the "AIR 1992 SC 604" marker in the text) inside
        # the Usha Chakraborty chunk, which is where this anchor points.
        "case_key": "usha_chakraborty",
        "paragraph_numbers": ["bhajan_lal_categories_fir_quashing"],
        "opinion_author": None,
        # the chunk lives in the Usha Chakraborty file but its content is
        # the Bhajan Lal test verbatim -- show it under the real source.
        "display_case_name": "State of Haryana v Bhajan Lal",
        "display_citation": "1992 Supp (1) SCC 335 (AIR 1992 SC 604) — as set out in Usha Chakraborty v State of West Bengal",
        "trigger_groups": [
            ("false fir",), ("false case",), ("false complaint",),
            ("fake fir",), ("fabricated", "fir"), ("fabricated", "case"),
            ("quash",), ("quashing",), ("get the fir quashed",),
            ("528 bnss",), ("482 crpc",), ("482 cr.p.c",),
            ("malicious", "prosecution"), ("maliciously", "fir"),
            ("false", "fir", "against me"), ("false", "case", "against me"),
            ("wreak", "vengeance"), ("personal grudge",), ("ulterior motive",),
            ("settle", "score"), ("harass", "false"), ("frame me",), ("framed me",),
            ("civil dispute", "criminal case"), ("civil matter", "criminal case"),
            ("no offence", "made out"), ("does not", "disclose", "offence"),
            # a complaint that on its own facts cannot amount to the offence
            # charged -- Bhajan Lal category 1
            ("kidnap", "my wife"), ("kidnap", "my own wife"),
            ("kidnapping", "wife"), ("kidnapping", "adult"),
            ("kidnap", "adult"), ("kidnapped", "adult"),
            ("married", "against", "wishes"), ("marriage", "against", "family"),
            ("she is an adult", "police"), ("she is a major",),
            ("came with me", "on her own"), ("came with me", "willingly"),
            ("left with me", "voluntarily"), ("her own free will",),
            ("she", "told the police", "voluntarily"),
            ("consenting adult",), ("she consented", "police"),
            ("her family", "complaint", "kidnap"),
        ],
        "context_note": (
            "The High Court's power to quash an FIR or a criminal "
            "proceeding (Section 528 of the BNSS, formerly Section 482 CrPC) "
            "is governed by the seven categories laid down by the Supreme "
            "Court in State of Haryana v Bhajan Lal, 1992 Supp (1) SCC 335 "
            "(AIR 1992 SC 604). In summary, a proceeding may be quashed "
            "where: (1) the allegations, taken at face value, do not make "
            "out any offence; (2)/(3)/(4) the allegations or the material "
            "collected do not disclose a cognizable offence, or disclose "
            "only a non-cognizable one for which no order of a Magistrate "
            "was obtained; (5) the allegations are so absurd and inherently "
            "improbable that no prudent person could find sufficient ground "
            "to proceed; (6) there is an express legal bar to the "
            "proceeding, or a specific, efficacious alternative remedy; or "
            "(7) the proceeding is manifestly attended with mala fides or "
            "is maliciously instituted with an ulterior motive to wreak "
            "vengeance out of a private grudge. The Court also cautioned "
            "that this power is to be exercised sparingly and not to stifle "
            "a legitimate prosecution.\n\n"
            "Category 1 is the one most often engaged where the complaint, "
            "on its own facts, cannot amount to the offence charged -- for "
            "example a 'kidnapping' complaint by a woman's family when the "
            "woman is an ADULT: 'kidnapping from lawful guardianship' under "
            "BNS Section 137 applies only to a child or a person of unsound "
            "mind, and a major's parents are not her 'lawful guardian', so "
            "an adult woman who leaves of her own accord (still more so one "
            "who has married the person and says so to the police) is not "
            "kidnapped in law. Courts have repeatedly protected the right "
            "of two consenting adults to marry a partner of their choice."
        ),
        "verified_note": (
            "The seven categories are quoted verbatim in the chunk slug "
            "'bhajan_lal_categories_fir_quashing' (x1) of "
            "chunks/usha_chakraborty_v_state_of_west_bengal_chunks.json -- "
            "the chunk text itself carries the 'AIR 1992 SC 604' source "
            "marker. Bhajan Lal has no standalone chunk file in this corpus; "
            "get_judgment_doctrine_override attributes the paragraph to "
            "Usha Chakraborty (the containing judgment) with its citation, "
            "and this context_note names Bhajan Lal as the source of the "
            "test. Added 2026-09-08 on user request."
        ),
    },
    "property_dispute_dressed_as_forgery_or_cheating": {
        "case_key": "md_ibrahim",
        "paragraph_numbers": [
            "civil_dispute_criminal_cloak_caution",
            "forgery_false_document_ownership_claim",
        ],
        "opinion_author": None,
        "trigger_groups": [
            ("forgery", "property"), ("forged", "property"),
            ("forgery", "land"), ("forged", "land"),
            ("forgery", "sale deed"), ("forged", "sale deed"),
            ("forgery", "document", "dispute"),
            ("false document", "property"), ("false document", "land"),
            ("forged", "signature", "property"), ("forged", "signature", "land"),
            ("forgery", "ancestral"), ("cheating", "ancestral"),
            ("fir", "property dispute"), ("fir", "land dispute"),
            ("arrested", "property dispute"), ("arrested", "land dispute"),
            ("civil", "property", "criminal"),
        ],
        "context_note": (
            "In Md. Ibrahim v State of Bihar (2009) 8 SCC 751 the Supreme "
            "Court set aside a criminal case arising from a land dispute, "
            "warning against the growing tendency to give a civil dispute "
            "the 'cloak of a criminal offence' to apply pressure. On "
            "forgery, it held that a person who executes a sale deed "
            "claiming that the property is his own -- even if that "
            "ownership claim is wrong or disputed -- does not thereby make "
            "a 'false document': forgery requires making a document "
            "dishonestly purporting to be made by someone who did not make "
            "it, or with a false date, etc. A genuine document containing a "
            "claim later found to be untrue is not a forged document, and a "
            "boundary/title dispute is for the civil court."
        ),
        "verified_note": (
            "Para slugs 'civil_dispute_criminal_cloak_caution' and "
            "'forgery_false_document_ownership_claim' read verbatim in "
            "chunks/md_ibrahim_v_state_of_bihar_chunks.json. Citation "
            "(2009) 8 SCC 751. Added 2026-09-08."
        ),
    },
    # ---- theft: dishonest intention is the ingredient -----------------
    "theft_requires_dishonest_intention": {
        "case_key": "kn_mehra",
        "paragraph_numbers": ["essential_ingredients"],
        "opinion_author": None,
        "trigger_groups": [
            ("theft", "intention"), ("theft", "dishonest"),
            ("stole", "intention"), ("stole", "dishonest"),
            ("theft", "consent"), ("stole", "consent"),
            ("arrested", "theft", "dispute"),
            ("theft", "did not intend"), ("theft", "no intention"),
            ("borrowed", "theft"), ("permission", "theft"),
        ],
        "context_note": (
            "In K.N. Mehra v State of Rajasthan, AIR 1957 SC 369 the Supreme "
            "Court set out the two essential ingredients of theft: (1) the "
            "movable property was moved out of a person's possession WITHOUT "
            "their consent, and (2) the moving was done WITH A DISHONEST "
            "INTENTION at that time. Both must be present. If the person had "
            "consent (express or implied) to take the thing, or genuinely "
            "had no dishonest intention when they took it, the offence of "
            "theft is not made out."
        ),
        "verified_note": (
            "Slug 'essential_ingredients' read verbatim in "
            "chunks/kn_mehra_v_state_of_rajasthan_chunks.json (single "
            "chunk). Citation AIR 1957 SC 369. Added 2026-09-08."
        ),
    },
    "temporary_taking_can_still_be_theft": {
        "case_key": "pyare_lal_bhargava",
        "paragraph_numbers": ["theft_temporary_deprivation"],
        "opinion_author": None,
        "trigger_groups": [
            ("theft", "returned"), ("theft", "gave back"),
            ("theft", "brought back"), ("stole", "returned"),
            ("stole", "gave it back"), ("took", "returned", "theft"),
            ("temporarily", "theft"), ("temporary", "theft"),
            ("borrowed", "theft"), ("meant to return",),
        ],
        "context_note": (
            "In Pyare Lal Bhargava v State of Rajasthan, AIR 1963 SC 1094 "
            "the Supreme Court held that theft does not require permanent "
            "deprivation -- a temporary taking or dispossession is enough, "
            "even where the person intended to return the property later, "
            "because depriving the owner of possession for any period is "
            "'wrongful loss'. So 'I was going to give it back' is not, by "
            "itself, a defence to theft; the questions remain consent and "
            "dishonest intention at the time of taking."
        ),
        "verified_note": (
            "Slug 'theft_temporary_deprivation' read verbatim in "
            "chunks/pyare_lal_bhargava_v_state_of_rajasthan_chunks.json. "
            "Citation AIR 1963 SC 1094. Added 2026-09-08."
        ),
    },
    # ---- cruelty / dowry harassment: over-implication of relatives ----
    "over_implication_of_husbands_relatives_in_cruelty_cases": {
        "case_key": "kahkashan_kausar_sonam",
        "paragraph_numbers": ["18_synthesis", "17_subba_rao_quote"],
        "opinion_author": None,
        "trigger_groups": [
            ("498a", "relatives"), ("498a", "in-laws"), ("498a", "family"),
            ("498a", "parents"), ("498a", "sister"), ("498a", "brother"),
            ("cruelty", "relatives"), ("cruelty", "in-laws"),
            ("cruelty", "husband", "family"),
            ("dowry", "case", "relatives"), ("dowry", "case", "in-laws"),
            ("dowry", "harassment", "relatives"),
            ("85", "relatives"), ("85", "in-laws"),
            ("false", "dowry", "case"), ("false", "498a"),
            ("wife", "case", "my parents"), ("wife", "case", "my family"),
            ("named", "all", "family"), ("distant relative", "dowry"),
        ],
        "context_note": (
            "In Kahkashan Kausar @ Sonam v State of Bihar (2022) 6 SCC 599 "
            "the Supreme Court quashed a Section 498A IPC (cruelty; now "
            "Section 85 BNS) case against the husband's relatives, noting a "
            "consistent line of authority expressing concern about the "
            "'misuse of Section 498A' and the 'tendency of implicating "
            "relatives of the husband in matrimonial disputes' with general "
            "and omnibus allegations. Where the complaint makes only vague, "
            "non-specific allegations against a relative -- no distinct role, "
            "no specific instance of cruelty attributed to that person -- the "
            "proceedings against that relative are liable to be quashed. "
            "This does not dilute a genuine, specific cruelty allegation "
            "against the husband or a named relative."
        ),
        "verified_note": (
            "Slugs '18_synthesis' (the court's own synthesis of the "
            "authorities) and '17_subba_rao_quote' (the K. Subba Rao / "
            "quoted caution) read verbatim in "
            "chunks/kahkashan_kausar_sonam_v_state_of_bihar_chunks.json. "
            "Citation (2022) 6 SCC 599. Added 2026-09-08."
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
    "default_bail_oral_application_enough_and_courts_duty": {
        "case_key": "rakesh_kumar_paul",
        "paragraph_numbers": [
            "40_written_or_oral_application_for_default_bail_is_of_no_consequence",
            "44_court_has_a_duty_to_apprise_the_accused_of_the_right",
        ],
        "opinion_author": None,
        "trigger_groups": [
            ("chargesheet", "days"), ("charge sheet", "days"),
            ("no chargesheet",), ("haven't filed", "chargesheet"),
            ("hasn't filed", "chargesheet"), ("not filed", "chargesheet"),
            ("default bail",), ("statutory bail",),
            ("60 days", "custody"), ("90 days", "custody"),
            ("ninety days",), ("sixty days",),
            ("no lawyer", "chargesheet"), ("cannot afford", "lawyer", "custody"),
        ],
        "context_note": (
            "In Rakesh Kumar Paul v State of Assam (2017) 15 SCC 67 the "
            "Supreme Court held that in matters of personal liberty the "
            "court must not be technical: whether the accused makes a "
            "WRITTEN application for default bail or only an ORAL one is of "
            "no consequence, and once the time limit has passed without a "
            "chargesheet the accused need only indicate they are ready to "
            "furnish bail. It also held it is the DUTY of the court, on "
            "coming to know that an accused before it is entitled to default "
            "bail, to inform them of that indefeasible right. (The case also "
            "held that 'imprisonment for not less than ten years' means the "
            "offence must carry a minimum of ten years for the 90-day limit "
            "to apply -- otherwise the limit is 60 days.)"
        ),
        "verified_note": (
            "Slugs '40_written_or_oral_application_for_default_bail_is_of_no_"
            "consequence' and '44_court_has_a_duty_to_apprise_the_accused_of_"
            "the_right' read verbatim in "
            "chunks/rakesh_kumar_paul_v_state_of_assam_chunks.json. Citation "
            "(2017) 15 SCC 67. Added 2026-09-08. Complements the M. Ravindran "
            "entry above; section-order sort + total cap keep the pair from "
            "flooding a default-bail answer."
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

    # Resolve each matched doctrine to an ordered list of its paragraphs.
    per_doctrine = []
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
        order = {str(pn): i for i, pn in enumerate(entry["paragraph_numbers"])}
        paras.sort(key=lambda pp: order.get(str(pp.get("paragraph_number")), 99))
        per_doctrine.append((entry, paras[:_MAX_PARAGRAPHS_PER_ENTRY]))

    # Round-robin: every matched case contributes its first paragraph before
    # any case contributes its second.
    results, seen = [], set()
    for rank in range(_MAX_PARAGRAPHS_PER_ENTRY):
        for entry, paras in per_doctrine:
            if rank >= len(paras):
                continue
            p = paras[rank]
            sig = (p.get("case_name"), str(p.get("paragraph_number")))
            if sig in seen:
                continue
            seen.add(sig)
            results.append({
                "case_name": entry.get("display_case_name") or p.get("case_name"),
                "citation": entry.get("display_citation") or p.get("citation"),
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
