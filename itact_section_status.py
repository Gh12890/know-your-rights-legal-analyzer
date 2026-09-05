
"""
itact_section_status.py

Answers a narrow, separate question from get_statute_section() (real
statute TEXT) and a future ITACT_SECTION_DATA (structured cognizable/
bailable/punishment data, Phase 3b): is this IT Act section still valid
law at all? Section 66A is the reason this file exists -- struck down
as unconstitutional in 2015, yet real search confirms it is still being
used to file FIRs nationwide years later, serious enough that the
Supreme Court issued a dedicated follow-up enforcement order in 2019.

Same discipline as citation_currency.py's GOOD_LAW/SUPERSEDED_BY_STATUTE
pattern (human-curated only -- no code in this file decides validity),
but keyed by "{ACT} {SECTION}" (e.g. "ITACT 66A") instead of
doctrine_key. citation_currency.CITATION_CURRENCY_MAP is architecturally
the wrong place for this (confirmed during Phase 3 planning): it is
keyed 1:1 against retrieval.JUDGMENT_CITATION_MAP's judgment entries,
and its interpreted_provision/successor_provision fields describe "the
provision a CASE construed" -- not "this provision's own status."

STATUS VALUES:
- GOOD_LAW: currently valid, in-force law. Nothing to flag.
- STRUCK_DOWN: held unconstitutional / void by a court with binding
  authority (here, the Supreme Court). Cannot lawfully be invoked at
  all -- distinct from citation_currency.py's SUPERSEDED_BY_STATUTE,
  which describes a provision that was merely RENUMBERED and remains
  fully enforceable under its new number.

NOT_YET_VERIFIED is deliberately never set by a curated entry -- it is
only the default get_itact_section_status() returns for a section with
no curated record, so "nobody has checked this section yet" is always
visible and never silently indistinguishable from "checked, and it's
fine."
"""

import logging
import re

logger = logging.getLogger("itact_section_status")


NOT_YET_VERIFIED = "NOT_YET_VERIFIED"


ITACT_SECTION_STATUS = {
    "ITACT 66A": {
        "status": "STRUCK_DOWN",
        "struck_down_by": {
            "case_name": "Shreya Singhal v Union of India",
            "citation": "(2015) 5 SCC 1",
            "date": "2015-03-24",
        },
        "verified_note": (
            "Struck down as unconstitutional (violates Article 19(1)(a), "
            "held vague and over-broad) in Shreya Singhal v Union of "
            "India, (2015) 5 SCC 1, decided 24 March 2015 -- confirmed "
            "via real web search 2026-09-05 (see the loc-transit-remand-"
            "plan project memory), not recalled from training data. Real "
            "search also confirmed Section 66A is STILL being used to "
            "file FIRs nationwide years after the strike-down -- serious "
            "enough that the Supreme Court issued a dedicated follow-up "
            "enforcement order, PUCL v Union of India (Feb 2019), "
            "directing States/UTs and High Courts to close existing "
            "Section 66A cases and stop registering new ones; reporting "
            "as recent as 2019-2024 confirms continued misuse despite "
            "that order. NOT yet backed by a corpus.json entry for "
            "Shreya Singhal itself (planned as Phase 3c) -- this status "
            "entry currently rests on the web-search verification only, "
            "flagged honestly here rather than overstated as fully "
            "corpus-sourced."
        ),
        "user_facing_note": (
            "Section 66A of the IT Act was struck down as unconstitutional "
            "by the Supreme Court in 2015 (Shreya Singhal v Union of "
            "India). It cannot lawfully be used to charge anyone. The "
            "Supreme Court has since directed police and courts nationwide "
            "to close any case still relying on it -- if this section is "
            "cited against you, that is a strong, well-established ground "
            "to challenge the case."
        ),
        "last_checked_date": "2026-09-05",
    },
}


def get_itact_section_status(section_number: str, act: str = "ITACT") -> dict:
    """Main entry point. Returns the validity-status record for an IT Act
    section.

    NEVER returns None and never raises for an unknown section -- absence
    of a curated record is itself a fact worth surfacing (nobody has
    checked this section's validity yet), not something to hide by
    silently assuming it's fine. Callers should always get a dict with a
    'status' key back.
    """
    key = f"{act} {section_number}".strip()
    entry = ITACT_SECTION_STATUS.get(key)
    if entry is None:
        logger.info(
            "itact_section_status: %r has no curated status record -- "
            "returning explicit NOT_YET_VERIFIED default.",
            key,
        )
        return {
            "status": NOT_YET_VERIFIED,
            "struck_down_by": None,
            "verified_note": (
                "No validity check has been performed yet for this section."
            ),
            "user_facing_note": None,
            "last_checked_date": None,
        }
    return entry


