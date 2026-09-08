"""
scenario_router.py  (Vibeathon Step 2, 2026-09-06)

Route a free-text situation to ONE scenario id.

This is the layer that makes Recourse answer the SITUATION, not the words. It
runs BEFORE retrieval and before any grounded answer, and its only job is
classification:

    "the police have kept my brother 70 days and still haven't filed
     any chargesheet"
        -> {scenario_id: "DEFAULT_BAIL", role: "family", stage: "...",
            offence_hint: "", factors: ["70 days", "no chargesheet"],
            confidence: 0.9}

Design, mirroring related_judgments.decompose_situation:
  - ONE bounded Haiku call, temperature 0 (classification, not generation).
  - Output is constrained to a FIXED ENUM of scenario ids. A hallucinated id
    is rejected and falls through to the deterministic keyword router.
  - Low confidence -> "OUT_OF_SCOPE": the honest "I can't help with this"
    path, never a guessed answer.
  - A pure-Python keyword router (_keyword_route) is BOTH the offline
    fallback (no client / bad JSON / API error) AND the tie-breaker the
    tests run against with no network. Same "trigger group" matching as
    statute_doctrine_map.py.

`factors` are short verbatim-ish phrases the model pulled out (used by
scenario_answer.py to decide which rights fire). They are a convenience signal
only -- the assembler also matches triggers against the raw user message, so a
missed factor never silently drops a right.
"""

import json
import logging
import re

logger = logging.getLogger("scenario_router")

try:
    from main import client
except Exception:
    client = None

_HAIKU_MODEL = "claude-haiku-4-5-20251001"

# The fixed enum. The 5 built scenarios (scenario_spec.SCENARIOS) plus routing
# targets that currently resolve to the closest built scenario until their own
# spec is authored (post-submission). Keep this list and scenario_spec in sync
# for the built ones -- test_scenario_router checks it.
SCENARIO_IDS = [
    # built
    "DEFAULT_BAIL",
    "ARREST_GENERAL",
    "ARREST_WOMAN",
    "FIR_NOT_REGISTERED",
    "SUMMONS_PRE_ARREST",
    "CHEQUE_BOUNCE_NOTICE",
    # routing targets (spec authored post-submission; resolve_target maps them)
    "GROUNDS_NOT_GIVEN",
    "NOT_PRODUCED_24H",
    "CUSTODIAL_VIOLENCE",
    "NO_LAWYER_ACCESS",
    "FIR_COPY_REFUSED",
    "LOC_DETENTION",
    "ITACT_66A",
    "FALSE_FIR_AGAINST_ME",
    "ANTICIPATORY_BAIL",
    # sentinel
    "OUT_OF_SCOPE",
]

# Until their own spec blocks are written, these routing targets are answered
# with the closest built scenario. Deliberately explicit -- not a fuzzy guess.
# The grounds / 24h / custodial-violence / lawyer grievances resolve to
# ARREST_GENERAL, NOT ARREST_WOMAN -- a man arrested for theft must never get
# an answer headed "A woman has been arrested".
_RESOLVE_TARGET = {
    "GROUNDS_NOT_GIVEN": "ARREST_GENERAL",
    "NOT_PRODUCED_24H": "ARREST_GENERAL",
    "CUSTODIAL_VIOLENCE": "ARREST_GENERAL",
    "NO_LAWYER_ACCESS": "ARREST_GENERAL",
    "ANTICIPATORY_BAIL": "SUMMONS_PRE_ARREST",
    "FALSE_FIR_AGAINST_ME": "FIR_NOT_REGISTERED",  # placeholder until hero-3 decision
    "ITACT_66A": "OUT_OF_SCOPE",             # handled by chat_assistant's own override
    "LOC_DETENTION": "OUT_OF_SCOPE",         # handled by statute_doctrine_map override
    "FIR_COPY_REFUSED": "OUT_OF_SCOPE",      # whitelist doctrine; spec pending
}

_MIN_CONFIDENCE = 0.45


def resolve_target(scenario_id: str) -> str:
    """Map a routed id to the scenario that will actually answer it. Built
    ids pass through; unbuilt routing targets resolve to their closest
    built scenario or OUT_OF_SCOPE."""
    return _RESOLVE_TARGET.get(scenario_id, scenario_id)


