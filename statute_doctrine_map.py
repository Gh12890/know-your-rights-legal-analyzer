
"""
statute_doctrine_map.py

Curated keyword-triggered overrides for statute sections that semantic
search under-retrieves, bypassing embedding-score uncertainty for
specific, known, high-stakes gaps -- same spirit as retrieval.py's
JUDGMENT_CITATION_MAP, but shaped for STATUTE sections (via
get_statute_section) rather than judgment paragraphs.

WHY THIS EXISTS (2026-08-28, resuming the original Aug 27 handoff):
The project's own Aug 27 session found and DELIBERATELY DEFERRED a real
gap: BNSS Section 43(5) (the sunset-to-sunrise no-arrest-of-women
safeguard) is genuinely present and correct in the embedded corpus, but
scores only ~0.343 against "arrested at night"-style queries --
essentially indistinguishable from the confirmed-irrelevant score
ceiling (~0.339). The handoff explicitly ruled out two fixes as
understood dead ends: (a) dropping SIMILARITY_THRESHOLD further (would
reintroduce noise across other queries, already tested and rejected
twice), and (b) re-chunking BNSS 43 for a clearer embedding (higher
effort, not guaranteed to help). The handoff's own recommendation,
followed here: a curated doctrine-map entry, consistent with the
existing JUDGMENT_CITATION_MAP pattern, hand-wiring the relevant
phrasing directly to Section 43, bypassing embedding uncertainty for
this specific high-stakes safeguard.

SCOPE NOTE -- READ BEFORE ASSUMING THIS FIXES THE COMPLIANCE CHECK:
This file ONLY affects the CHAT interface's free-text semantic
retrieval (chat_assistant.py's answer_question(), via
semantic_retrieval.py's find_relevant_sections()). It has NOTHING to
do with, and does NOT touch, main.py's check_night_arrest_of_woman(),
which is a SEPARATE, ALREADY-WORKING compliance check in the
document-upload flow. That function was confirmed correct and
unaffected during this session (2026-08-28) -- this file exists solely
because a user typing a free-text question like "can a woman be
arrested at night" into the CHAT feature was getting no useful match,
not because any compliance check was broken.

SEPARATE, NEWLY-DISCOVERED, NOT YET FIXED (2026-08-28): while
investigating this gap, a real accuracy issue was found in
check_night_arrest_of_woman()'s messaging -- it does not mention that
the Madurai Bench of the Madras High Court (Deepa vs. S. Vijayalakshmi
and Others) held this provision DIRECTORY, not mandatory, meaning
non-compliance alone does not automatically make an arrest illegal.
This file's STATUTE_DOCTRINE_MAP entry below DOES include this caveat
in its context_note, since chat responses should state this correctly
even though the older compliance-check function does not yet. Fixing
check_night_arrest_of_woman() itself is a separate, not-yet-actioned
task -- flagged, not silently fixed as a side effect of this file.
"""

import logging

logger = logging.getLogger("statute_doctrine_map")


# Each entry: trigger keyword groups (same "all words in a group must
# appear somewhere in the question" logic proven out and stress-tested
# for doctrine_matcher.py earlier this session -- concept-word matching,
# not exact-phrase matching, since exact phrases were shown to miss
# real user variation) mapped to a statute lookup (act + section_number,
# passed straight to retrieval.py's get_statute_section) plus a
# curated context_note giving the legal nuance a bare statute-text
# lookup wouldn't include on its own.

# "An arrest has actually happened" -- shared by every post-arrest
# safeguard entry so they all fire whether the person writes "I was
# arrested" or "the police arrested my father / brother / son". Keeping
# this in one place stopped the entries drifting apart (a real gap: the
# BNSS 47/35/58/187 blocks were "me"-only and missed "arrested my
# father").
_ARREST_HAPPENED = [
    ("been arrested",), ("was arrested",), ("been arrest",), ("got arrested",),
    ("arrested me",), ("have arrested me",), ("arrested my",), ("arrested our",),
    ("arrested him",), ("arrested her",), ("police arrested",),
    ("taken into custody",), ("taken to custody",), ("in the lock-up",),
    ("in the lockup",), ("in lock-up",), ("in lockup",), ("in the lock up",),
    ("in police custody",), ("police custody",), ("in judicial custody",),
    ("in custody",), ("still in custody",), ("held in custody",),
    ("picked up", "police"), ("remanded",),
    ("arrested", "days"), ("custody", "days"), ("lock-up", "days"),
    ("lockup", "days"), ("detained", "days"),
]

