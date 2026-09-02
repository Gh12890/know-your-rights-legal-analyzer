
"""
layman_summary.py

Translates a COMPLETED compliance verdict (the output of
run_arrest_compliance_checks, exactly as already used by the
document-upload, button-interview, and free-text-interview flows) into
a warm, offence-specific, plain-language summary for a person under
real stress -- reusing the SAME "explain, never decide" boundary this
entire project already enforces everywhere else.

ARCHITECTURE NOTE (the whole point of this file): this NEVER changes,
re-derives, or second-guesses a single verdict. Every Compliant/
Non-Compliant/Cannot Determine status, every severity score, every
bail pathway -- all of it comes from the SAME deterministic
run_arrest_compliance_checks()/compute_severity()/
compute_bail_pathway_info() functions already used throughout this
project, UNCHANGED. This file's only job is PHRASING an
already-decided result warmly and specifically -- the same boundary
chat_assistant.py's generate_grounded_response() already enforces for
retrieved statute text, applied here to a compliance result instead.

WHY THIS EXISTS (2026-08-29): the existing render_compliance_ui_main()
was built for, and is correctly shaped for, a DIFFERENT audience -- a
duty-lawyer-style structured legal audit (doctrine citations,
paragraph numbers, formal requirement labels like "S.35(3) BNSS notice
before arrest [Arnesh Kumar (2014)...]"). That artifact should still
exist and still be available (e.g. behind a "show full legal
breakdown" expander, or the existing PDF download) -- it is NOT being
removed or replaced. But it is the wrong FIRST thing to show a
stressed layperson mid-conversation, for two confirmed real reasons:
    1. It reads as generic legal template language regardless of the
       actual offence -- nothing in the existing render ever says
       "theft" specifically, even though the underlying checks did
       correctly resolve to Section 303.
    2. It assumes legal literacy a person in crisis often doesn't have
       and shouldn't need, to get a first, orienting answer.

TWO OUTPUTS, ONE COMPUTATION: given the same compliance_result,
severity, and bail_pathway dicts, this module produces a SEPARATE,
warm, offence-named summary alongside (not instead of) the existing
structured render. Both are real, both are correct, both come from the
identical deterministic verdict -- they differ only in audience and
tone, the same "two front doors, one engine" principle
interview_flow.py already established for INPUT collection, now
applied to OUTPUT presentation.
"""

import logging
import re as _re

logger = logging.getLogger("layman_summary")

SONNET_MODEL = "claude-sonnet-5"
HAIKU_MODEL = "claude-haiku-4-5-20251001"


LAYMAN_SUMMARY_PROMPT = """You are briefing a junior lawyer -- someone newly qualified or a law intern, early in practice but not a layperson. They understand legal English, statutory language, and basic procedure, but appreciate a clear, well-organized summary over a dense clause-by-clause audit. Your job is to explain what was found clearly, precisely, and specifically to THIS case -- never generically, and never dumbed down.

CRITICAL RULES:
- Use ONLY the facts given below. Do not add legal information, section numbers, or case names beyond what's provided.
- ALWAYS name both the plain offence AND its section number together wherever relevant (e.g. "theft under Section 303", not just "theft" and not just "Section 303" alone) -- state this clearly near the start and reuse it naturally throughout, not just once.
- If the ACTUAL STATUTE TEXT is provided below, open your briefing by quoting the operative part of it directly (verbatim, in a clearly marked block), THEN explain what it means in plain terms. The reader should see the real law, not just a description of it -- this is a deliberate requirement, not optional context.
- STATE SPECIFIC FACTS AS FACTS, not as things to defer to "a lawyer." If the compliance findings below include a specific numeric threshold, monetary value, time limit, or condition (e.g. a value-based exception, a day-count deadline), STATE IT DIRECTLY AND PRECISELY. CONFIRMED REAL FAILURE (2026-08-29): a previous summary said bail eligibility "depends on details about the underlying offence involved, which needs a lawyer's eye to sort out properly" -- this was technically honest but uselessly vague, when the actual compliance data already contained the specific fact (a Rs. 5,000 value threshold with a return-of-property condition) that should have been stated outright: "for theft under Section 303, if the value involved is under Rs. 5,000 and the property is returned, this becomes bailable at the station; above that, it is non-bailable and a court must decide." The reader is capable of understanding a real statutory threshold -- give it to them, don't gesture around it.
- You may use standard legal terminology (cognizable, bailable, notice, remand, etc.) without stopping to define basic terms -- this reader already knows them. Do not oversimplify language, but DO organize the information clearly: group related findings (e.g. everything about arrest-time safeguards) under a short clear heading rather than either a dense wall of formal citations or an overly casual paragraph.
- Formal case citations (case name, year, court) are fine to include briefly where they add real value (e.g. "the Arnesh Kumar guidelines require...") -- this reader can use them, unlike a layperson audience.
- Be precise and direct about what IS and ISN'T established. "Cannot Determine" findings should be stated as genuinely open questions with WHY they're open (what specific fact is missing) -- not softened into vague reassurance.
- If there are concerning findings (Non-Compliant, May be Non-Compliant), state them clearly and specifically, including which requirement was violated and what the practical consequence is.
- End with the single most useful concrete next step, stated specifically (not "consult a lawyer" -- name the actual missing fact or action that would resolve the most open questions).

The offence involved: {offence_name}

Actual statute text (quote the relevant operative part of this verbatim before explaining it, if provided): {statute_text}

The full compliance findings (translate ALL of this into a clear, organized, precise briefing -- don't skip items, don't vague-out specific facts that are actually present):
{compliance_summary}

Severity assessment: {severity_label}

Bail pathway information (state any specific thresholds or conditions given here directly and precisely): {bail_pathway_message}

Write a clear, precise, well-organized briefing suitable for a junior lawyer reviewing this case for the first time. Roughly 250-350 words, including the quoted statute text."""