# ---------------------------------------------------------------------------
# Chat-facing trigger detection, Phase 3a of the loc-transit-remand-plan.
#
# WHY THIS IS SEPARATE FROM statute_doctrine_map.py: that module's
# get_statute_doctrine_override() unconditionally calls
# retrieval.get_statute_section(act, section_number) and skips the entry
# entirely if that returns None -- correct for a still-valid section
# whose real text should ground the answer, but WRONG here. Section 66A
# has no real "current" text to show (that is the whole point -- it is
# void), and no ITACT chunk file exists yet (that is Phase 3b's job).
# Reusing that path would either silently produce nothing, or wrongly
# imply 66A is a real, currently-applicable provision by fetching text
# for it. This resolver instead builds its own "text" block directly
# from the curated status record -- a short, accurate factual statement
# (not "current statute text") -- so the shape fed to
# format_retrieved_text_for_prompt is the same (act, section_number,
# text, context_note, source), but the content honestly reflects that
# this is a struck-down-status flag, not a live provision.
#
# Regex (word-boundaried), not the naive-substring matching
# statute_doctrine_map.py uses -- deliberately, after that module's own
# "\block" vs "\blook" typo this session went undetected by a unit test
# that passed for the wrong reason. Verified here with tests that
# isolate each pattern with no other field able to satisfy a sibling
# pattern.
# ---------------------------------------------------------------------------
_SECTION_66A_PATTERNS = [
    re.compile(r"\bsection\s*66\s*-?\s*a\b", re.I),
    re.compile(r"\b(it act|information technology act|cyber\s*crime|cyber\s*law)\b.{0,60}\b66\s*-?\s*a\b", re.I),
    re.compile(r"\b66\s*-?\s*a\b.{0,60}\b(it act|information technology act)\b", re.I),
]


def match_66a_mention(question: str) -> bool:
    """True if the question explicitly names Section 66A (any of "Section
    66A", "IT Act 66A", "66A" near "cyber crime/law", etc.), False
    otherwise. Deliberately narrow -- this does NOT try to infer 66A from
    fact-pattern language alone (e.g. "offensive message"), since that
    would risk asserting a specific charge the person never mentioned;
    it only fires when the person (or a document they're quoting) names
    the section themselves."""
    if not question or not question.strip():
        return False
    return any(p.search(question) for p in _SECTION_66A_PATTERNS)


def get_itact_status_override(question: str) -> list:
    """Main chat-facing entry point, mirroring
    statute_doctrine_map.get_statute_doctrine_override()'s call shape and
    return contract so chat_assistant.py can merge this into the same
    statute_overrides list. Returns a list (empty if no 66A mention) of
    dicts shaped like a normal statute match: act, section_number, text,
    context_note, source='curated_override'."""
    if not match_66a_mention(question):
        return []

    record = get_itact_section_status("66A")
    if record["status"] != "STRUCK_DOWN":
        # No curated record (NOT_YET_VERIFIED) -- nothing safe to assert.
        return []

    struck = record["struck_down_by"] or {}
    text = (
        f"Section 66A of the Information Technology Act, 2000 was struck "
        f"down as unconstitutional by the Supreme Court in "
        f"{struck.get('case_name', 'Shreya Singhal v Union of India')}, "
        f"{struck.get('citation', '(2015) 5 SCC 1')}, decided "
        f"{struck.get('date', '24 March 2015')}. It is void and cannot "
        f"lawfully be used to charge anyone."
    )
    return [{
        "act": "ITACT",
        "section_number": "66A",
        "text": text,
        "context_note": record["user_facing_note"],
        "source": "curated_override",
    }]