STATUTE_DOCTRINE_MAP = {
    "bnss_482_anticipatory_bail": {
        # WHY (2026-09-02): "i think the police are going to arrest me
        # soon, what can i do" -- anticipatory bail (BNSS 482) is the
        # single most important thing to tell someone facing imminent
        # arrest, yet it does not appear anywhere in the top ~25 semantic
        # matches for this phrasing (the corpus is arrest-PROCEDURE heavy;
        # BNSS 482 is a remedy, framed differently). Before the retrieval
        # block-cap it slipped into answers only because the model
        # volunteered it and "482" happened to survive the grounding net
        # via a concordance-translated CrPC 438 mention in a bail
        # judgment -- luck, not retrieval. This wires it deterministically,
        # same as the 43(5) entry below.
        "act": "BNSS",
        "section_number": "482",
        # Phrase-based, not scatter words: ("going","arrest") used to fire
        # on "onGOING dispute ... ARRESTed my father" -- a case where the
        # person is ALREADY arrested and anticipatory bail is the wrong
        # remedy. get_statute_doctrine_override also suppresses this entry
        # when the message says an arrest has already happened.
        "trigger_groups": [
            ("going to be arrested",), ("going to arrest me",),
            ("about to be arrested",), ("about to arrest me",),
            ("arrest me soon",), ("may be arrested",), ("might be arrested",),
            ("anticipatory bail",), ("anticipatory",), ("pre-arrest bail",),
            ("apprehend", "arrest"), ("apprehending", "arrest"),
            ("afraid", "arrest"), ("scared", "be arrested"),
            ("worried", "be arrested"), ("fear", "being arrested"),
            ("fear of arrest",), ("avoid arrest",), ("prevent my arrest",),
            ("before", "arrest", "bail"), ("bail", "before", "being arrested"),
            ("police are looking for me",), ("threatening to arrest me",),
        ],
        "suppress_if_already_arrested": True,
        "context_note": (
            "BNSS Section 482 is anticipatory bail. When a person has "
            "reason to believe they may be arrested on an accusation of a "
            "NON-BAILABLE offence, they may apply to the High Court or the "
            "Court of Session for a direction that, in the event of arrest, "
            "they be released on bail. It is the main pre-arrest remedy for "
            "someone who fears an imminent or false case.\n\n"
            "Key limits to state honestly: it is available only for "
            "non-bailable offences; the grant is discretionary, not "
            "automatic; and the court can attach conditions (making "
            "yourself available for interrogation, not tampering with "
            "evidence or influencing witnesses, not leaving India without "
            "permission). It does not prevent investigation and does not "
            "erase the case -- it only pre-empts custodial arrest. The "
            "applicant should move promptly once the apprehension of "
            "arrest is concrete, ideally with a lawyer."
        ),
        "verified_note": (
            "BNSS 482 statute text pulled live via get_statute_section "
            "(not hardcoded here). Section 482 = anticipatory bail is the "
            "BNSS re-enactment of CrPC Section 438; correspondence "
            "confirmed against statute_concordance.json. Curated entry "
            "added 2026-09-02 alongside the chat retrieval block-cap, "
            "which exposed that this remedy was reaching answers only by "
            "chance."
        ),
    },
    "bnss_43_5_night_arrest_women": {
        "act": "BNSS",
        "section_number": "43",
        "trigger_groups": [
            ("woman", "arrest", "night"),
            ("women", "arrest", "night"),
            ("woman", "arrested", "night"),
            ("women", "arrested", "night"),
            ("arrest", "sunset"),
            ("arrest", "sunrise"),
            ("arrested", "sunset"),
            ("arrested", "sunrise"),
            ("female", "arrest", "night"),
            ("woman", "night", "police"),
            # a female relation ARRESTED (as a tight phrase, not scattered
            # words -- "she"/"her"/"night" all appear in plenty of male-
            # arrest stories where "she" is a witness and "night" is when
            # HE was taken)
            ("my sister was arrested", "night"), ("my wife was arrested", "night"),
            ("my daughter was arrested", "night"), ("my mother was arrested", "night"),
            ("sister was arrested at night",), ("wife was arrested at night",),
            ("daughter was arrested at night",), ("she was arrested at night",),
            ("she was arrested", "midnight"), ("she was arrested", "after dark"),
            ("arrested my sister", "night"), ("arrested my wife", "night"),
            ("arrested my daughter", "night"), ("arrested her", "night"),
        ],
        "context_note": (
            "BNSS Section 43(5) states: save in exceptional circumstances, "
            "no woman shall be arrested after sunset and before sunrise, "
            "and where such exceptional circumstances exist, a woman "
            "police officer must obtain the prior written permission of a "
            "Judicial Magistrate of the first class before making the "
            "arrest.\n\n"
            "IMPORTANT LEGAL NUANCE: the Madurai Bench of the Madras High "
            "Court (Deepa vs. S. Vijayalakshmi and Others) has held this "
            "provision to be DIRECTORY, not mandatory -- meaning that "
            "failure to follow it does not, by itself, automatically make "
            "an arrest illegal. However, the arresting officer must still "
            "be able to justify any deviation from the rule, and the "
            "safeguard's purpose (preventing abuse of the cover of "
            "darkness) remains the governing principle. This is genuinely "
            "unsettled/context-dependent, not a bright-line rule -- a "
            "person in this situation should still raise the deviation "
            "with a lawyer or the magistrate, since 'directory' does not "
            "mean 'irrelevant'."
        ),
        "verified_note": (
            "Statute text confirmed via multiple independent legal-reference "
            "sources 2026-08-28 (apnilaw.com, barristery.in, law4u.in), "
            "cross-checked for verbatim consistency across all three -- not "
            "a single-source claim. Directory-not-mandatory ruling confirmed "
            "via coverage of Deepa vs. S. Vijayalakshmi and Others "
            "(Madurai Bench, Madras HC) from 2 independent legal-education "
            "sources (shankariasparliament.com, vajiramandravi.com). This "
            "ruling was NOT previously known to this project as of the Aug "
            "27 handoff -- it is new information surfaced this session, not "
            "something the original embedding/chunking work had already "
            "accounted for. Recommend independently verifying the exact "
            "case citation before treating it as settled law, since it was "
            "found via general web search, not sourced/QA'd through this "
            "project's own judgment-corpus pipeline the way the 12 embedded "
            "judgments were."
        ),
    },
    # WHY (2026-09-05, Phase 1 of the loc-transit-remand-plan): a real
    # test scenario -- detained by Immigration at an airport on a Look
    # Out Circular (LOC) issued by another state's police, needing to
    # contest an "upcoming transit remand" -- was traced through the
    # whole chat pipeline and confirmed to hit ZERO deterministic
    # matches anywhere (no offence-keyword anchor, no whitelist topic,
    # no corpus content at all for "transit remand" or "LOC" -- grepped
    # the full codebase). Yet BNSS 58 and 187 already, directly answer
    # this: a person can lawfully be produced before ANY Magistrate
    # within 24 hours (excluding travel time) regardless of that
    # Magistrate's jurisdiction over the actual case (S.58), and that
    # Magistrate may remand them and then forward them to the Magistrate
    # who does have jurisdiction (S.187(2)) -- this pair of sections IS
    # the statutory basis for what is colloquially called a "transit
    # remand". Two entries below (one per section, matching this map's
    # one-section-per-entry shape) rather than one, so both sections'
    # real text reach the answer.
    "bnss_58_transit_production_24_hours": {
        "act": "BNSS",
        "section_number": "58",
        "trigger_groups": [
            ("look", "out", "circular"),
            ("lookout", "circular"),
            ("lookout", "notice"),
            ("transit", "remand"),
            ("detained", "immigration"),
            ("detention", "immigration"),
            ("immigration", "airport"),
            ("detained", "airport"),
        ],
        "context_note": (
            "BNSS Section 58 requires that a person arrested/detained "
            "without a warrant be produced before a Magistrate within 24 "
            "hours -- and this 24-hour period specifically EXCLUDES the "
            "time necessary for the journey from the place of arrest to the "
            "Magistrate's Court. The section explicitly allows this "
            "production before a Magistrate's Court \"whether having "
            "jurisdiction or not\" -- so if someone is detained in one "
            "city/state over a matter being investigated elsewhere (for "
            "example, on a Look Out Circular), the law itself contemplates "
            "producing them before the NEAREST Magistrate first, not "
            "necessarily the one who will eventually try the case. This is "
            "the statutory basis for what is commonly called a \"transit "
            "remand\"."
        ),
        "verified_note": (
            "BNSS 58 text pulled live via get_statute_section (not "
            "hardcoded here), matching the phrase \"whether having "
            "jurisdiction or not\" confirmed directly against the project's "
            "own embedded statute chunk 2026-09-05 -- not a guessed or "
            "recalled paraphrase. Added after a real test scenario (LOC "
            "detention at Delhi IGI Airport, Chennai-issued, contesting a "
            "transit remand) found this exact gap; see the "
            "loc-transit-remand-gap project memory for the full trace."
        ),
    },
    "bnss_187_transit_remand_forwarding": {
        "act": "BNSS",
        "section_number": "187",
        "trigger_groups": [
            ("look", "out", "circular"),
            ("lookout", "circular"),
            ("lookout", "notice"),
            ("transit", "remand"),
            ("detained", "immigration"),
            ("detention", "immigration"),
            ("immigration", "airport"),
            ("detained", "airport"),
        ],
        "context_note": (
            "BNSS Section 187(2) directly covers this situation: a "
            "Magistrate to whom an arrested/detained person is produced may "
            "authorise their detention \"irrespective of whether he has or "
            "has no jurisdiction to try the case\". If that Magistrate has "
            "no jurisdiction over the case and considers further detention "
            "before them unnecessary, the law directs that they \"may order "
            "the accused to be forwarded to a Magistrate having such "
            "jurisdiction\". In practice this IS the transit-remand "
            "mechanism -- a short remand order near the place of detention, "
            "authorising the police to move the person to where the actual "
            "investigation/FIR is based, where the substantive remand and "
            "bail proceedings then continue.\n\n"
            "The standard arrest safeguards remain fully in force at this "
            "stage too: the grounds for the arrest/detention must still be "
            "communicated (BNSS 47), and a relative or friend must still be "
            "informed of the detention and where the person is being held "
            "(BNSS 48). A person facing a transit remand can be represented "
            "by a lawyer at THIS stage -- contesting whether the arrest/"
            "detention itself was validly made, or whether these procedural "
            "safeguards were actually followed, is a genuine, immediate "
            "opportunity, not something that has to wait until reaching the "
            "state where the case is registered."
        ),
        "verified_note": (
            "BNSS 187(2) text pulled live via get_statute_section (not "
            "hardcoded here), matching the \"irrespective of whether he has "
            "or has no jurisdiction\" / \"forwarded to a Magistrate having "
            "such jurisdiction\" language confirmed directly against the "
            "project's own embedded statute chunk 2026-09-05. The BNSS "
            "47/48 cross-references in the context_note were independently "
            "pulled and confirmed the same way, not assumed from the older "
            "IPC/CrPC framing. Added alongside the S.58 entry above for the "
            "same real test scenario; see loc-transit-remand-gap."
        ),
    },
    # WHY (2026-09-08): a real multi-issue user query -- "I've been arrested
    # for cheating and breach of trust ... I've been in the lock-up two days
    # and nobody has shown me the [grounds]" -- was traced through the chat
    # pipeline. classify_scope correctly identified it as being about
    # "arrest procedure, detention beyond 24 hours, and right to see case
    # documents", the offence anchors fired BNS 318 + 316 -- but NOTHING
    # surfaced the core post-arrest safeguards (grounds of arrest, the
    # arrest-necessity rule, 24-hour production, the remand/default-bail
    # limits). The existing BNSS 58/187 entries are gated behind
    # LOC/transit-remand/airport triggers only, and semantic retrieval does
    # not reliably rank these procedure sections for a plain "I've been
    # arrested and held for X days" question -- the same class of gap the
    # 43(5) and 482 entries above exist for. These four entries wire the
    # standard arrest safeguards deterministically for anyone who has
    # ALREADY been arrested and is describing a custody or grounds
    # grievance. get_statute_doctrine_override() dedupes by section, so
    # these never double up with the LOC-specific 58/187 entries above.
    "post_arrest_grounds_of_arrest_bnss_47": {
        "act": "BNSS",
        "section_number": "47",
        "trigger_groups": _ARREST_HAPPENED + [
            ("not told", "why", "arrested"), ("nobody", "why", "arrested"),
            ("no reason", "arrest"), ("grounds", "arrest"),
            ("haven't shown", "why"), ("not shown", "grounds"),
            ("didn't tell", "why", "arrested"),
        ],
        "context_note": (
            "BNSS Section 47 requires that a person arrested without a "
            "warrant be told, immediately, the full grounds of the arrest -- "
            "the actual reasons and the substance of the accusation, not "
            "just a section number. The Supreme Court (Prabir Purkayastha v "
            "State (NCT of Delhi), 2024; and Pankaj Bansal v Union of India, "
            "2023, for PMLA) has held that these grounds must be furnished "
            "IN WRITING, and that a failure to do so vitiates the arrest and "
            "the remand that follows -- the person is entitled to be "
            "released. The grounds must contain enough detail for the person "
            "(and their lawyer) to actually respond and to apply for bail. "
            "Being told only the offence label, or being shown nothing at "
            "all, does not satisfy Section 47. The related right to be told "
            "the arrest has happened and where the person is held (BNSS 48) "
            "runs alongside this."
        ),
        "verified_note": (
            "BNSS 47 text pulled live via get_statute_section (not hardcoded "
            "here). The grounds-of-arrest-in-writing holding is from Prabir "
            "Purkayastha v State (NCT of Delhi) 2024 INSC 414 and Pankaj "
            "Bansal v Union of India (2023) -- both are in this project's "
            "judgment corpus and concordance; the s.47 = old CrPC 50 "
            "correspondence is in statute_concordance.json. Entry added "
            "2026-09-08 after a real user query surfaced that no post-arrest "
            "safeguard was being anchored for someone already in custody."
        ),
    },
    "post_arrest_necessity_and_notice_bnss_35": {
        "act": "BNSS",
        "section_number": "35",
        "trigger_groups": _ARREST_HAPPENED + [
            ("directly arrested",), ("arrested", "without", "notice"),
            ("no notice", "arrest"), ("arrested straight away",),
            ("based only on", "statement"), ("only", "his statement"),
            ("only", "their statement"), ("one-sided",),
        ],
        "context_note": (
            "BNSS Section 35 governs WHEN the police may arrest without a "
            "warrant. For a cognizable offence punishable with up to seven "
            "years (this covers cheating under BNS 318(4), criminal breach "
            "of trust under BNS 316(2), and most property offences), the "
            "officer may arrest only if satisfied that arrest is NECESSARY "
            "for a specific reason -- to stop the person committing a "
            "further offence, for proper investigation, to stop them "
            "tampering with evidence or influencing witnesses, or to ensure "
            "their attendance in court -- and the officer must RECORD those "
            "reasons in writing. Where arrest is not necessary, Section "
            "35(3) requires the police to instead serve a notice to appear "
            "(the notice that codifies Arnesh Kumar v State of Bihar, 2014). "
            "An arrest made without recording why it was necessary is open "
            "to challenge before the Magistrate at the first production, and "
            "the Magistrate is required to record satisfaction that the "
            "Section 35 conditions were met before authorising any further "
            "detention. Section 35(7) adds that for an offence punishable "
            "with under seven years, a person who is infirm or above sixty "
            "is not to be arrested without an officer's written permission."
        ),
        "verified_note": (
            "BNSS 35 text pulled live via get_statute_section (not hardcoded "
            "here). Section 35 is the BNSS re-enactment of CrPC 41/41A "
            "(correspondence in statute_concordance.json); the "
            "arrest-necessity / notice-to-appear doctrine is Arnesh Kumar v "
            "State of Bihar (2014) 8 SCC 273, in this project's corpus. "
            "Entry added 2026-09-08."
        ),
    },
    "post_arrest_24h_production_bnss_58_general": {
        "act": "BNSS",
        "section_number": "58",
        "trigger_groups": _ARREST_HAPPENED + [
            ("two days",), ("three days",), ("2 days",), ("3 days",),
            ("four days",), ("not produced",), ("not been produced",),
            ("haven't been produced",), ("not brought", "court"),
            ("not brought", "magistrate"), ("24 hours", "magistrate"),
            ("twenty-four hours", "magistrate"),
        ],
        "context_note": (
            "BNSS Section 58 states that a person arrested without a warrant "
            "must not be kept in police custody for more than twenty-four "
            "hours (excluding the time needed for the journey to the "
            "Magistrate's Court). Beyond twenty-four hours, continued "
            "custody is lawful only under a Magistrate's remand order made "
            "under BNSS Section 187. If someone has been in a lock-up for "
            "two or three days, either they were produced before a "
            "Magistrate and remanded (in which case there should be a remand "
            "order they are entitled to see) or the twenty-four-hour limit "
            "has been breached -- which is a serious illegality to raise "
            "with the Magistrate and, if needed, by a habeas corpus "
            "petition to the High Court. The clock runs from the arrest, not "
            "from when the police choose to register it."
        ),
        "verified_note": (
            "BNSS 58 text pulled live via get_statute_section. This is a "
            "general-arrest counterpart to the LOC/transit-remand "
            "bnss_58_transit_production_24_hours entry above; "
            "get_statute_doctrine_override() dedupes by section so only one "
            "s.58 block ever reaches an answer. s.58 = CrPC 57 "
            "(concordance). Added 2026-09-08."
        ),
    },
    "post_arrest_remand_default_bail_bnss_187_general": {
        "act": "BNSS",
        "section_number": "187",
        # narrower than the other three: s.187 (remand + default bail) is
        # about what happens AFTER first production, so fire it on ongoing/
        # prolonged custody or a chargesheet-delay signal, not every fresh
        # arrest.
        "trigger_groups": [
            ("been arrested",), ("was arrested",), ("arrested me",),
            ("arrested my",), ("arrested our",), ("police arrested",),
            ("in the lock-up",), ("in the lockup",), ("in lock-up",),
            ("in lockup",), ("in police custody",), ("police custody",),
            ("in judicial custody",), ("in custody",), ("still in custody",),
            ("arrested", "days"), ("custody", "days"), ("lock-up", "days"),
            ("remand",), ("remanded",), ("still investigating",),
            ("no chargesheet",), ("no charge sheet",), ("not filed", "chargesheet"),
            ("haven't filed", "chargesheet"), ("hasn't filed", "chargesheet"),
            ("days", "chargesheet"), ("days", "charge sheet"),
            ("chargesheet", "deadline"), ("default bail",), ("statutory bail",),
        ],
        "context_note": (
            "BNSS Section 187 is the remand provision. A Magistrate may "
            "authorise detention beyond the first twenty-four hours, but "
            "police custody can be sought only in the first fifteen days "
            "(which may be spread across the early part of the period), and "
            "the total custody during investigation cannot exceed sixty "
            "days for most offences, or ninety days where the offence is "
            "punishable with death, life imprisonment, or at least ten "
            "years. If the investigation is not complete and no chargesheet "
            "is filed within that limit, the person is entitled to be "
            "released on bail as of right (\"default\" or \"statutory\" "
            "bail) if they are prepared to furnish bail -- this does not "
            "depend on the merits of the case. At every remand extension the "
            "person must be physically produced before the Magistrate, and "
            "can be represented by a lawyer to oppose further custody."
        ),
        "verified_note": (
            "BNSS 187 text pulled live via get_statute_section. "
            "General-arrest counterpart to bnss_187_transit_remand_"
            "forwarding above; section-level dedupe in "
            "get_statute_doctrine_override() keeps only one s.187 block. "
            "The 60/90-day default-bail rule is s.187(3); default bail as an "
            "indefeasible right is M. Ravindran v DRI (2021) and Bikramjit "
            "Singh v State of Punjab (2020), both in this project's corpus. "
            "Added 2026-09-08."
        ),
    },
    # WHY (2026-09-08): "the police won't register my complaint" is one of
    # the three headline situations this tool is built for, but the chat
    # engine's answer for it leaned on semantic retrieval and came back
    # with the theft-offence law and BNSS 106 (seizure of stolen property)
    # -- directionally right ("move the Magistrate to direct registration")
    # but never citing the sections or the governing judgment. These two
    # entries wire the FIR-registration route deterministically.
    "fir_refusal_registration_duty_bnss_173": {
        "act": "BNSS",
        "section_number": "173",
        "trigger_groups": [
            ("won't register",), ("wont register",), ("will not register",),
            ("not registering",), ("didn't register",), ("did not register",),
            ("refuse", "register"), ("refusing", "register"), ("refused", "register"),
            ("refuse", "fir"), ("refusing", "fir"), ("refused", "fir"),
            ("won't", "fir"), ("wont", "fir"), ("not lodge",), ("won't lodge",),
            ("refusing", "complaint"), ("won't take", "complaint"),
            ("won't", "complaint"), ("wont", "complaint"),
            ("no fir",), ("zero fir",), ("fir", "not", "registered"),
            ("police", "not", "registering"), ("station", "turned me away"),
            ("sent me away",), ("no action", "complaint"),
        ],
        "context_note": (
            "BNSS Section 173(1) makes registration of a First Information "
            "Report MANDATORY once information disclosing a cognizable "
            "offence is given to the officer in charge of a police station. "
            "The Supreme Court held this in Lalita Kumari v Government of "
            "Uttar Pradesh (2014) 2 SCC 1: the police have no discretion to "
            "refuse -- if the information discloses a cognizable offence, an "
            "FIR must be registered; a preliminary enquiry is permitted "
            "only in a narrow set of categories (matrimonial, commercial, "
            "medical negligence, corruption, or an abnormal delay) and even "
            "then must be completed within a fixed period and cannot be "
            "used to sidestep registration. Section 173(3) is the "
            "preliminary-enquiry provision for offences punishable with "
            "three to seven years, with the prior permission of a superior "
            "officer. Section 173(4) gives the complainant a direct remedy "
            "where the officer in charge refuses: send the substance of the "
            "information, in writing and by post, to the Superintendent of "
            "Police, who if satisfied a cognizable offence is disclosed "
            "either investigates or directs an investigation. A woman "
            "complainant in the sexual-offence categories is entitled to "
            "have the information recorded by a woman officer and, in "
            "specified cases, at her residence."
        ),
        "verified_note": (
            "BNSS 173 text pulled live via get_statute_section. s.173 is the "
            "BNSS re-enactment of CrPC 154 (concordance). Lalita Kumari v "
            "Govt of UP (2014) 2 SCC 1 is in this project's judgment corpus "
            "(chunks/lalita_kumari_v_government_of_uttar_pradesh_chunks.json, "
            "seeded 2026-09-08, para 111 holding verbatim-verified). Entry "
            "added 2026-09-08."
        ),
    },
    "fir_refusal_magistrate_direction_bnss_175": {
        "act": "BNSS",
        "section_number": "175",
        "trigger_groups": [
            ("won't register",), ("wont register",), ("will not register",),
            ("not registering",), ("didn't register",), ("did not register",),
            ("refuse", "register"), ("refusing", "register"), ("refused", "register"),
            ("refuse", "fir"), ("refusing", "fir"), ("refused", "fir"),
            ("won't", "fir"), ("not lodge",), ("won't lodge",),
            ("refusing", "complaint"), ("won't take", "complaint"),
            ("no fir",), ("zero fir",), ("fir", "not", "registered"),
            ("sp", "no action"), ("superintendent", "no action"),
            ("magistrate", "register"), ("court", "direct", "fir"),
        ],
        "context_note": (
            "BNSS Section 175(3) is the court route when the police will "
            "not act. A person aggrieved by a refusal to register an FIR, or "
            "by inaction after registration, may -- after first sending the "
            "complaint in writing to the Superintendent of Police under "
            "Section 173(4) -- apply to the Magistrate empowered to take "
            "cognizance. The Magistrate, after considering the application, "
            "the officer's response and hearing the officer, may direct the "
            "police to register and investigate. This is the BNSS successor "
            "to the well-known Section 156(3) CrPC power. The practical "
            "sequence is: (1) written complaint to the station, keep a "
            "copy and get an acknowledgement; (2) if refused, written "
            "complaint by post to the SP under s.173(4); (3) if still no "
            "action, an application to the Magistrate under s.175(3), "
            "usually drafted with a lawyer or with help from the District "
            "Legal Services Authority."
        ),
        "verified_note": (
            "BNSS 175 text pulled live via get_statute_section. s.175(3) is "
            "the BNSS re-enactment of CrPC 156(3) (concordance). Added "
            "2026-09-08 alongside the s.173 entry."
        ),
    },
}