# audience="plain" (2026-09-02): the module was reframed for a junior lawyer
# on 2026-08-29, but the UI redesign needs a GENUINE plain-language register
# alongside it -- one on-screen tab for a stressed layperson, another for a
# lawyer. Same computed compliance_result, same "explain never decide"
# boundary; only the phrasing differs.
PLAIN_SUMMARY_PROMPT = """You are explaining a legal situation to an ordinary person who is stressed and has no legal training. They need to understand, in plain words, what happened and what they can do -- not a legal briefing.

CRITICAL RULES:
- Use ONLY the facts in the findings below. Never add a legal rule, a verdict, or a consequence that is not already stated there. Never say something is "illegal" or "unlawful" unless the findings say so in those words.
- NO section numbers. NO case names. NO Latin. NO words like "cognizable", "remand", "prima facie". If a finding uses them, translate to plain English ("cognizable" -> "the police can arrest without a warrant for this").
- Short sentences. Second person ("you", "the person who was arrested").
- If a specific number, date, or money threshold is in the findings (a deadline, a value limit), state it plainly and exactly -- do not round it away or hide it behind "it depends".
- Be honest about what is NOT known: if a finding is "Cannot Determine", say plainly what fact is missing and why it matters.
- Do NOT reassure falsely and do NOT alarm beyond what the findings support.

Structure it as four short parts, with these exact headings:
**What happened**
**What the law expects here**
**What may not have been done**
**What you can do now** (one concrete step -- name the actual missing document or the actual person to approach; never just "consult a lawyer")

The situation: {offence_name}

The findings (translate all of this to plain words -- do not skip any):
{compliance_summary}

How serious this looks overall: {severity_label}

About getting out on bail, if relevant: {bail_pathway_message}

Write about 120-180 words total. Plain, calm, direct."""


_PROMPTS = {"counsel": LAYMAN_SUMMARY_PROMPT, "plain": PLAIN_SUMMARY_PROMPT}


def _format_compliance_for_prompt(compliance_result, keep_citations=True):
    """Formats the compliance_checks list into plain text for the
    prompt -- every check's requirement/status/explanation verbatim.

    keep_citations=True (default, the junior-lawyer audience) leaves the
    formal '[Arnesh Kumar (2014)...]' bracket in the requirement string,
    since that reader can use it. The plain-language register passes
    keep_citations=False so the bracket is stripped before the model
    ever sees it (CHANGED 2026-08-29 had removed the strip entirely when
    the module was reframed; the plain path brings it back, scoped)."""
    lines = []
    for check in compliance_result.get("compliance_checks", []):
        requirement = check.get("requirement", "")
        if not keep_citations:
            requirement = _re.split(r"\s*\[", requirement, maxsplit=1)[0].strip()
        status = check.get("status", "")
        explanation = check.get("explanation", "")
        lines.append(f"- {requirement}: {status}. {explanation}")
    return "\n".join(lines)


