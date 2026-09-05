
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
        "trigger_groups": [
            ("going", "arrest"),
            ("about", "arrested"),
            ("arrest", "soon"),
            ("anticipatory",),
            ("apprehend", "arrest"),
            ("apprehending", "arrest"),
            ("afraid", "arrest"),
            ("scared", "arrest"),
            ("worried", "arrest"),
            ("fear", "arrest"),
            ("fear", "arrested"),
            ("avoid", "arrest"),
            ("prevent", "arrest"),
            ("before", "arrest", "bail"),
            ("bail", "before", "arrested"),
        ],
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

    matched_keys = match_statute_doctrine(question)
    results = []

    for key in matched_keys:
        entry = STATUTE_DOCTRINE_MAP[key]
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

