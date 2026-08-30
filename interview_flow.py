
"""
interview_flow.py

The conversational compliance-check flow: lets a person with NO document
describe their situation in their own words and still get the same
Compliant/Non-Compliant/Cannot Determine verdict machinery the
document-upload flow provides -- by incrementally building the SAME
`fields` dict shape ARREST_EXTRACTION_PROMPT produces, then calling the
SAME run_arrest_compliance_checks(fields) function main.py already has.

ARCHITECTURE NOTE (the whole point of this file): this does NOT introduce
a second way of deciding compliance. Every verdict still comes from
main.py's existing check_* functions, unchanged. This file's only job is
COLLECTING the fields those functions need, through conversation instead
of through PDF extraction -- a second front door into the same
deterministic engine, not a new engine.

SCOPE (2026-08-29): arrest cases only, matching run_arrest_compliance_checks.
Other domains (freeze, search, FIR) can follow this same pattern later --
not built here, since arrest is the most complete compliance domain and
the case that motivated this feature.

FIELD PRIORITY, derived from real check_* function dependencies (see
field_priority_analysis.py for the full reasoning, not repeated here):
    1. sections_cited      -- gates 3 of 8 checks, by far the highest value
    2. arrest_datetime_full -- gates 3 checks
    3. arrestee_gender      -- gates 2 checks with ONE question
    4. offence_date         -- needed alongside #2 for post-facto detection
    5. the 3 independent D.K. Basu yes/no facts -- no dependencies, can
       be asked as a batch
    6. everything else -- later-stage, asked only if the person keeps
       engaging; a "Cannot Determine" outcome on these is still a
       legitimate, useful result, not a failure state

CRITICAL DESIGN DECISION -- OFFENCE IDENTIFICATION NEVER EXPOSES SECTION
NUMBERS TO THE USER. A layperson describing "they said he stole a goat"
does not know or need to know it maps to "BNS Section 303". The
confirmation step asks about the OFFENCE in plain language ("it sounds
like this is being treated as theft -- is that right?"), never the
section number. The section number is purely an internal bookkeeping
detail that sections_cited needs for the compliance engine -- it must
never appear in what the person sees. This was an explicit user
instruction (2026-08-29): "You DO NOT have to explain what is BNS
sections, but then carve out the BNS sections accordingly."

CRITICAL DESIGN DECISION -- OFFENCE CONFIRMATION IS MANDATORY, NEVER
SILENT. Using semantic search's top hit to silently populate
sections_cited would risk a WRONG section driving a REAL compliance
verdict -- a materially higher-stakes use of retrieval than chat's
explanatory use (where a wrong-ish match just means a slightly
imperfect explanation, not a wrong legal classification). Per explicit
user decision (2026-08-29), the offence is ALWAYS confirmed with the
person before being written into fields["sections_cited"].
"""

import logging
import re

logger = logging.getLogger("interview_flow")


def _extract_text_from_response(response):
    """Shared helper: safely extracts the text content from an
    Anthropic API response, regardless of block order or the presence
    of non-text blocks (e.g. ThinkingBlock).

    FIXED 2026-08-29: every call site in this project previously did
    `response.content[0].text`, assuming the first content block is
    always plain text. CONFIRMED REAL FAILURE (in layman_summary.py,
    same bug class): 'ThinkingBlock' object has no attribute 'text' --
    for a sufficiently complex prompt, the model can return a
    ThinkingBlock as the first content item, followed by the actual
    TextBlock. Applied here defensively to every extraction call in
    this file, even though these currently run on Haiku with simple
    prompts less likely to trigger extended thinking -- "hasn't broken
    yet" is not the same as "cannot break," and this fix costs nothing
    to apply proactively.

    Raises:
        ValueError if no text block is found at all -- callers should
        let this propagate to their existing exception handling (it
        will be caught by whatever try/except already wraps the
        messages.create() call), not silently return an empty string.
    """
    text_block = next((block for block in response.content if hasattr(block, "text")), None)
    if text_block is None:
        raise ValueError("No text block found in response.content -- only non-text blocks returned.")
    return text_block.text


