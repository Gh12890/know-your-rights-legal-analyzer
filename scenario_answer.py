"""
scenario_answer.py  (Vibeathon Step 2, 2026-09-06)

Assemble one tailored answer for a routed situation.

Input : the user's free-text message.
Output: a structured answer dict -- stage explainer, an ORDERED list of only the
        rights the person's own facts raise, each with real statute text and one
        pinned case; the can / cannot lists; next-24h actions; negation lines;
        the paper Recourse can generate; red flags.

The three things that make this "not a generic chatbot", all implemented here:

  1. TRIGGER-GATED RIGHTS. A Right with `triggers=[]` always fires. A Right with
     triggers fires only when the person's words (message + router factors)
     match one of its trigger groups. So "my sister was arrested last night"
     surfaces the night-arrest right; "my sister was arrested this morning"
     does not -- same scenario, different answer.

  2. SUPPRESSION. A case named once in an answer is not repeated for a second
     right -- the second right keeps its section and plain text but its case
     pin is dropped (with a short "see above" note). One landmark, one mention.

  3. NEGATION. For every negation line whose triggering factor is ABSENT, the
     answer states plainly that the situation does NOT raise that issue. Ruling
     things out is the strongest possible signal that the specific facts were
     understood.

Statute text is pulled live from retrieval.get_statute_section -- never
hardcoded in scenario_spec.py. If a section can't be resolved the right still
shows (plain text + case), just without the quoted provision.

This module makes NO legal-correctness decision the engine doesn't already own.
The plain-language wording comes from scenario_spec.py (a first draft the legal
teammate vets); the case pins are real corpus cases; the statute text is the
project's own verified chunks. No LLM call happens here.
"""

import logging

from scenario_router import route_situation, resolve_target
from scenario_spec import get_scenario, ALWAYS

logger = logging.getLogger("scenario_answer")


def _match_group(group, haystack: str) -> bool:
    return all(word in haystack for word in group)


def _fires(triggers, haystack: str) -> bool:
    """A right/negation with no triggers (ALWAYS) fires unconditionally.
    Otherwise it fires when ANY trigger group fully matches the haystack."""
    if triggers is ALWAYS or not triggers:
        return True
    return any(_match_group(g, haystack) for g in triggers)


def _statute_text(act: str, section: str) -> str:
    if not act or not section:
        return ""
    try:
        from retrieval import get_statute_section
        data = get_statute_section(act, section)
    except Exception:
        logger.exception("scenario_answer: get_statute_section failed for %s %s", act, section)
        return ""
    return (data or {}).get("text", "") or ""


def build_scenario_answer(message: str, *, route: dict = None) -> dict:
    """The Step-2 entry point. `route` can be passed in (e.g. by a test or to
    avoid a second LLM call); otherwise route_situation() is called.

    Returns a dict with a stable shape -- see the keys assembled below.
    `status` is one of:
        "answered"      -- a scenario matched and an answer was assembled
        "out_of_scope"  -- routed to OUT_OF_SCOPE, or to a target with no spec
    """
    route = route or route_situation(message)
    routed_id = route.get("scenario_id", "OUT_OF_SCOPE")
    target_id = resolve_target(routed_id)
    scenario = get_scenario(target_id)

    if scenario is None:
        return {
            "status": "out_of_scope",
            "message": message,
            "routed_id": routed_id,
            "target_id": target_id,
            "confidence": route.get("confidence", 0.0),
            "via": route.get("via", ""),
            "honest_note": (
                "This doesn't look like something Recourse can help with yet. "
                "Recourse covers arrest, FIR, police procedure and bail for the "
                "person a case is happening to -- not this."
            ),
        }

    # The haystack every trigger is matched against: the raw message plus the
    # router's extracted factors, lowercased.
    haystack = " ".join([
        (message or "").lower(),
        " ".join(route.get("factors", [])).lower(),
    ])

    # --- 1. which rights fire ---
    firing = [r for r in scenario.rights if _fires(r.triggers, haystack)]
    if not firing:  # defensive -- every scenario has at least one ALWAYS right
        firing = [r for r in scenario.rights if r.triggers is ALWAYS or not r.triggers]

    # --- 2. suppression: one case, one mention ---
    seen_cases = set()
    rights_out = []
    for r in firing:
        case = r.case
        suppressed = False
        if case:
            if case in seen_cases:
                suppressed = True
            else:
                seen_cases.add(case)
        rights_out.append({
            "plain_text": r.plain_text,
            "section": r.section,
            "act": r.act,
            "section_label": (f"Section {r.section} of the {r.act}"
                              if r.section and r.act else ""),
            "statute_text": _statute_text(r.act, r.section),
            "case": "" if suppressed else case,
            "case_suppressed": suppressed,
            "case_ref": case if suppressed else "",   # named, so the UI can say "see X above"
            "para_hint": "" if suppressed else r.para_hint,
            "in_corpus": r.in_corpus,
            "needs_review": r.review,
            "note": r.note,
        })

    # --- 3. negations: state what the facts do NOT raise ---
    negations_out = [
        {"line": n.line, "needs_review": n.review}
        for n in scenario.negations
        if not any(_match_group(g, haystack) for g in n.absent_triggers)
    ]

    # cases actually cited in THIS answer (after suppression), in order
    cited_cases = [ro["case"] for ro in rights_out if ro["case"]]

    return {
        "status": "answered",
        "message": message,
        "routed_id": routed_id,
        "target_id": target_id,
        "scenario_label": scenario.label,
        "role": route.get("role") or scenario.role,
        "stage": route.get("stage") or scenario.stage,
        "offence_hint": route.get("offence_hint", ""),
        "factors": route.get("factors", []),
        "confidence": route.get("confidence", 0.0),
        "via": route.get("via", ""),
        "stage_explainer": scenario.stage_explainer,
        "rights": rights_out,
        "police_can": scenario.police_can,
        "police_cannot": scenario.police_cannot,
        "next_24h": scenario.next_24h,
        "negations": negations_out,
        "paper_type": scenario.paper_type,
        "red_flags": scenario.red_flags,
        "cited_cases": cited_cases,
        "scenario_case_pool": scenario.cases,
        "needs_review": scenario.review or any(r["needs_review"] for r in rights_out),
    }