def match_statute_doctrine(question: str) -> list:
    """
    Given a user's free-text question, return statute doctrine entries
    (from STATUTE_DOCTRINE_MAP) whose trigger groups match. Same
    matching logic as doctrine_matcher.py's match_doctrines(): a group
    matches if ALL its words appear anywhere in the question,
    regardless of order/distance -- concept-word matching, not exact
    phrase matching, per this session's earlier finding that exact
    phrases miss real user variation.

    Args:
        question: the user's raw question text, any case.

    Returns:
        List of entry keys (str, matching STATUTE_DOCTRINE_MAP's top
        level keys) that had at least one trigger group match. Empty
        list if nothing matched -- expected and common, not an error.
    """
    if not question or not question.strip():
        return []

    question_lower = question.lower()
    matched_keys = []

    for entry_key, entry in STATUTE_DOCTRINE_MAP.items():
        for group in entry["trigger_groups"]:
            if all(word in question_lower for word in group):
                matched_keys.append(entry_key)
                logger.info(
                    "statute_doctrine_map: matched entry_key=%r on group=%r "
                    "for question=%r",
                    entry_key, group, question[:100]
                )
                break

    return matched_keys


def get_statute_doctrine_override(question: str) -> list:
    """
    Main entry point for chat_assistant.py to call. Given a user's
    question, returns a list of fully-resolved statute override
    results (statute text + curated context note), ready to merge into
    the same retrieved-text pipeline as normal semantic search matches.

    This function calls retrieval.py's get_statute_section() to fetch
    the REAL statute text -- it does not hardcode statute wording here,
    so if the underlying statute chunk data is ever corrected/updated,
    this stays in sync automatically. Only the curated context_note
    (the legal nuance beyond bare text) is hardcoded, since that's
    genuinely curated content, not something retrievable from the
    corpus.

    Returns:
        List of dicts, each with keys: act, section_number, text
        (real statute text from get_statute_section), context_note
        (curated nuance), source ("curated_override" -- so callers can
        distinguish this from a normal semantic match if needed).
        Empty list if no trigger matched, or if get_statute_section()
        returned None for some reason (logged as a warning -- this
        would mean the underlying statute chunk data is missing or
        was restructured, a real problem worth knowing about, not a
        silent failure).
    """
    from retrieval import get_statute_section
    import re as _re

    matched_keys = match_statute_doctrine(question)
    results = []
    seen_sections = set()

    _already_arrested = bool(_re.search(
        r"\b(been arrested|was arrested|got arrested|arrested (me|him|her|my|our)|"
        r"in (police |judicial )?custody|in the lock-?up|taken into custody|"
        r"picked (him|me|us) up|is in jail|remanded)\b",
        question or "", _re.I,
    ))

    for key in matched_keys:
        entry = STATUTE_DOCTRINE_MAP[key]

        if entry.get("suppress_if_already_arrested") and _already_arrested:
            logger.info("statute_doctrine_map: %r suppressed -- the person is "
                        "already arrested, not facing an imminent arrest", key)
            continue

        # Section-level dedupe: two entries can resolve the same section
        # (e.g. the LOC-specific and the general post-arrest BNSS 58/187
        # blocks). Keep the FIRST that matched -- file order puts the more
        # specific LOC entries ahead of the general ones, so an
        # LOC-plus-arrest query keeps the LOC framing and a plain arrest
        # query gets the general one, and neither ever double-anchors.
        sec_key = (entry["act"].upper(), str(entry["section_number"]))
        if sec_key in seen_sections:
            logger.info("statute_doctrine_map: %r resolves already-anchored "
                        "section %s -- skipping the duplicate", key, sec_key)
            continue
        seen_sections.add(sec_key)

        statute_data = get_statute_section(entry["act"], entry["section_number"])

        if statute_data is None:
            logger.warning(
                "statute_doctrine_map: entry_key=%r matched but "
                "get_statute_section(%r, %r) returned None -- statute "
                "chunk data may be missing or restructured. Skipping "
                "this override rather than returning incomplete data.",
                key, entry["act"], entry["section_number"]
            )
            continue

        results.append({
            "act": statute_data["act"],
            "section_number": statute_data["section_number"],
            "text": statute_data["text"],
            "context_note": entry["context_note"],
            "source": "curated_override",
        })

    return results