# FIELD_PRIORITY split into two explicit tiers, per user direction
# (2026-08-29) after confirming repeatedly this session that an
# 8-9-question interview causes real, confirmed user frustration
# (already observed in the earlier button-based interview mode).
#
# TIER 1 ("fast read"): offence + timing + gender -- the minimum set
# that already produces a genuinely useful, honest, specific briefing
# (confirmed via a real test this session: a 3-field answer set
# produced a correct, specific, well-organized summary quoting real
# statute text and a real Rs. 5,000 threshold, honestly listing
# everything else as unconfirmed). This is now the DEFAULT stopping
# point, not an accident of an early-stop bug.
#
# TIER 2 ("deeper check"): the D.K. Basu safeguards and later-stage
# procedural facts. NEVER asked automatically -- only offered, via an
# explicit button in app.py, after Tier 1 results are shown. The
# person who wants to stop gets a complete, honest, useful answer
# immediately; the person willing to spend more time chooses to
# continue, with full visibility into what they're opting into.
# TIER 1 ("fast read"), REVISED 2026-08-29 per explicit user direction
# to prioritize legal CRITICALITY over convenience. Reasoned from the
# actual check_* functions' own consequences, not just "what's cheap
# to ask":
#
# - 41A_or_35_BNSS_notice_issued_before_arrest: per check_arnesh_kumar_notice,
#   this single fact can flip the ENTIRE case to "May be Non-Compliant"
#   -- the arrest itself may be illegal -- for any offence up to 7
#   years, which is the overwhelming majority of real cases. Arguably
#   the single highest-consequence fact in the whole compliance engine.
# - grounds_of_arrest_in_writing_furnished_to_arrestee: per
#   check_written_grounds, its absence can render the arrest itself
#   illegal under Article 22(1) (Vihaan Kumar), independent of offence
#   type or bail restrictions -- universally applicable, high-consequence.
# - witness_attested_memo: user's own explicit addition -- a basic,
#   universally-applicable D.K. Basu safeguard, not offence- or
#   gender-specific; its absence is a direct, real finding regardless
#   of case type.
# - arrest_datetime_full: kept as necessary SCAFFOLDING (needed to
#   anchor 24-hour production, default bail, and night-arrest
#   calculations) rather than critical in itself -- but without it,
#   several of the above become uncheckable, so it stays in Tier 1.
# - arrestee_gender: kept on cost/value grounds, not dramatic weight --
#   a single word that gates TWO entire checks at once (night-arrest,
#   female-officer-involvement); leaving it to Tier 2 would mean those
#   checks stay permanently unresolved for anyone who stops at Tier 1,
#   for the cost of one extra one-word question. My own addition per
#   the user's invitation to include one more field I judge critical.
#
# offence_date moved to Tier 2 -- it only sharpens post-facto detection
# inside check_arnesh_kumar_notice, a secondary refinement, not a
# primary determination the way the five fields above are.
TIER_1_FIELDS = [
    ("41A_or_35_BNSS_notice_issued_before_arrest", "Before the arrest, did the police send any prior notice asking the person to appear?", "critical"),
    ("grounds_of_arrest_in_writing_furnished_to_arrestee", "Was the person given anything in writing explaining why they were being arrested?", "critical"),
    ("witness_attested_memo", "When the arrest happened, was there a written arrest memo, and did anyone else witness it being made?", "critical"),
    ("arrest_datetime_full", "When exactly did the arrest happen -- do you know the date and roughly what time?", "scaffolding"),
    ("arrestee_gender", "Is the person who was arrested a man, a woman, or do they identify another way?", "scaffolding"),
]

TIER_2_FIELDS = [
    ("offence_date", "And when did the incident itself happen -- the same day as the arrest, or earlier?", "later"),
    ("family_or_friend_informed", "Was a family member or friend told about the arrest at the time?", "dk_basu"),
    ("medical_exam_at_arrest_recorded", "Was the person medically examined around the time of the arrest?", "dk_basu"),
    ("production_datetime_full", "Do you know if and when the person was produced before a magistrate or court?", "later"),
    ("chargesheet_filed_date", "Has a chargesheet been filed in this case yet, and if so, when?", "later"),
]

# Kept for any code that still references the combined list directly
# (e.g. _get_pending_field-style lookups need to search across both
# tiers) -- NOT used to drive question order by itself anymore.
FIELD_PRIORITY = TIER_1_FIELDS + TIER_2_FIELDS

# (MINIMUM_FIELDS_FOR_FIRST_RESULT removed 2026-08-29 -- superseded by
# explicit tiering, see TIER_1_FIELDS/TIER_2_FIELDS above. Results now
# fire deterministically when the active tier is exhausted, not via an
# arbitrary field-count-plus-turn-count heuristic.)


class InterviewState:
    """Holds one conversation's accumulated fields and progress. Created
    fresh per conversation (e.g. stored in Streamlit's st.session_state
    by the caller). Plain data holder -- no persistence logic itself."""

    def __init__(self):
        self.fields = {}
        self.offence_confirmed = False
        self.offence_plain_language = None
        self.questions_asked = set()
        self.turn_count = 0
        self.offence_clarification_attempts = 0
        self.last_asked_field = None
        self.active_tier = 1  # NEW 2026-08-29: 1 = fast-read questions
                               # only, 2 = also asking Tier 2's deeper
                               # procedural questions. Starts at 1;
                               # advanced to 2 only via an explicit
                               # opt-in from the UI layer (app.py's
                               # "check more" button), never
                               # automatically -- see module docstring's
                               # tiering explanation.
        self.tier_1_complete_shown = False  # tracks whether Tier 1
                               # results have already been shown once,
                               # so the UI layer knows whether a
                               # "ready_for_results" return is the
                               # first (Tier 1) or second (Tier 2) pass.

    def known_field_count(self):
        return sum(
            1 for k, v in self.fields.items()
            if k != "sections_cited" and v is not None and v != "unclear"
        )

    def next_question(self):
        """Draws the next question ONLY from the currently active tier
        (TIER_1_FIELDS while active_tier==1, TIER_2_FIELDS once
        advanced to active_tier==2 via explicit user opt-in). Returns
        None once the ACTIVE tier is exhausted -- this is what triggers
        _build_results() to fire, at the end of Tier 1 by default, or
        at the end of Tier 2 if the person opted in.

        Records last_asked_field explicitly before returning, so
        process_turn() knows precisely which field this question's
        answer belongs to -- see this method's prior docstring history
        for the confirmed real bug this replaced (an unordered-set-
        based inference that broke as soon as question order diverged
        from a single fixed list)."""
        active_fields = TIER_1_FIELDS if self.active_tier == 1 else TIER_2_FIELDS
        for field_name, question_text, _group in active_fields:
            if field_name in self.questions_asked:
                continue
            if self.fields.get(field_name) not in (None, "unclear"):
                self.questions_asked.add(field_name)
                continue
            self.questions_asked.add(field_name)
            self.last_asked_field = field_name
            return field_name, question_text
        self.last_asked_field = None
        return None

    def advance_to_tier_2(self):
        """Explicit opt-in, called ONLY from the UI layer when the
        person clicks "check more" after seeing Tier 1 results. Never
        called automatically -- see module docstring."""
        self.active_tier = 2