# ---------------------------------------------------------------------------
# Plain-text rendering -- for scenario_demo.py and quick inspection. The app
# (Step 4) will render the same dict as HTML with the verification badge.
# ---------------------------------------------------------------------------
def render_text(answer: dict, *, show_statute: bool = False) -> str:
    if answer["status"] == "out_of_scope":
        return (f"[OUT OF SCOPE]  (routed: {answer['routed_id']} -> "
                f"{answer['target_id']}, confidence {answer['confidence']:.2f})\n\n"
                f"{answer['honest_note']}")

    L = []
    L.append(f"SITUATION:  {answer['scenario_label']}")
    L.append(f"  routed {answer['routed_id']} -> {answer['target_id']}  "
             f"(role: {answer['role'] or '?'}, confidence {answer['confidence']:.2f}, "
             f"via {answer['via']})")
    if answer["factors"]:
        L.append(f"  factors: {', '.join(answer['factors'])}")
    L.append("")
    L.append("WHAT THIS MEANS")
    L.append("  " + answer["stage_explainer"])
    L.append("")

    L.append("YOUR RIGHTS RIGHT NOW")
    for i, r in enumerate(answer["rights"], 1):
        L.append(f"  {i}. {r['plain_text']}")
        tag = []
        if r["section_label"]:
            tag.append(r["section_label"])
        if r["case"]:
            tag.append(f"{r['case']}" + (f" ({r['para_hint']})" if r["para_hint"] else ""))
        elif r["case_suppressed"]:
            tag.append(f"(see {r['case_ref']} above)")
        if tag:
            L.append(f"       - {'  |  '.join(tag)}")
        if r["in_corpus"] is False:
            L.append("       - [!] case not yet in corpus - Step 3 top-up")
        if show_statute and r["statute_text"]:
            snippet = r["statute_text"].strip().replace("\n", " ")
            L.append(f"       > {snippet[:300]}{'...' if len(snippet) > 300 else ''}")
    L.append("")

    if answer["negations"]:
        L.append("WHAT YOUR SITUATION DOES NOT RAISE")
        for n in answer["negations"]:
            L.append(f"  - {n['line']}")
        L.append("")

    L.append("WHAT THE POLICE CAN DO")
    for c in answer["police_can"]:
        L.append(f"  - {c}")
    L.append("")
    L.append("WHAT THE POLICE CANNOT DO")
    for c in answer["police_cannot"]:
        L.append(f"  - {c}")
    L.append("")

    L.append("NEXT 24 HOURS")
    for a in answer["next_24h"]:
        L.append(f"  - {a}")
    L.append("")

    if answer["red_flags"]:
        L.append("SEE A LAWYER IMMEDIATELY IF")
        for rf in answer["red_flags"]:
            L.append(f"  - {rf}")
        L.append("")

    L.append(f"DOCUMENT RECOURSE CAN PREPARE:  {answer['paper_type']}")
    L.append(f"CASES CITED IN THIS ANSWER:  {', '.join(answer['cited_cases']) or '(none)'}")
    if answer["needs_review"]:
        L.append("\n[legal teammate: this scenario has lines flagged review=True]")
    return "\n".join(L)
