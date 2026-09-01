
"""
cheque_bounce_interview_flow.py

Free-text conversational compliance-check flow for cheque-bounce
(Section 138 NI Act) cases. Same architectural pattern as
interview_flow.py (arrest) and freeze_interview_flow.py (bank
freezing) -- persistent state, deterministic field extraction, a
single flat priority list (no tiering needed, 8 fields total, well
under the threshold that caused confirmed real user frustration in
arrest's original 8-9-question design).

NO OFFENCE/SECTION-IDENTIFICATION STEP: unlike arrest (offence named
by the person) or even freeze (inferred from observable facts),
cheque-bounce cases are always about the SAME statutory provision --
Section 138 NI Act. There is nothing to identify or confirm.

Feeds directly into main.py's run_compliance_checks (4 checks: 30-day
window, corrected amount-match, 15-day window, jurisdiction),
explain_debt_presumption_status, and compute_settlement_cost_incentive
-- all built and tested earlier this session against 5 real Supreme
Court judgments.
"""

import logging

logger = logging.getLogger("cheque_bounce_interview_flow")

CHEQUE_FIELD_PRIORITY = [
    ("return_memo_date",
     "When did the bank return or bounce the cheque?"),
    ("notice_date",
     "When was the legal notice sent to you, or when did you receive it?"),
    ("cheque_face_value",
     "What amount was written on the cheque itself?"),
    ("demand_principal_amount",
     "What amount is the notice asking you to pay?"),
    ("payment_window_days_granted",
     "How many days did the notice give you to pay?"),
    ("cheque_was_blank_when_signed",
     "Was the cheque signed and handed over blank, with the amount filled in later by someone else, "
     "or was it fully filled in when it was signed?"),
    ("cheque_presentation_bank_location",
     "In which city or town was the cheque presented for collection -- i.e. where is the bank "
     "branch that tried to process it?"),
    ("complaint_filed_location",
     "In which city or town has the complaint been filed, or is expected to be filed?"),
]


class ChequeBounceInterviewState:
    """Holds one conversation's accumulated cheque-bounce fields and
    progress. Same pattern as InterviewState/FreezeInterviewState."""

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
        for field_name, question_text in CHEQUE_FIELD_PRIORITY:
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


FIELD_EXTRACTION_PROMPT = """You are extracting ONE specific fact from a person's plain-language answer during a conversation about a bounced cheque (Section 138 NI Act case). Do NOT judge legality. Do NOT infer beyond what is stated. If the answer doesn't actually address the question, or is unclear, respond with "unclear" -- do not guess.

Today's real date is: {today_date}

The question that was asked: {question_text}

The field this answer should fill: {field_name}

The person's answer: {answer_text}

Respond with ONLY a valid JSON object in this exact format, no other text:
{{"value": <the extracted value, in the correct type for this field, or "unclear" if the answer doesn't address the question>}}

Field-specific extraction rules:
- return_memo_date, notice_date: extract as "DD-MM-YYYY" if a date is given, or "unclear" if genuinely not stated. RESOLVE relative dates ("yesterday", "last week", "two months ago") against today's real date given above -- do not mark a specific relative phrase as unclear, resolve it. Only mark "unclear" if the phrasing is genuinely ambiguous.
- cheque_face_value, demand_principal_amount: extract just the number if given, or "unclear" if no specific figure is mentioned. Strip currency symbols/commas.
- payment_window_days_granted: extract just the number of days if given, or "unclear".
- cheque_was_blank_when_signed: true (signed blank, filled in later), false (fully filled in when signed), or "unclear".
- cheque_presentation_bank_location, complaint_filed_location: extract the city/town name as plain text if given, or "unclear" if not stated. If the person's own certainty is hedged ("I think", "not sure", "maybe"), extract "unclear" rather than the hedged guess.

Respond with ONLY the JSON object."""


class FieldExtractionError(Exception):
    pass


def _extract_text_from_response(response):
    """Shared defensive helper, same pattern applied across every
    other module this session -- handles ThinkingBlock or any
    non-text content block appearing before the real text block."""
    text_block = next((block for block in response.content if hasattr(block, "text")), None)
    if text_block is None:
        raise ValueError("No text block found in response.content -- only non-text blocks returned.")
    return text_block.text


def extract_field_from_answer(field_name, question_text, answer_text):
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
    except FieldExtractionError:
        raise
    except Exception as e:
        raise FieldExtractionError(f"Field extraction failed for {field_name}: {e}")


def process_turn(state, user_message):
    """Advances the cheque-bounce interview by one turn. Same
    state-dict pattern as the other two flows."""
    state.turn_count += 1

    pending_field = state.last_asked_field
    if pending_field is None:
        next_field, next_question = state.next_question() or (None, None)
        if next_field is None:
            return _build_results(state)
        return {"state": "asking_field", "field_name": next_field, "question": next_question}

    question_text = next((q for f, q in CHEQUE_FIELD_PRIORITY if f == pending_field), "")
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
    """Runs run_compliance_checks (the 4 hard checks) plus BOTH
    informational sidebars -- all built and tested earlier this
    session. NOTE: case_stage is not collected by CHEQUE_FIELD_PRIORITY
    above (a deliberate simplification for the free-text flow, since
    most free-text users describing a fresh situation are pre-trial)
    -- defaults to "pre_trial" unless a future revision adds an
    explicit question for it. Flagged here, not silently assumed."""
    from main import run_compliance_checks, explain_debt_presumption_status, compute_settlement_cost_incentive, compute_severity

    fields_with_defaults = dict(state.fields)
    fields_with_defaults.setdefault("case_stage", "pre_trial")

    compliance_result = run_compliance_checks(fields_with_defaults)
    presumption_info = explain_debt_presumption_status(fields_with_defaults)
    settlement_info = compute_settlement_cost_incentive(fields_with_defaults)
    severity = compute_severity(compliance_result.get("compliance_checks", []))

    return {
        "state": "ready_for_results",
        "compliance_result": compliance_result,
        "presumption_info": presumption_info,
        "settlement_info": settlement_info,
        "severity": severity,
        "fields_known": dict(state.fields),
    }