# ---------------------------------------------------------------------
# Offence identification. See module docstring's two CRITICAL DESIGN
# DECISION blocks -- never expose section numbers to the user, and
# never silently trust a semantic match for a real compliance verdict.
# ---------------------------------------------------------------------

# Minimum similarity score to even OFFER a suggested offence. Below
# this, the semantic match is too weak to responsibly suggest --
# fall back to asking the person to name the offence directly, rather
# than proposing a low-confidence guess and risking anchoring them
# toward something wrong.
#
# CORRECTED 2026-08-29: originally set to 0.45 as an untested, reasoned
# guess ("higher than chat's statute threshold of 0.34, since this
# drives a real verdict, not just an explanation"). CONFIRMED WRONG via
# real testing: "police said my brother stole a goat" -- the EXACT
# phrase this project verified scores 0.3542 for BNS Section 303
# earlier this session -- was rejected by the 0.45 bar, producing a
# dead-end "I want to make sure I get this right" loop with no escape,
# even on repeated tries. This is a genuinely bad failure mode for a
# person in real distress. Lowered to 0.34, matching
# STATUTE_SIMILARITY_THRESHOLD from semantic_retrieval.py -- the
# ORIGINAL reasoning for using a stricter bar here was sound in
# principle (a wrong guess drives a real verdict) but the specific
# number was never tested, and it's better to occasionally confirm a
# slightly-off suggestion (which the person can just say no to) than to
# never make a suggestion strong evidence already supports.
OFFENCE_SUGGESTION_THRESHOLD = 0.34

# After this many consecutive failed offence-identification attempts,
# STOP asking the person to rephrase (which produces the frustrating
# repeated-question loop) and instead offer a manual fallback -- a short
# list of common offence names to pick from directly. Added 2026-08-29
# after a real test showed the original code had NO escape from this
# loop at all.
MAX_OFFENCE_CLARIFICATION_ATTEMPTS = 2


class OffenceIdentificationError(Exception):
    """Raised when offence identification can't proceed at all (e.g.
    semantic search unavailable). Caller should fall back to asking the
    person to state the offence directly in their own words, or name a
    section if they already know it -- never silently skip this step,
    since sections_cited is the single highest-value field."""
    pass


# Deterministic keyword-to-gender mapping for relationship words that
# imply gender in English. ADDED 2026-08-29 per confirmed real user
# feedback: asking "Is the person who was arrested a man, a woman..."
# after the person already said "my brother" reads as not listening.
# Pure keyword matching, NOT an LLM call -- this is a small, fixed,
# unambiguous vocabulary where a deterministic lookup is more reliable
# and cheaper than any model call. Deliberately conservative: only
# words with a single, unambiguous gender implication in standard
# English are included (e.g. "cousin", "sibling", "partner", "spouse"
# are deliberately EXCLUDED since they don't imply a specific gender).
RELATIONSHIP_GENDER_WORDS = {
    "male": ["brother", "husband", "father", "son", "boyfriend", "grandfather",
             "uncle", "nephew", "dad", "papa", "husband's"],
    "female": ["sister", "wife", "mother", "daughter", "girlfriend", "grandmother",
               "aunt", "niece", "mom", "mama", "wife's"],
}


def _infer_gender_from_text(message_text):
    """Deterministic, keyword-based gender inference from relationship
    words in the person's own message (e.g. "my brother" -> male).
    Returns "male", "female", or None if no unambiguous relationship
    word is found -- None means the dedicated gender question should
    still be asked, exactly as before this fix.

    Pure substring matching, no LLM call -- this is a small, fixed
    vocabulary where a deterministic lookup is the right tool, not
    model inference (see RELATIONSHIP_GENDER_WORDS for the exact list
    and why it's deliberately conservative)."""
    message_lower = message_text.lower()
    for gender, words in RELATIONSHIP_GENDER_WORDS.items():
        for word in words:
            # Word-boundary check via surrounding non-letter characters
            # or string edges, to avoid a substring false-positive (e.g.
            # "sonny" should not match "son").
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, message_lower):
                return gender
    return None


OFFENCE_EXTRACTION_PROMPT = """A person is describing a situation involving a police arrest. Extract ONLY the words that describe what OFFENCE or CRIME the person is accused of -- strip away everything about who was arrested, when, or other circumstances.

Examples:
"they arrested my brother last night for theft" -> "theft"
"police said my brother stole a goat" -> "stole a goat"
"he was accused of cheating someone out of money" -> "cheating someone out of money"
"my cousin was arrested, they said it was for hitting someone with a stick" -> "hitting someone with a stick"
"they took him for questioning about a dowry case" -> "dowry case"

If the message doesn't actually describe any offence at all (e.g. it only answers a different question, or is a greeting), respond with "NONE".

Respond with ONLY the extracted phrase, or "NONE" -- no other text, no punctuation, no explanation.

Message: {message}"""


