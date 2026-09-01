"""
freeze_interview_flow.py

Free-text conversational compliance-check flow for bank-account
freezing, mirroring interview_flow.py's proven architecture (persistent
state, deterministic field extraction, tiered questions) but adapted
for a genuinely different fact pattern from arrest.

KEY ARCHITECTURAL DIFFERENCE FROM interview_flow.py (2026-08-30):
arrest's free-text flow identifies an OFFENCE via semantic search, then
gates on a confirmation question, because a layperson genuinely knows
and can name what they were accused of ("theft", "cheating"). Freezing
has NO equivalent -- a person whose account is frozen typically does
NOT know which BNSS section was invoked (106 vs 107), because this is
never explained to them in terms they'd recognize. Per explicit user
confirmation: "The user may not know anything about the section of
BNS. He may only know that his account is frozen."

Given this, there is NO offence/section-identification step in this
flow at all. Instead, this flow asks about OBSERVABLE FACTS a
layperson genuinely can report (was a court/Magistrate mentioned, was
a written order shown, was the whole account or a specific amount
frozen) and feeds them into check_freeze_authorization_inferred() --
a new function specifically built to NEVER silently convert an
inferred fact into a confident section citation the person never
actually stated. See check_freeze_authorization_inferred's own
docstring in main.py for the full architectural reasoning.

SCOPE: bank-account freezing only. Does not attempt to identify BNSS
section, since that information is not something the target user
reliably has.
"""

import logging

logger = logging.getLogger("freeze_interview_flow")


FREEZE_FIELD_PRIORITY = [
    ("court_or_magistrate_mentioned",
     "When your account was frozen, did anyone mention a court or a Magistrate being involved -- "
     "for example, papers referring to a judge's order, or someone saying a court had approved this?"),
    ("written_order_shown",
     "Did the bank or police show you, or send you, anything in writing about the freeze -- a "
     "letter, notice, or order of any kind?"),
    ("scope",
     "Was your entire account frozen, or only a specific amount of money held?"),
    ("specific_amount_stated",
     "Do you know the specific amount that's said to be in question -- the amount the freeze is "
     "actually about?"),
    ("account_holder_intimated",
     "How did you first find out the account was frozen -- did someone tell you directly, or did "
     "you only discover it when a payment or withdrawal failed?"),
]

CONDITIONAL_FOLLOWUP_QUESTION = (
    "written_order_mentions_court",
    "Did that letter or notice mention a court order, or did it just say the account was frozen "
    "without explaining why?"
)


class FreezeInterviewState:
    """Holds one conversation's accumulated freeze-related fields and
    progress. Created fresh per conversation, persisted by the caller,
    same pattern as interview_flow.InterviewState."""

    def __init__(self):
        self.fields = {}
        self.questions_asked = set()
        self.last_asked_field = None
        self.turn_count = 0

    def known_field_count(self):
        return sum(
            1 for k, v in self.fields.items()
            if v is not None and v != "unclear"
        )

    def next_question(self):
        """Draws the next question from FREEZE_FIELD_PRIORITY, with a
        special case: if written_order_shown was just answered True,
        the conditional follow-up (written_order_mentions_court) is
        inserted immediately next, before continuing down the normal
        priority list."""
        if (self.fields.get("written_order_shown") is True
                and "written_order_mentions_court" not in self.fields
                and "written_order_mentions_court" not in self.questions_asked):
            field_name, question_text = CONDITIONAL_FOLLOWUP_QUESTION
            self.questions_asked.add(field_name)
            self.last_asked_field = field_name
            return field_name, question_text

        for field_name, question_text in FREEZE_FIELD_PRIORITY:
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


# ---------------------------------------------------------------------
# Field extraction from free-text conversational answers.
# ---------------------------------------------------------------------

FIELD_EXTRACTION_PROMPT = """You are extracting ONE specific fact from a person's plain-language answer during a conversation about a bank account freeze. Do NOT judge legality. Do NOT infer beyond what is stated. If the answer doesn't actually address the question, or is unclear, respond with "unclear" -- do not guess.

The question that was asked: {question_text}

The field this answer should fill: {field_name}

The person's answer: {answer_text}

Respond with ONLY a valid JSON object in this exact format, no other text:
{{"value": <the extracted value, in the correct type for this field, or "unclear" if the answer doesn't address the question>}}

Field-specific extraction rules:
- court_or_magistrate_mentioned, written_order_shown, written_order_mentions_court, account_holder_intimated: true, false, or "unclear". A clear "no" is false, not unclear -- an honest negative is real information. For written_order_mentions_court specifically: if the answer says the notice "just said frozen, no explanation", that is false (no court mentioned), not unclear.
- scope: "entire account", "specific disputed amount", or "unclear" -- based on whether the person describes the WHOLE account being frozen versus only a specific sum being held.
- specific_amount_stated: extract just the number if given (e.g. "200", "5000"), or "unclear" if no specific figure is mentioned.
- For account_holder_intimated specifically: "told directly" by someone who clearly/confidently informed them = true. "discovered via failed payment/ATM/cheque bounce" or similar = false. IMPORTANT: if the person's own answer contains hedging language about their OWN certainty ("not sure", "I don't remember", "I think", "maybe") applied to how or whether they were told, this OVERRIDES any surface keyword match -- extract "unclear" in that case, not true or false. Confirmed real failure: "not sure, my brother told me something but I don't remember exactly" wrongly matched the "told directly" pattern and returned true, when the person was actually expressing genuine uncertainty and this should be "unclear".

Respond with ONLY the JSON object."""