# ---------------------------------------------------------------------------
# General "this is probably an IT Act matter, but no specific section is
# confirmed" orientation note. Added 2026-09-05 after live user testing of
# the LOC/transit-remand scenario (Chennai Cyber Crime Police, a deleted
# Twitter post) surfaced a real, reported gap: the chat answer discussed
# ONLY BNSS 58/187 (arrest/transit-remand procedure) and said nothing at
# all about the IT Act, even though this exact fact pattern -- an arrest/
# detention/LOC driven by a social-media post that the cyber-crime police
# are investigating -- is precisely the scenario Phase 3 of the
# loc-transit-remand-plan set out to bring into scope.
#
# WHY THIS IS SEPARATE FROM match_66a_mention/get_itact_status_override
# ABOVE, NOT A RELAXATION OF IT: that function is deliberately narrow by
# design (see its own docstring) -- it refuses to infer 66A "from fact-
# pattern language alone... since that would risk asserting a specific
# charge the person never mentioned." This function does NOT relax that:
# it never names a specific section as the one actually charged. It only
# states the general, unavoidably-true fact that a post-driven cyber case
# is ordinarily investigated under the IT Act, 2000 (a body of law, not a
# single section), and separately flags -- conditionally, "if that is the
# section shown" -- that 66A specifically is void law, which is worth
# knowing regardless of which section actually turns out to apply, given
# real search already confirmed 66A is still being misused nationwide
# (see ITACT_SECTION_STATUS above). No new fact is asserted about THIS
# person's case that they did not already supply themselves.
#
# Deliberately fires independently of match_66a_mention -- chat_assistant.py
# decides, at the point it merges statute_overrides, whether a more
# specific ITACT match (66A named explicitly, or a keyword-anchored
# section like hacking/66) already covers the ground, and skips this
# general note when one does, so a specific match is never diluted by a
# vaguer one sitting alongside it.
# ---------------------------------------------------------------------------
_CYBER_AGENCY_PATTERN = re.compile(r"\bcyber\s*(crime|cell|police|wing)\b", re.I)
_ONLINE_CONTENT_PATTERN = re.compile(
    r"\b(post|posted|posting|tweet|tweeted|twitter|facebook|instagram|whatsapp|"
    r"social\s*media|video|photo|picture|message|messaged|comment|commented|"
    r"upload|uploaded|reel|story|blog)\b",
    re.I,
)
_PROCEDURE_OR_ACCUSATION_PATTERN = re.compile(
    r"\b(fir|arrest|arrested|arresting|detain|detained|detention|remand|"
    r"look\s*out\s*circular|lookout\s*circular|complaint|summon|summoned|"
    r"notice|case\s+(has\s+been|was)\s+(filed|registered)|chargesheet)\b",
    re.I,
)


def match_cyber_backstory_no_confirmed_section(question: str) -> bool:
    """True when the question describes an arrest/detention/FIR-shaped
    situation (_PROCEDURE_OR_ACCUSATION_PATTERN) tied to something posted
    online (_ONLINE_CONTENT_PATTERN) that a cyber-crime agency is involved
    with (_CYBER_AGENCY_PATTERN) -- all three, since any one alone is too
    weak a signal (e.g. "cyber cell" alone could be purely informational;
    "posted" alone is not cyber-crime-specific). Does NOT check for an
    explicit section mention itself -- chat_assistant.py's call site
    handles not double-firing alongside a more specific ITACT match."""
    if not question or not question.strip():
        return False
    return bool(
        _CYBER_AGENCY_PATTERN.search(question)
        and _ONLINE_CONTENT_PATTERN.search(question)
        and _PROCEDURE_OR_ACCUSATION_PATTERN.search(question)
    )


def get_cyber_backstory_note(question: str) -> list:
    """Chat-facing entry point, same return contract as
    get_itact_status_override(). Returns a list (empty if the trigger
    doesn't match) with ONE general orientation entry -- deliberately NOT
    tied to a real section_number (there isn't one to confirm), so
    section_number is a short descriptive label rather than a number;
    downstream consumers (_section_act_map, _find_sections_missing_act)
    only ever match REAL digit section numbers extracted from the
    model's own response text, so this label never collides with or is
    mistaken for an actual cited section."""
    if not match_cyber_backstory_no_confirmed_section(question):
        return []

    record = get_itact_section_status("66A")
    text = (
        "This situation involves content posted online (not a fresh "
        "in-person allegation), so the underlying case is ordinarily "
        "investigated under the Information Technology Act, 2000, in "
        "addition to any BNS/BNSS procedure. Exactly which IT Act "
        "section is invoked matters a great deal -- it affects whether "
        "the offence is bailable and how serious the maximum punishment "
        "is. Ask the investigating officer or a lawyer for the FIR or "
        "remand copy, which will state the exact section(s) relied on."
    )
    if record["status"] == "STRUCK_DOWN":
        text += (
            " One specific thing worth knowing regardless: Section 66A "
            "of the IT Act was struck down as unconstitutional by the "
            "Supreme Court in 2015 (Shreya Singhal v Union of India) and "
            "cannot lawfully be used to charge anyone -- if that is the "
            "section shown on the FIR, that alone is a strong, "
            "well-established ground to challenge the case immediately."
        )
    return [{
        "act": "ITACT",
        "section_number": "general orientation",
        "text": text,
        "context_note": None,
        "source": "curated_override",
    }]