def _extract_offence_phrase(message_text):
    """Internal helper: pulls just the offence-describing words out of a
    full user message, so semantic search runs on a focused phrase
    instead of a full sentence diluted with unrelated words (arrest
    timing, family relationships, etc.) -- see suggest_offence()'s
    docstring for the confirmed real failure this fixes.

    Returns the extracted phrase (str), or None if extraction failed
    (API error) or the model determined no offence is described --
    callers should fall back to using the raw message text in either
    case, not treat this as fatal."""
    try:
        from main import client
    except ImportError:
        client = None

    if client is None:
        return None

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            temperature=0,
            messages=[{
                "role": "user",
                "content": OFFENCE_EXTRACTION_PROMPT.format(message=message_text),
            }],
        )
        extracted = _extract_text_from_response(response).strip()
        if not extracted or extracted.upper() == "NONE":
            return None
        return extracted
    except Exception:
        return None


def suggest_offence(description_text):
    """Given a plain-language description of what the person is accused
    of (e.g. "stole a goat", "hit someone with a stick"), returns a
    SUGGESTED offence for confirmation -- never a silently-trusted fact.

    Reuses semantic_retrieval.py's existing embeddings (the SAME corpus
    used for chat), filtered to statute matches only, since this
    question is specifically "which BNS section" not "what case law is
    relevant" -- judgment matches are irrelevant to this step.

    FIXED 2026-08-29: previously ran semantic_search directly on the
    person's FULL raw message (e.g. "they arrested my brother last
    night for theft"). CONFIRMED REAL FAILURE: this full-sentence query
    matched Section 60 (score 0.3574, an unrelated abetment provision)
    instead of Section 303 (theft) -- surrounding words like "arrested"
    and "last night" diluted the actual offence signal. The bare word
    "theft" alone correctly matched Section 303 at 0.4965 -- a much
    higher, more confident score. This mirrors ARREST_EXTRACTION_PROMPT's
    own established principle: narrow, targeted extraction beats
    dumping a whole raw text at a lookup. Fixed by first extracting
    JUST the offence-describing phrase from the raw message via a
    small, targeted Haiku call, then running semantic search on that
    extracted phrase only, not the full sentence.

    Args:
        description_text: the person's raw message. This function now
            internally extracts the offence-relevant portion before
            searching -- callers do NOT need to pre-extract it
            themselves.

    Returns:
        dict with keys:
            plain_offence_name (str) -- a short, PLAIN-LANGUAGE name for
                the offence (e.g. "theft"), derived from the matched
                section's 'offence' field in BNS_SECTION_DATA, NEVER
                the section number itself.
            section_number (str) -- the actual BNS section. INTERNAL
                USE ONLY -- never surface this in any user-facing text.
            score (float) -- the real similarity score, for logging.
        Returns None if no statute match cleared OFFENCE_SUGGESTION_THRESHOLD.

    Raises:
        OffenceIdentificationError if semantic search itself is
        unavailable (embeddings not set up).
    """
    from semantic_retrieval import semantic_search

    extracted_phrase = _extract_offence_phrase(description_text)
    search_text = extracted_phrase if extracted_phrase else description_text

    results = semantic_search(search_text)
    if results is None:
        raise OffenceIdentificationError(
            "semantic_search returned None -- embeddings unavailable. "
            "Cannot suggest an offence; fall back to asking the person "
            "to name it directly or state a section if they know one."
        )

    statute_results = [r for r in results if r.get("type") == "statute"]
    if not statute_results:
        return None

    best = max(statute_results, key=lambda r: r["score"])
    if best["score"] < OFFENCE_SUGGESTION_THRESHOLD:
        logger.info(
            "suggest_offence: best statute match for %r scored %.3f, "
            "below OFFENCE_SUGGESTION_THRESHOLD=%.2f -- no suggestion offered",
            description_text[:80], best["score"], OFFENCE_SUGGESTION_THRESHOLD
        )
        return None

    section_number = best["section_number"]

    # Pull the real offence description from BNS_SECTION_DATA (the SAME
    # verified table every other part of this project uses) rather than
    # inventing a plain-language label from the raw statute text.
    #
    # FIXED 2026-08-29: BNS_SECTION_DATA keys 239 of 436 entries (55%)
    # by SUBSECTION (e.g. "303(2)"), not the bare top-level number
    # semantic search returns (statute chunks are split at the
    # top-level section boundary only). A direct .get(section_number)
    # on the bare number silently returned None even for "theft" itself
    # (matched section_number="303" at score 0.4965 -- high confidence
    # -- but BNS_SECTION_DATA has no bare "303" key, only "303(2)"),
    # causing plain_offence_name to fall through to the generic "this
    # offence" placeholder every single time, no matter how confident
    # the match. This is the EXACT SAME bug class
    # semantic_retrieval.py's find_relevant_sections() already found
    # and fixed for its own purposes (pulling every subsection variant
    # of a matched bare number) -- reusing that same pattern here
    # instead of the naive direct lookup I originally wrote.
    try:
        from main import BNS_SECTION_DATA
    except ImportError:
        BNS_SECTION_DATA = {}

    exact = BNS_SECTION_DATA.get(section_number)
    subsection_variants = {
        k: v for k, v in BNS_SECTION_DATA.items()
        if k == section_number or k.startswith(f"{section_number}(")
    }
    # Prefer the exact bare-number entry if it exists; otherwise use the
    # FIRST subsection variant found (sorted for determinism) -- good
    # enough for extracting a plain-language OFFENCE NAME, since the
    # offence description is usually near-identical across subsections
    # of the same section (e.g. 303(1) and 303(2) both describe theft;
    # they differ in punishment tier, not in what the offence IS). The
    # actual COMPLIANCE data (cognizable/bailable/max_years) is looked
    # up separately and correctly downstream by run_arrest_compliance_checks
    # itself, which already handles subsection variants properly via
    # its own existing logic -- this function only needs a reasonable
    # NAME for the confirmation prompt, not the full compliance picture.
    section_data = exact
    if section_data is None and subsection_variants:
        first_key = sorted(subsection_variants.keys())[0]
        section_data = subsection_variants[first_key]
    if section_data and section_data.get("offence"):
        raw_offence = section_data["offence"]
        # BNS_SECTION_DATA's "offence" field is often a long, formal
        # clause (e.g. "Whoever, intending to take dishonestly any
        # movable property out of the possession of any person without
        # that person's consent..."). A layperson-facing confirmation
        # needs something short. NOT attempting fancy NLP summarization
        # here -- that would be an LLM making a content judgment outside
        # this file's deterministic scope. Instead: use a short, curated
        # common-name lookup for known sections, falling back to a
        # trimmed version of the raw text (first ~8 words) if no curated
        # name exists yet. This is DELIBERATELY a growing lookup table,
        # not a complete one -- add entries as real sections come up in
        # practice, same incremental-verification discipline as every
        # other data table in this project.
        plain_name = COMMON_OFFENCE_NAMES.get(section_number)
        if plain_name is None:
            words = raw_offence.split()[:8]
            plain_name = " ".join(words).rstrip(",.") + "..."
    else:
        plain_name = f"this offence"  # last-resort, honest but vague

    return {
        "plain_offence_name": plain_name,
        "section_number": section_number,
        "score": best["score"],
    }