def generate_layman_summary(compliance_result, severity, bail_pathway, offence_name=None,
                             audience="counsel",
                             section_number=None, statute_text=None, model=SONNET_MODEL):
    """Generates a precise, section-specific briefing of an
    ALREADY-COMPUTED compliance verdict, aimed at a junior-lawyer-level
    reader, now including the REAL statute text verbatim when
    available. Never re-derives or changes any verdict -- pure
    translation of existing, correct results.

    REFRAMED 2026-08-29 per explicit user direction: originally built
    for a stressed-layperson audience (see prior confirmed failure re:
    vague-out of specific facts, described in the prompt itself).
    Reframed for a junior lawyer / law intern, and extended to include
    real statute text -- per explicit user direction that the reader
    should see the actual law verbatim, not just a paraphrase, the
    same principle chat_assistant.py's format_retrieved_text_for_prompt
    already established for the chat feature (never invent or
    paraphrase-only when real source text is available).

    Args:
        compliance_result: the dict returned by run_arrest_compliance_checks.
        severity: the dict returned by compute_severity.
        bail_pathway: the dict returned by compute_bail_pathway_info,
            or None if not applicable.
        offence_name: plain-language offence name (e.g. "theft"), if known.
        section_number: the actual section number (e.g. "303"), if known.
        statute_text: the REAL statute text (e.g. from retrieval.py's
            get_statute_section), if available. When provided, the
            prompt instructs the model to quote it verbatim before
            explaining it. When None, the prompt gracefully proceeds
            without a quoted-text section rather than fabricating one.
        model: defaults to SONNET_MODEL.

    Returns:
        The generated summary text (str), or None if the API call fails.
    """
    try:
        from main import client
    except ImportError:
        client = None

    if client is None:
        return None

    prompt_template = _PROMPTS.get(audience, LAYMAN_SUMMARY_PROMPT)
    plain = audience == "plain"

    compliance_summary = _format_compliance_for_prompt(compliance_result, keep_citations=not plain)
    severity_label = severity.get("severity_label", "Not Available")
    bail_message = bail_pathway.get("message", "") if bail_pathway else "Not applicable for this situation."
    statute_text_display = statute_text if statute_text else "Not available for this section."

    if plain:
        offence_display = offence_name or "the situation described"
    elif offence_name and section_number:
        offence_display = f"{offence_name} (Section {section_number})"
    elif offence_name:
        offence_display = offence_name
    else:
        offence_display = "the offence described"

    fmt_kwargs = dict(
        offence_name=offence_display,
        compliance_summary=compliance_summary,
        severity_label=severity_label,
        bail_pathway_message=bail_message,
    )
    if not plain:
        fmt_kwargs["statute_text"] = statute_text_display

    try:
        response = client.messages.create(
            model=model,
            max_tokens=800 if plain else 1600,
            messages=[{
                "role": "user",
                "content": prompt_template.format(**fmt_kwargs),
            }],
        )
        # FIXED 2026-08-29: was `response.content[0].text`, which
        # assumes the first content block is always plain text. CONFIRMED
        # REAL FAILURE: 'ThinkingBlock' object has no attribute 'text' --
        # for this more complex synthesis prompt (quoting verbatim
        # statute text, applying a specific threshold, organizing
        # multiple findings), Sonnet returned a ThinkingBlock as the
        # first content item, followed by the actual TextBlock. Fixed
        # by searching content for the first block that actually has a
        # .text attribute, rather than assuming position -- this is
        # more robust generally, not just a one-off patch, since any
        # future call that happens to trigger extended thinking would
        # hit the same failure otherwise.
        text_block = next((block for block in response.content if hasattr(block, "text")), None)
        if text_block is None:
            raise ValueError("No text block found in response.content -- only non-text blocks returned.")
        return text_block.text.strip()
    except Exception as e:
        # TEMPORARY DIAGNOSTIC (2026-08-29): logger.warning alone may
        # not print to console depending on logging configuration --
        # confirmed real case where generate_layman_summary silently
        # failed (fallback correctly caught it, but the real cause was
        # never visible). Using print() as a forceful, impossible-to-miss
        # diagnostic until the real cause is found and fixed.
        import traceback
        print(f"=== generate_layman_summary DIAGNOSTIC ===")
        traceback.print_exc()
        print(f"Exception details: {type(e).__name__}: {e}")
        print("=== END DIAGNOSTIC ===")
        logger.warning("generate_layman_summary failed: %s", e)
        return None