# ---------------------------------------------------------------------------
# Deterministic keyword router -- offline fallback + test oracle.
# Order matters: the FIRST scenario with a firing group wins, so the most
# specific patterns come first. Same matching as statute_doctrine_map:
# a group fires when every word in it appears somewhere in the message.
# ---------------------------------------------------------------------------
_KEYWORD_ROUTES = [
    ("DEFAULT_BAIL", [
        ("chargesheet",), ("charge sheet",), ("charge-sheet",),
        ("final report",), ("default bail",), ("statutory bail",),
        ("60 days",), ("90 days",), ("sixty days",), ("ninety days",),
        ("days", "no", "chargesheet"), ("days", "still", "custody"),
        ("months", "no", "chargesheet"),
    ]),
    ("CHEQUE_BOUNCE_NOTICE", [
        ("cheque", "bounce"), ("cheque", "bounced"), ("cheque", "dishonour"),
        ("cheque", "returned"), ("138",), ("bounced cheque",),
    ]),
    ("FIR_NOT_REGISTERED", [
        ("won't register",), ("wont register",), ("not registering",),
        ("refuse", "fir"), ("refusing", "fir"), ("register", "my complaint"),
        ("not lodge",), ("won't lodge",), ("no fir",), ("register", "complaint"),
        ("police", "not", "complaint"), ("zero fir",),
    ]),
    ("SUMMONS_PRE_ARREST", [
        ("notice to appear",), ("notice", "41a"), ("section 35", "notice"),
        ("might arrest",), ("going to arrest",), ("about to arrest",),
        ("summon",), ("asking me to come",), ("called to the station",),
        ("anticipatory",), ("afraid", "arrest"), ("fear", "arrest"),
        ("scared", "arrested"),
    ]),
    ("ARREST_WOMAN", [
        ("sister", "arrest"), ("wife", "arrest"), ("daughter", "arrest"),
        ("mother", "arrest"), ("woman", "arrest"), ("women", "arrest"),
        ("she", "arrested"), ("her", "arrested"), ("girl", "arrest"),
        ("nursing mother",), ("lady constable",), ("woman police officer",),
    ]),
    ("CUSTODIAL_VIOLENCE", [
        ("beaten", "custody"), ("beaten", "lockup"), ("beaten", "police station"),
        ("tortured",), ("third degree",), ("slapped", "lockup"),
        ("kept awake",), ("custodial",),
    ]),
    ("ARREST_GENERAL", [
        ("arrested me",), ("i was arrested",), ("i am arrested",),
        ("arrested my brother",), ("arrested my son",), ("arrested my father",),
        ("arrested my husband",), ("arrested my friend",),
        ("police arrested",), ("arrested him",), ("was arrested",),
        ("came to my house", "arrest"), ("directly arrested",),
        ("arrested", "without", "notice"), ("arrested",),
    ]),
    ("NOT_PRODUCED_24H", [
        ("not produced",), ("24 hours", "magistrate"), ("still not", "magistrate"),
        ("days", "not", "magistrate"), ("never produced",),
    ]),
    ("GROUNDS_NOT_GIVEN", [
        ("grounds", "arrest"), ("reason", "arrest", "not"),
        ("didn't tell", "why"), ("not told", "why"), ("no reason", "arrest"),
    ]),
    ("NO_LAWYER_ACCESS", [
        ("not allowed", "lawyer"), ("denied", "lawyer"), ("meet", "lawyer", "not"),
        ("no lawyer",), ("without a lawyer",),
    ]),
    ("FIR_COPY_REFUSED", [
        ("copy", "fir", "not"), ("fir copy",), ("copy of the fir",),
        ("refusing", "copy"),
    ]),
    ("LOC_DETENTION", [
        ("look out circular",), ("lookout circular",), ("lookout notice",),
        ("detained", "airport"), ("detained", "immigration"), ("transit remand",),
        ("stopped at the airport",),
    ]),
    ("ITACT_66A", [
        ("66a",), ("section 66 a",),
    ]),
    ("FALSE_FIR_AGAINST_ME", [
        ("false fir",), ("false case",), ("civil dispute", "fir"),
        ("property dispute", "fir"), ("business dispute", "fir"),
        ("quash",),
    ]),
    ("ANTICIPATORY_BAIL", [
        ("anticipatory bail",), ("pre-arrest bail",), ("before", "arrest", "bail"),
    ]),
]


def _keyword_route(message: str) -> dict:
    low = (message or "").lower()
    for scenario_id, groups in _KEYWORD_ROUTES:
        for group in groups:
            if all(word in low for word in group):
                return {
                    "scenario_id": scenario_id,
                    "role": "",
                    "stage": "",
                    "offence_hint": "",
                    "factors": [],
                    "confidence": 0.6,
                    "via": "keyword",
                    "matched_group": list(group),
                }
    return {
        "scenario_id": "OUT_OF_SCOPE",
        "role": "", "stage": "", "offence_hint": "", "factors": [],
        "confidence": 0.0, "via": "keyword", "matched_group": None,
    }