# Curated common-name lookup for known BNS sections -- deliberately
# small and growing, NOT auto-generated, since a wrong plain-language
# label shown to a stressed layperson is worse than a slightly awkward
# fallback. Add entries only after confirming the section's real offence
# text against BNS_SECTION_DATA, same verification discipline as every
# other hand-curated table in this project.
COMMON_OFFENCE_NAMES = {
    "303": "theft",
    "303(2)": "theft",
    "318": "cheating",
    "318(1)": "cheating",
    "318(2)": "cheating",
    "318(3)": "cheating",
    "318(4)": "cheating",
    "109": "attempt to murder",
    "109(1)": "attempt to murder",
    "109(2)": "attempt to murder",
    "101": "murder",
    "115": "voluntarily causing hurt",
    "118": "voluntarily causing hurt by dangerous means",
    "74": "assault or use of criminal force against a woman",
    "80": "dowry death",
    "80(1)": "dowry death",
    "85": "cruelty by husband or relatives",
}


# ---------------------------------------------------------------------
# Field extraction from free-text conversational answers.
# ---------------------------------------------------------------------

FIELD_EXTRACTION_PROMPT = """You are extracting ONE specific fact from a person's plain-language answer during a conversation about a police arrest. Do NOT judge legality. Do NOT infer beyond what is stated. If the answer doesn't actually address the question, or is unclear, respond with "unclear" -- do not guess.

Today's real date is: {today_date}

The question that was asked: {question_text}

The field this field should fill: {field_name}

The person's answer: {answer_text}

Respond with ONLY a valid JSON object in this exact format, no other text:
{{"value": <the extracted value, in the correct type for this field, or "unclear" if the answer doesn't address the question>}}

Field-specific extraction rules:
- Date/time fields (arrest_datetime_full, offence_date, production_datetime_full, chargesheet_filed_date): extract as "DD-MM-YYYY HH:MM" if a time is given, "DD-MM-YYYY" if only a date, or "unclear" if genuinely not stated.
  RELATIVE DATES: since you now know today's real date above, RESOLVE relative phrasing into an absolute date rather than marking it unclear. "Yesterday" = today's date minus 1 day. "Last night" = yesterday's date (assume evening, e.g. 22:00, ONLY if the person's own words don't give a more specific time -- if they say "last night around 10:30pm", use their stated time, not a guessed default). "Two days ago" = today's date minus 2 days. "This morning" = today's date. Only mark "unclear" if the phrasing is genuinely ambiguous (e.g. "a while back", "recently" with no way to pin down even an approximate day) -- a specific relative-day phrase like "yesterday" or "last night" is NOT ambiguous and must be resolved, not rejected.
- arrestee_gender: "male", "female", "third_gender", or "unclear".
- Yes/no fields (witness_attested_memo, family_or_friend_informed, medical_exam_at_arrest_recorded, 41A_or_35_BNSS_notice_issued_before_arrest, grounds_of_arrest_in_writing_furnished_to_arrestee): true, false, or "unclear". A clear "no" or "I don't think so" is false, not unclear -- an honest negative is still information.

Respond with ONLY the JSON object."""