class FieldExtractionError(Exception):
    """Raised when the extraction call itself fails. Caller should
    treat this the same as an "unclear" answer -- ask again or move
    on -- never crash the conversation."""
    pass


def _extract_text_from_response(response):
    """Shared helper: safely extracts text content from an Anthropic
    API response, regardless of block order or the presence of
    non-text blocks (e.g. ThinkingBlock). Same defensive pattern
    already applied across interview_flow.py, layman_summary.py,
    chat_assistant.py, and main.py this session."""
    text_block = next((block for block in response.content if hasattr(block, "text")), None)
    if text_block is None:
        raise ValueError("No text block found in response.content -- only non-text blocks returned.")
    return text_block.text


def extract_field_from_answer(field_name, question_text, answer_text):
    """Extracts ONE field's value from the person's free-text answer to
    ONE specific question. Same single-field, single-question
    discipline as interview_flow.py's equivalent function."""
    import json
    try:
        from main import client
    except ImportError:
        client = None

    if client is None:
        raise FieldExtractionError("No API client available for field extraction.")

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            temperature=0,
            messages=[{
                "role": "user",
                "content": FIELD_EXTRACTION_PROMPT.format(
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
    except FieldExtractionError:
        raise
    except Exception as e:
        raise FieldExtractionError(f"Field extraction failed for {field_name}: {e}")


# ---------------------------------------------------------------------
# Main turn-by-turn driver.
# ---------------------------------------------------------------------

def process_turn(state, user_message):
    """Advances the freeze interview by one turn. Call once per user
    message; mutates `state` in place and returns a dict describing
    what to show next. Same state-dict pattern as
    interview_flow.process_turn() and chat_assistant.answer_question(),
    for consistency across this project's conversational interfaces.

    Returns:
        dict with a 'state' key, one of:
            'awaiting_first_message'  -- not used in practice (first
                                          message always triggers a
                                          question, no confirmation
                                          gate needed for this domain)
            'asking_field'            -- normal mid-interview turn
            'ready_for_results'       -- enough fields collected;
                                          'compliance_result' holds
                                          run_freeze_compliance_checks'
                                          output PLUS the new
                                          check_freeze_authorization_inferred
                                          result appended
            'extraction_unavailable'  -- API call failed this turn
    """
    state.turn_count += 1

    pending_field = state.last_asked_field
    if pending_field is None:
        # First turn: the user's opening message describes their
        # situation in general terms. No specific field extraction is
        # attempted from it (unlike arrest, there's no offence to
        # identify) -- it's simply acknowledged, and the first real
        # question is asked.
        next_field, next_question = state.next_question() or (None, None)
        if next_field is None:
            return _build_results(state)
        return {"state": "asking_field", "field_name": next_field, "question": next_question}

    question_text = next(
        (q for f, q in FREEZE_FIELD_PRIORITY if f == pending_field),
        CONDITIONAL_FOLLOWUP_QUESTION[1] if pending_field == CONDITIONAL_FOLLOWUP_QUESTION[0] else ""
    )
    try:
        value = extract_field_from_answer(pending_field, question_text, user_message)
    except FieldExtractionError:
        return {"state": "extraction_unavailable", "field_name": pending_field}

    state.fields[pending_field] = value
    state.last_asked_field = None

    next_field, next_question = state.next_question() or (None, None)
    if next_field is None:
        return _build_results(state)
    return {"state": "asking_field", "field_name": next_field, "question": next_question}


def _build_results(state):
    """Runs BOTH the existing run_freeze_compliance_checks (for scope
    and holder-intimation, which don't depend on knowing the section)
    AND the new check_freeze_authorization_inferred (for the
    honest, inference-based authorization question) -- combining them
    into one coherent result. Deliberately does NOT call
    check_freeze_107_court_order or check_freeze_magistrate_intimation
    directly, since those require a KNOWN section_invoked value this
    flow never collects -- calling them would require fabricating that
    field, which is exactly the silent-inference risk this whole
    redesign exists to avoid."""
    from main import (
        check_freeze_section_and_scope,
        check_freeze_holder_intimation,
        check_freeze_authorization_inferred,
        compute_severity,
    )

    checks = [
        check_freeze_authorization_inferred(state.fields),
        check_freeze_section_and_scope(state.fields),
        check_freeze_holder_intimation(state.fields),
    ]
    non_compliant = [c for c in checks if c["status"] in ("Non-Compliant", "May be Non-Compliant")]
    if non_compliant:
        overall = f"{len(non_compliant)} procedural concern(s) found or suspected. Freeze may be legally vulnerable."
    else:
        overall = "No defects found in the available checks."

    compliance_result = {"compliance_checks": checks, "overall_assessment": overall}
    severity = compute_severity(checks)

    return {
        "state": "ready_for_results",
        "compliance_result": compliance_result,
        "severity": severity,
        "fields_known": dict(state.fields),
    }
    