_ROUTER_PROMPT = """You are a router for a legal-information tool for people in India who are dealing with the police, an arrest, an FIR, or bail. Read the person's message and decide which ONE situation it best fits.

Choose exactly one scenario_id from this fixed list:

- DEFAULT_BAIL: someone is in custody, the investigation is dragging, and the chargesheet / final report has not been filed within the time limit (60 or 90 days).
- ARREST_WOMAN: a WOMAN or girl has been arrested (the arrested person is female - the sender's sister / wife / daughter / mother, or "she" / "her"). Only choose this when the arrested person is clearly a woman.
- ARREST_GENERAL: a person has been arrested (and it is NOT specifically a woman, and NOT specifically a default-bail chargesheet-delay question) - the message is about an arrest that has already happened and any of: grounds of arrest not given, arrested directly without a notice, family not informed, no lawyer, beaten in custody, not produced in 24 hours. This is the default for "the police arrested me / my brother / my son / my father".
- FIR_NOT_REGISTERED: the person is a victim / complainant and the police are refusing or failing to register their FIR for a cognizable offence.
- SUMMONS_PRE_ARREST: the person has NOT been arrested yet - they have (or expect) a notice to appear, or fear an imminent arrest, for an offence punishable with up to 7 years.
- CHEQUE_BOUNCE_NOTICE: a cheque has bounced and the question is about the demand notice / complaint timeline.
- GROUNDS_NOT_GIVEN: someone was arrested and was not told the grounds / reasons for the arrest. (Use ARREST_GENERAL unless grounds-of-arrest is the ONLY issue.)
- NOT_PRODUCED_24H: someone was arrested and has not been produced before a Magistrate within 24 hours.
- CUSTODIAL_VIOLENCE: someone was beaten, tortured, or mistreated in police custody.
- NO_LAWYER_ACCESS: an arrested person is being denied access to a lawyer.
- FIR_COPY_REFUSED: an FIR has been registered but the police will not give a copy of it.
- LOC_DETENTION: someone has been stopped / detained at an airport or border, or there is a Look Out Circular.
- ITACT_66A: someone has been booked under Section 66A of the IT Act.
- FALSE_FIR_AGAINST_ME: an FIR has been filed against the person over what is really a civil / business / family dispute, and they want it quashed.
- ANTICIPATORY_BAIL: the person specifically wants pre-arrest (anticipatory) bail.
- OUT_OF_SCOPE: none of the above fits, OR the message is not about Indian arrest / FIR / police / bail at all, OR there is not enough to tell.

Also extract:
- role: "accused" | "family" (a relative writing about the arrested person) | "complainant" (the victim) | "" if unclear
- stage: a few words on where things stand (e.g. "in custody ~70 days", "not arrested yet", "FIR refused")
- offence_hint: the offence mentioned, if any, in plain words - "" if none
- factors: 2-6 short phrases copied from the message that a lawyer would care about (e.g. "70 days", "no chargesheet", "nursing mother", "arrested at 9 pm", "not named in the FIR"). Copy the words, do not paraphrase.
- confidence: 0.0 to 1.0 - how sure you are of the scenario_id. Use below 0.45 if you are guessing.

Return ONLY this JSON object, nothing else:
{{"scenario_id": "...", "role": "...", "stage": "...", "offence_hint": "...", "factors": ["..."], "confidence": 0.0}}

The person's message:
{message}"""


def _extract_text(response):
    block = next((b for b in getattr(response, "content", []) if hasattr(b, "text")), None)
    if block is None:
        raise ValueError("no text block in response")
    return block.text


def route_situation(message: str) -> dict:
    """Classify `message` into one scenario.

    Returns a dict:
        {scenario_id, role, stage, offence_hint, factors: [str],
         confidence: float, via: "llm" | "keyword" | "llm+keyword"}

    scenario_id is always a member of SCENARIO_IDS. "OUT_OF_SCOPE" is a
    valid, honest result - callers must render the "I can't help with
    this" path, never fall back to a generic answer.

    Never raises. On any failure it returns the deterministic keyword
    route (which itself returns OUT_OF_SCOPE if nothing matches).
    """
    if not message or not message.strip():
        return {"scenario_id": "OUT_OF_SCOPE", "role": "", "stage": "",
                "offence_hint": "", "factors": [], "confidence": 0.0, "via": "empty"}

    kw = _keyword_route(message)

    if client is None:
        return kw

    try:
        response = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=600,
            temperature=0,
            messages=[{"role": "user", "content": _ROUTER_PROMPT.format(message=message)}],
        )
        raw = _extract_text(response).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
    except Exception:
        logger.exception("route_situation: LLM route failed; using keyword route")
        return kw

    sid = parsed.get("scenario_id")
    if sid not in SCENARIO_IDS:
        logger.warning("route_situation: model returned unknown id %r; using keyword route", sid)
        return kw

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    factors = parsed.get("factors")
    if not isinstance(factors, list):
        factors = []
    factors = [str(f).strip() for f in factors if str(f).strip()][:6]

    result = {
        "scenario_id": sid,
        "role": str(parsed.get("role") or "").strip(),
        "stage": str(parsed.get("stage") or "").strip(),
        "offence_hint": str(parsed.get("offence_hint") or "").strip(),
        "factors": factors,
        "confidence": confidence,
        "via": "llm",
    }

    # Low-confidence guard: the model itself is unsure. If the keyword
    # router found something concrete, trust that instead; otherwise be
    # honest and bail.
    if confidence < _MIN_CONFIDENCE and sid != "OUT_OF_SCOPE":
        if kw["scenario_id"] != "OUT_OF_SCOPE":
            kw["factors"] = factors
            kw["role"] = result["role"]
            kw["stage"] = result["stage"]
            kw["offence_hint"] = result["offence_hint"]
            kw["via"] = "llm+keyword"
            return kw
        result["scenario_id"] = "OUT_OF_SCOPE"

    return result