class FieldExtractionError(Exception):
    """Raised when the extraction call itself fails (API error, bad
    JSON). Caller should treat this the same as an "unclear" answer --
    ask again or move on -- never crash the conversation."""
    pass


def extract_field_from_answer(field_name, question_text, answer_text):
    """Extracts ONE field's value from the person's free-text answer to
    ONE specific question. Deliberately single-field, single-question --
    NOT a general free-text parser -- since asking a targeted question
    and extracting a targeted answer is far more reliable than trying to
    parse an open-ended paragraph for multiple facts at once (the same
    lesson ARREST_EXTRACTION_PROMPT already encodes for documents,
    applied here to conversation instead).

    FIXED 2026-08-29: previously had no way to resolve relative dates
    ("yesterday", "last night") into absolute ones, since the prompt
    never told the model what day "today" actually is -- every relative
    phrase was marked "unclear" even when the person gave a perfectly
    specific answer. CONFIRMED REAL FAILURE: "yesterday at around 1030
    pm he was arrested" produced arrest_datetime_full="unclear",
    cascading into check_24_hour_production and check_default_bail both
    reporting "Cannot Determine" despite the person having given a
    genuinely specific, usable answer. Fixed by passing today's real
    date into the prompt and instructing the model to resolve relative
    phrasing against it.

    Args:
        field_name: which field this answer is for (must be a key from
            FIELD_PRIORITY).
        question_text: the exact question that was asked (helps the
            model understand context, e.g. distinguishing "yes" meaning
            different things for different questions).
        answer_text: the person's raw answer.

    Returns:
        The extracted value in its correct type (str, bool, or the
        string "unclear"), matching ARREST_EXTRACTION_PROMPT's existing
        field-value conventions so it drops straight into the same
        fields dict main.py's check_* functions already expect.

    Raises:
        FieldExtractionError if the API call fails or returns
        unparseable JSON. Caller should treat this as "unclear", not
        crash the interview.
    """
    import json
    from datetime import datetime as _dt
    try:
        from main import client
    except ImportError:
        client = None

    if client is None:
        raise FieldExtractionError("No API client available for field extraction.")

    today_date = _dt.now().strftime("%d-%m-%Y (%A)")

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            temperature=0,
            messages=[{
                "role": "user",
                "content": FIELD_EXTRACTION_PROMPT.format(
                    today_date=today_date,
                    question_text=question_text,
                    field_name=field_name,
                    answer_text=answer_text,
                ),
            }],
        )
        raw = _extract_text_from_response(response).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
        return parsed.get("value", "unclear")
    except Exception as e:
        # TEMPORARY DIAGNOSTIC (2026-08-29): print the real exception to
        # the terminal so we can see what's actually failing, since a
        # real live failure occurred (arrestee_gender="woman" raised
        # this twice in a row) that couldn't be reproduced by testing
        # the prompt template in isolation -- the template itself
        # formats correctly, so the failure must be either a real API
        # error or a malformed model response. Remove this print once
        # the real cause is found and fixed.
        import traceback
        print(f"=== FieldExtractionError DIAGNOSTIC for field={field_name!r} answer={answer_text!r} ===")
        traceback.print_exc()
        print("=== END DIAGNOSTIC ===")
        raise FieldExtractionError(f"Field extraction failed for {field_name}: {e}")


# ---------------------------------------------------------------------
# Main turn-by-turn driver. This is the single entry point a UI layer
# (Streamlit app.py) should call once per user message.
# ---------------------------------------------------------------------

def process_turn(state, user_message):
    """Advances the interview by one turn. Call this once per user
    message; it mutates `state` in place (adding to state.fields) and
    returns a dict describing what to show the person next.

    This mirrors chat_assistant.answer_question()'s state-dict pattern
    deliberately, for consistency across this project's conversational
    interfaces -- always a 'state' key the caller switches on, never a
    bare string or exception.

    Args:
        state: an InterviewState instance, persisted by the caller
            across turns (e.g. in Streamlit's st.session_state). This
            function assumes state.turn_count has NOT yet been
            incremented for this turn -- it increments it itself.
        user_message: the person's latest raw message.

    Returns:
        dict with a 'state' key, one of:
            'awaiting_offence'       -- first turn, no offence identified
                                        yet; 'question' holds what to ask
            'confirming_offence'     -- a candidate offence was suggested
                                        from THIS message; 'plain_offence_name'
                                        holds what to show the person,
                                        'question' holds the yes/no
                                        confirmation prompt. Section
                                        number is available internally on
                                        state._pending_section but is
                                        NEVER included in this return
                                        dict's user-facing fields.
            'offence_unclear'        -- no confident offence match found;
                                        'question' asks the person to
                                        describe it differently
            'asking_field'           -- normal mid-interview turn;
                                        'question' holds the next question,
                                        'field_name' holds which field it's for
            'ready_for_results'      -- enough fields are known;
                                        'compliance_result' holds the SAME
                                        dict shape run_arrest_compliance_checks
                                        already returns, 'bail_pathway' holds
                                        compute_bail_pathway_info's result
            'extraction_unavailable' -- API call failed this turn; caller
                                        should show a generic "let's try
                                        that again" message, not crash
    """
    state.turn_count += 1

    # NEW 2026-08-29: on the very FIRST message only (before offence is
    # confirmed and before any field has been asked), check for a
    # relationship word implying gender (e.g. "my brother") and
    # pre-populate arrestee_gender if found -- so the dedicated gender
    # question in TIER_1_FIELDS is naturally skipped by next_question()
    # (which already skips any field with a real, non-"unclear" value).
    # Confirmed real user feedback: asking "is the person a man, woman..."
    # after they already said "my brother" reads as not listening.
    if not state.offence_confirmed and state.fields.get("arrestee_gender") is None:
        inferred_gender = _infer_gender_from_text(user_message)
        if inferred_gender:
            state.fields["arrestee_gender"] = inferred_gender

    # First turn, or offence not yet confirmed: this message is either
    # the initial description, or the person's answer to an offence
    # confirmation/clarification prompt.
    if not state.offence_confirmed:
        pending_section = getattr(state, "_pending_section", None)

        # Real escape hatch: if the person explicitly says they don't
        # know/aren't sure, honor that rather than forcing a guess or
        # looping again. Several checks can still run meaningfully
        # without sections_cited (e.g. check_written_grounds,
        # check_dk_basu_memo, check_night_arrest_of_woman don't need
        # it) -- proceeding with sections_cited left empty is honest,
        # not broken; run_arrest_compliance_checks already handles a
        # missing/unrecognised section with "Cannot Determine" on the
        # checks that specifically need it.
        if _looks_like_dont_know(user_message) and pending_section is None:
            state.fields["sections_cited"] = []
            state.offence_confirmed = True
            state.offence_plain_language = "an offence you're not sure of the exact name for"
            next_field, next_question = state.next_question() or (None, None)
            if next_field is None:
                return _build_results(state)
            return {
                "state": "asking_field",
                "field_name": next_field,
                "question": next_question,
            }

        if pending_section is not None:
            # We already suggested an offence last turn; this message
            # is the person's yes/no (or correction).
            affirmative = _looks_affirmative(user_message)
            if affirmative:
                state.fields["sections_cited"] = [pending_section]
                state.offence_confirmed = True
                state._pending_section = None
                next_field, next_question = state.next_question() or (None, None)
                if next_field is None:
                    return _build_results(state)
                return {
                    "state": "asking_field",
                    "field_name": next_field,
                    "question": next_question,
                }
            else:
                # Not confirmed -- treat this message as a fresh
                # description and try again, rather than silently
                # keeping the wrong section or giving up entirely.
                state._pending_section = None
                return _attempt_offence_identification(state, user_message)

        return _attempt_offence_identification(state, user_message)

    # Offence already confirmed: this message answers the field question
    # that was MOST RECENTLY ASKED, tracked explicitly on
    # state.last_asked_field (see InterviewState.next_question()'s
    # docstring for why the old set-based inference was a real bug).
    pending_field = state.last_asked_field
    if pending_field is None:
        # No outstanding question (shouldn't normally happen if the UI
        # layer only calls this after asking a question) -- just get
        # the next one from the active tier, or show results if the
        # active tier is exhausted.
        next_field, next_question = state.next_question() or (None, None)
        if next_field is None:
            return _build_results(state)
        return {"state": "asking_field", "field_name": next_field, "question": next_question}

    field_name = pending_field
    question_text = next(
        (q for f, q, _g in FIELD_PRIORITY if f == field_name), ""
    )
    try:
        value = extract_field_from_answer(field_name, question_text, user_message)
    except FieldExtractionError:
        return {"state": "extraction_unavailable", "field_name": field_name}

    state.fields[field_name] = value
    state.last_asked_field = None

    # CHANGED 2026-08-29: results now fire exactly when the ACTIVE
    # tier is exhausted -- no arbitrary "minimum fields + turn count"
    # heuristic. Tier 1 (3 fields: timing x2, gender) is the deliberate
    # default stop, per explicit user direction after confirmed real
    # user frustration with longer (8-9 question) interviews. Tier 2
    # only runs at all if the UI layer has called
    # state.advance_to_tier_2() following an explicit person opt-in --
    # this function has no opinion about that decision, it only asks
    # whatever the active tier still has left.
    next_field, next_question = state.next_question() or (None, None)
    if next_field is None:
        return _build_results(state)
    return {"state": "asking_field", "field_name": next_field, "question": next_question}


def _attempt_offence_identification(state, message_text):
    """Internal helper: tries to identify an offence from the given
    text, returning the appropriate turn result.

    FIXED 2026-08-29 (dead-end loop): tracks attempts and offers a
    manual picklist after MAX_OFFENCE_CLARIFICATION_ATTEMPTS.

    FIXED 2026-08-29 (awkward re-confirmation): previously ALWAYS
    asked "is that right?" even when the person's own message already
    contained the exact offence word verbatim (e.g. "arrested my
    brother for theft" -> matched theft -> asked "is that right?" for
    a fact the person just stated in plain English). CONFIRMED REAL
    USER FEEDBACK: this reads as not listening, not as due diligence.
    Fixed with a two-tier confidence check: if the matched offence's
    plain name (or a close variant) appears as a literal substring in
    the person's own message, skip the question entirely and use a
    brief acknowledgment instead -- confirmation is only asked when
    the match came from semantic inference the person didn't
    explicitly state themselves."""
    try:
        suggestion = suggest_offence(message_text)
    except OffenceIdentificationError:
        suggestion = None

    if suggestion is not None:
        state.offence_clarification_attempts = 0
        state._pending_section = suggestion["section_number"]
        state.offence_plain_language = suggestion["plain_offence_name"]

        # Confidence check: did the person's own words already contain
        # the offence name verbatim? If so, they don't need to be
        # asked to confirm what they just said.
        offence_words = suggestion["plain_offence_name"].lower().split()
        message_lower = message_text.lower()
        explicitly_stated = any(word in message_lower for word in offence_words if len(word) > 3)

        if explicitly_stated:
            state.fields["sections_cited"] = [suggestion["section_number"]]
            state.offence_confirmed = True
            state._pending_section = None
            next_field, next_question = state.next_question() or (None, None)
            if next_field is None:
                return _build_results(state)
            return {
                "state": "asking_field",
                "field_name": next_field,
                "question": next_question,
                "acknowledgment": f"Got it -- treating this as {suggestion['plain_offence_name']}.",
            }

        return {
            "state": "confirming_offence",
            "plain_offence_name": suggestion["plain_offence_name"],
            "question": f"It sounds like this is being treated as {suggestion['plain_offence_name']} -- is that right?",
        }

    state.offence_clarification_attempts += 1

    if state.offence_clarification_attempts >= MAX_OFFENCE_CLARIFICATION_ATTEMPTS:
        state.offence_clarification_attempts = 0
        common_names = sorted(set(COMMON_OFFENCE_NAMES.values()))
        options_text = ", ".join(common_names)
        return {
            "state": "offence_unclear",
            "question": (
                f"I'm having trouble matching that to a specific offence automatically. "
                f"Is it one of these: {options_text}? If so, just tell me which one. "
                f"If it's something else entirely, tell me the name of the offence as the "
                f"police described it, and I'll do my best -- or if you're not sure, that's "
                f"okay too, just say so and I'll continue with what we already know."
            ),
        }

    return {
        "state": "offence_unclear",
        "question": "I want to make sure I get this right -- could you describe in a few words what the police said the offence was?",
    }


def _build_results(state):
    """Runs the SAME compliance engine main.py's document-upload flow
    uses, against whatever fields have been collected so far. This is
    the point where this file hands off entirely to existing,
    unchanged, already-tested logic -- nothing about HOW compliance is
    decided is reimplemented here.

    ADDED 2026-08-29: also generates a precise, section-specific
    briefing via layman_summary.py, now including the REAL statute
    text (via retrieval.py's get_statute_section) alongside the
    plain-language explanation -- per explicit user direction that the
    reader should see the actual law, not just a description of it,
    the same "show real text, not just a paraphrase" principle
    chat_assistant.py's format_retrieved_text_for_prompt already
    established for the chat feature. Purely a presentation addition,
    never touching the underlying verdict."""
    from main import run_arrest_compliance_checks, compute_bail_pathway_info, compute_severity
    from layman_summary import generate_layman_summary

    compliance_result = run_arrest_compliance_checks(state.fields)
    bail_pathway = compute_bail_pathway_info(state.fields.get("sections_cited", []))
    severity = compute_severity(compliance_result.get("compliance_checks", []))

    section_number = (state.fields.get("sections_cited") or [None])[0]

    statute_text = None
    if section_number:
        try:
            from retrieval import get_statute_section
            statute_data = get_statute_section("BNS", section_number)
            if statute_data:
                statute_text = statute_data["text"]
        except ImportError:
            pass

    layman_text = generate_layman_summary(
        compliance_result, severity, bail_pathway,
        offence_name=state.offence_plain_language,
        section_number=section_number,
        statute_text=statute_text,
    )

    return {
        "state": "ready_for_results",
        "compliance_result": compliance_result,
        "bail_pathway": bail_pathway,
        "severity": severity,
        "layman_summary": layman_text,
        "statute_text": statute_text,
        "section_number": section_number,
        "fields_known": dict(state.fields),
        "tier_shown": state.active_tier,  # NEW 2026-08-29: tells app.py
                               # whether these results are from Tier 1
                               # (offer the "check more" button) or
                               # Tier 2 (don't -- nothing further to offer).
    }


def _looks_affirmative(text):
    """Simple, deterministic yes/no detection for the offence
    confirmation step -- deliberately NOT an LLM call, since this is a
    binary decision with a small, well-known vocabulary; adding a model
    call here would be unnecessary cost and latency for something this
    simple. Errs toward requiring a clear affirmative -- ambiguous
    responses are treated as "no", which safely triggers a re-ask
    rather than silently accepting an uncertain confirmation for a
    field this consequential."""
    text_lower = text.strip().lower()
    affirmative_words = ("yes", "yeah", "yep", "correct", "right", "that's right", "ya", "haan", "sahi")
    return any(text_lower == w or text_lower.startswith(w + " ") or text_lower.startswith(w + ",") for w in affirmative_words)


def _looks_like_dont_know(text):
    """Deterministic detection of an honest 'I don't know' answer, so
    the conversation can move forward gracefully instead of treating
    uncertainty as a failed extraction to retry. Added 2026-08-29 as
    part of fixing the confirmed dead-end loop in offence
    identification."""
    text_lower = text.strip().lower()
    dont_know_phrases = (
        "i don't know", "i dont know", "not sure", "don't know",
        "dont know", "no idea", "unsure", "i'm not sure", "im not sure",
    )
    return any(phrase in text_lower for phrase in dont_know_phrases)