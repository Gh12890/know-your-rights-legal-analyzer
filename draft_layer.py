"""
draft_layer.py  --  Project 3: Bounded-Action / Compliance-Drafting Layer

Turns an already-computed `full_analysis` (from main.py's arrest pipeline
/ interview flow) into a DRAFT the person can act on.

THE ONE ARCHITECTURAL PRINCIPLE STILL HOLDS: deterministic Python decides
everything here. There is no LLM in this path. Every ground in a draft is
one compliance finding the engine already reached, quoted verbatim,
tagged with the case law `_result()` already attached. Nothing is
asserted that the findings do not support.

Shape (per the user's steer, 2026-09-02):
  - ONE body of content -- `assemble_draft_content()` -- built from the
    findings. What goes in depends on the situation (which checks came
    back Non-Compliant / May be Non-Compliant / Cannot Determine).
  - The ADDRESSEE is a choice made at draft time -- `render_draft(content,
    target)` with target in {"understanding", "magistrate", "sp"}:
      "understanding" -> plain notes, no addressee, no prayer
      "magistrate"    -> a representation: cause-title, grounds, prayer
      "sp"            -> a complaint letter to the Superintendent of Police
  - Facts the tool does not hold (name, police station, court, FIR
    number -- the arrest interview never captures these) render as
    "[ ___ ]" placeholders. No PII is collected or stored.

v1 is arrest-domain only. freeze / cheque-bounce reuse this same
content/target split later.
"""

import re

_ACTIONABLE = ("Non-Compliant", "May be Non-Compliant")

# worst-first, mirrors generate_quick_reference() in main.py
_PRIORITY = {"Non-Compliant": 0, "May be Non-Compliant": 1}

FILL = "[ ___ ]"

_DRAFT_HEADER = (
    "This is an automatically prepared draft based only on the information given. "
    "It is not legal advice. Have a qualified lawyer check it before you rely on it or file it. "
    "Anything shown as [ ___ ] or in [ square brackets ] is for you to fill in."
)

_ARNESH_CONSEQUENCES = (
    "The Supreme Court in Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273, has laid down that a "
    "police officer who arrests without complying with the mandatory notice/where arrest is not "
    "necessary is liable to departmental action and to punishment for contempt of court before the "
    "High Court having territorial jurisdiction; and a Judicial Magistrate who authorises detention "
    "without recording reasons in writing is liable to departmental action by the concerned High Court."
)


# ---------------------------------------------------------------------------
# 1. content assembly  --  pure lookup over full_analysis
# ---------------------------------------------------------------------------

def _citation_for(check):
    """The case-law tag for a compliance check. Prefers the real source
    paragraph `_result()` attached; falls back to the '[...]' tag baked
    into the requirement string."""
    sp = check.get("source_paragraphs") or []
    if sp:
        name = (sp[0].get("case_name") or "").strip()
        cite = (sp[0].get("citation") or "").strip()
        if name and cite:
            return f"{name}, {cite}"
        if name:
            return name
    m = re.search(r"\[([^\]]+)\]", check.get("requirement", ""))
    return m.group(1).strip() if m else ""


def _heading_of(check):
    """The requirement text with its trailing '[citation]' tag removed."""
    return re.split(r"\s*\[", check.get("requirement", ""), maxsplit=1)[0].strip()


# A compliance-check explanation is written for the on-screen UI, where the
# status label ("May be Non-Compliant") sits right next to it. In a draft
# document that label is gone, so a sentence like "The arrest may be illegal
# if no notice was served" reads as a bolder claim than the tool should be
# putting into a citizen's filing. Drop any sentence that states a
# conclusion about the arrest's validity -- the draft's own "GROUNDS" /
# "appears not to have been complied with" framing is the bounded way to
# raise it, and the lawyer decides how hard to argue it.
_CONCLUSION_SENT = re.compile(
    r"(?<![^.\s])(the\s+arrest|this|the\s+detention)\b[^.]*\b"
    r"(illegal|unlawful|vitiat\w*|void|bad\s+in\s+law|without\s+jurisdiction)\b[^.]*\.\s*",
    re.IGNORECASE,
)


def _trim_conclusion(finding):
    return _CONCLUSION_SENT.sub("", finding or "").strip()


def _val(f, key, blank):
    v = (f or {}).get(key)
    if v in (None, "", "unclear", "not stated", "not applicable"):
        return blank
    return str(v)


def _fact_lines(fields):
    """The narrative factual recital -- full sentences, safe to number
    under 'MOST RESPECTFULLY SHOWETH'. [ ___ ] where the tool has nothing."""
    f = fields or {}
    secs = ", ".join(str(s) for s in (f.get("sections_cited") or [])) or FILL
    lines = [
        f"the arrest took place on {_val(f, 'arrest_datetime_full', '[ date and time of arrest ]')}",
        f"the arrest was stated to be for an offence under Section(s) {secs}",
    ]
    prod = _val(f, "production_datetime_full", None)
    if prod:
        lines.append(f"the arrested person was produced before a Magistrate on {prod}")
    else:
        lines.append("the date and time of production before a Magistrate is not on record and remains "
                     "[ to be filled in ]")
    return lines


def _party_lines(fields):
    """The identifying details the tool never captures -- always blanks,
    shown as a fill-in checklist (not narrative)."""
    return [
        f"Name of the arrested person: {FILL}",
        f"Parentage / address: {FILL}",
        f"Police station and district: {FILL}",
        f"FIR number and date: {FILL}",
    ]


def assemble_draft_content(full_analysis):
    """The single body of draft substance, built from the findings.

    Returns a dict:
      facts        - list[str]   factual recital, [ ___ ] for unknowns
      grounds      - list[dict]  {heading, finding, citation, hedged}
                                 one per Non-Compliant / May be Non-Compliant check, worst first
      key_dates    - list[str]   forward-looking deadlines (default bail), any status
      to_verify    - list[str]   'Cannot Determine' checks, as "<heading> - <why>"
      consequences - bool        whether the Arnesh Kumar notice check is Non-Compliant
      no_defect    - bool        True when nothing came back actionable
      sections     - list[str]   sections cited (for the cause title)
    """
    compliance = (full_analysis or {}).get("compliance", {}) or {}
    checks = compliance.get("compliance_checks", []) or []
    fields = (full_analysis or {}).get("extracted_fields", {}) or {}

    actionable = sorted(
        (c for c in checks if c.get("status") in _ACTIONABLE),
        key=lambda c: _PRIORITY[c["status"]],
    )

    grounds = [
        {
            "heading": _heading_of(c),
            "finding": _trim_conclusion(c.get("explanation")),
            "citation": _citation_for(c),
            "hedged": c.get("status") == "May be Non-Compliant",
        }
        for c in actionable
    ]

    key_dates = []
    for c in checks:
        if "Default bail" in c.get("requirement", "") and c.get("explanation"):
            key_dates.append(c["explanation"].strip())

    to_verify = [
        f"{_heading_of(c)} - {(c.get('explanation') or '').strip()}"
        for c in checks
        if c.get("status") == "Cannot Determine"
    ]

    consequences = any(
        ("41A" in c.get("requirement", "") or "35(3)" in c.get("requirement", "")
         or "notice before arrest" in c.get("requirement", "").lower())
        and c.get("status") in _ACTIONABLE
        for c in checks
    )

    return {
        "facts": _fact_lines(fields),
        "party": _party_lines(fields),
        "grounds": grounds,
        "key_dates": key_dates,
        "to_verify": to_verify,
        "consequences": consequences,
        "no_defect": not grounds,
        "sections": [str(s) for s in (fields.get("sections_cited") or [])],
    }


_ARREST_MARKERS = ("arrest", "s.35", "s. 35", "default bail", "24 hour", "d.k. basu",
                   "dk basu", "arnesh", "vihaan", "grounds of arrest")


def is_arrest_analysis(full_analysis):
    """True when full_analysis came from the arrest pipeline -- the only
    domain draft_layer handles in v1. Checks the compliance requirements
    rather than a classification label so it works for both the document
    and interview entry points."""
    checks = ((full_analysis or {}).get("compliance", {}) or {}).get("compliance_checks", []) or []
    reqs = " ".join(c.get("requirement", "").lower() for c in checks)
    return any(m in reqs for m in _ARREST_MARKERS)


def available_targets(full_analysis):
    """'understanding' is always offered. The addressed drafts
    (magistrate / SP) are offered only when there is something to raise."""
    content = assemble_draft_content(full_analysis)
    targets = ["understanding"]
    if content["grounds"] or content["key_dates"]:
        targets += ["magistrate", "sp"]
    return targets


TARGET_LABELS = {
    "understanding": "Just to understand where things stand",
    "magistrate": "As a representation to the Magistrate",
    "sp": "As a complaint to the Superintendent of Police",
}


# ---------------------------------------------------------------------------
# 2. rendering  --  same content, different envelope
# ---------------------------------------------------------------------------

def _ground_verb(g):
    return "appears not to have been complied with" if g["hedged"] else "was not complied with"


def _render_understanding(c):
    out = ["NOTES ON THE PROCEDURAL POSITION IN THIS MATTER", "",
           f"[{_DRAFT_HEADER}]", ""]

    out += ["WHAT THE RECORD SHOWS", "On the information available:"]
    out += [f"- {line[0].upper() + line[1:]}." for line in c["facts"]]
    out += [""]

    out += ["DETAILS TO FILL IN"]
    out += [f"- {p}" for p in c["party"]]
    out += [""]

    if c["grounds"]:
        out += ["POINTS THAT MAY NOT COMPLY WITH PROCEDURE"]
        for i, g in enumerate(c["grounds"], 1):
            line = f"{i}. {g['heading']} - this {_ground_verb(g)}. {g['finding']}"
            if g["citation"]:
                line += f" (Reference: {g['citation']})"
            out.append(line)
        out += [""]
    else:
        out += ["No procedural defect was identified on the information available. "
                "This does not mean none exists - only that nothing in what was provided shows one.", ""]

    if c["key_dates"]:
        out += ["KEY DATES"]
        out += [f"- {d}" for d in c["key_dates"]]
        out += [""]

    if c["to_verify"]:
        out += ["STILL TO CONFIRM"]
        out += [f"- {t}" for t in c["to_verify"]]
        out += [""]

    if c["consequences"]:
        out += ["IF THE NOTICE REQUIREMENT WAS NOT FOLLOWED", _ARNESH_CONSEQUENCES, ""]

    return "\n".join(out).rstrip() + "\n"


def _render_magistrate(c):
    secs = ", ".join(c["sections"]) or FILL
    out = [
        "IN THE COURT OF [ name of the Magistrate ], AT [ place ]",
        "",
        f"FIR No. {FILL}, Police Station {FILL}, under Section(s) {secs}",
        "",
        "In the matter of: [ full name of the arrested person ], "
        "son/daughter/spouse of [ ___ ], resident of [ ___ ]  ... Arrested Person",
        "",
        "REPRESENTATION ON BEHALF OF THE ARRESTED PERSON REGARDING THE "
        "LEGALITY OF THE ARREST AND CONTINUED CUSTODY",
        "",
        f"[{_DRAFT_HEADER}]",
        "",
        "MOST RESPECTFULLY SHOWETH:",
        "",
    ]
    for i, fact in enumerate(c["facts"], 1):
        out.append(f"{i}. That {fact}.")
    out += ["", "GROUNDS", ""]

    if c["grounds"]:
        for idx, g in enumerate(c["grounds"]):
            letter = chr(ord("A") + idx)
            verb = "does not appear to have been complied with" if g["hedged"] else "was not complied with"
            body = f"{letter}. {g['heading']}: it is submitted that this requirement {verb}. {g['finding']}"
            if g["citation"]:
                body += f" This is contrary to {g['citation']}."
            out.append(body)
    else:
        out.append("A. No specific procedural defect is asserted; this representation is made "
                   "so that the Court may satisfy itself as to the legality of the arrest.")
    out += [""]

    if c["consequences"]:
        out += ["CONSEQUENCES OF NON-COMPLIANCE", _ARNESH_CONSEQUENCES, ""]

    out += ["PRAYER", "",
            "It is therefore most respectfully prayed that this Hon'ble Court may be pleased to:",
            "a) examine the legality of the arrest and the continued custody of the arrested "
            "person in the light of the grounds set out above;"]
    if c["key_dates"]:
        out.append("b) consider the arrested person's entitlement to release, having regard to the "
                   "position on default bail set out below;")
        letter = "c"
    else:
        letter = "b"
    out.append(f"{letter}) pass such further or other order as this Hon'ble Court may deem fit and proper "
               "in the interest of justice.")
    out += [""]

    if c["key_dates"]:
        out += ["POSITION ON DEFAULT BAIL"]
        out += [f"- {d}" for d in c["key_dates"]]
        out += [""]

    if c["to_verify"]:
        out += ["MATTERS STATED TO BE UNVERIFIED (for the Court's information)"]
        out += [f"- {t}" for t in c["to_verify"]]
        out += [""]

    out += ["", "VERIFICATION", "",
            "Verified at [ place ] on [ date ] that the contents of the above representation are "
            "true to the best of my knowledge and belief.",
            "",
            "[ place ]                                          [ signature ]",
            "[ date ]                                           [ name - the arrested person / counsel / next friend ]"]
    return "\n".join(out).rstrip() + "\n"


def _render_sp(c):
    secs = ", ".join(c["sections"]) or FILL
    out = [
        "To,",
        "The Superintendent of Police,",
        "[ district ]",
        "",
        f"Subject: Non-compliance with arrest procedure in the case of [ name of the arrested person ], "
        f"FIR No. {FILL}, Police Station {FILL} (Section(s) {secs}).",
        "",
        f"[{_DRAFT_HEADER}]",
        "",
        "Sir / Madam,",
        "",
    ]
    out.append("1. This is submitted on behalf of [ name of the arrested person ]. "
               f"On the information available, {c['facts'][0]}.")
    out.append("2. It is submitted that, on the information available, the following requirements "
               "were not met in this arrest:")
    out.append("")
    if c["grounds"]:
        for idx, g in enumerate(c["grounds"]):
            letter = chr(ord("a") + idx)
            line = f"   {letter}) {g['heading']} - this {_ground_verb(g)}. {g['finding']}"
            if g["citation"]:
                line += f" (Reference: {g['citation']})"
            out.append(line)
    else:
        out.append("   (No specific defect is alleged; this is brought to your notice for verification.)")
    out.append("")

    n = 3
    if c["key_dates"]:
        out.append(f"{n}. On the question of custody: " + " ".join(c["key_dates"]))
        n += 1
    if c["consequences"]:
        out.append(f"{n}. {_ARNESH_CONSEQUENCES}")
        n += 1
    out.append(f"{n}. It is requested that the above be examined, that the compliance of the "
               "officer(s) concerned be looked into, and that I be informed of the action taken.")
    out += ["",
            "Yours faithfully,",
            "",
            "[ name ]",
            "[ address / contact number ]",
            "[ date ]"]
    return "\n".join(out).rstrip() + "\n"


_RENDERERS = {
    "understanding": _render_understanding,
    "magistrate": _render_magistrate,
    "sp": _render_sp,
}


def render_draft(content, target):
    """`content` from assemble_draft_content(); `target` in
    {'understanding','magistrate','sp'}. Returns plain text."""
    if target not in _RENDERERS:
        raise ValueError(f"unknown draft target {target!r}; expected one of {list(_RENDERERS)}")
    return _RENDERERS[target](content)


def draft_for(full_analysis, target):
    """Convenience: assemble + render in one call."""
    return render_draft(assemble_draft_content(full_analysis), target)


# ---------------------------------------------------------------------------
# 3. PDF  --  lays the (possibly user-edited) draft text into the KYR PDF style
# ---------------------------------------------------------------------------

def generate_draft_pdf(draft_text, target, output_path="action_draft.pdf"):
    """Render the draft text (as edited by the person) into a PDF using
    the shared Know Your Rights styles. Heading detection is simple:
    an ALL-CAPS line becomes a section title, everything else is body,
    blank lines become spacing."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from main import _kyr_pdf_styles

    S = _kyr_pdf_styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    )
    story = [
        Paragraph("KNOW YOUR RIGHTS", S["header"]),
        Paragraph(f"Draft &mdash; {TARGET_LABELS.get(target, target)}", S["sub"]),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#14213D")),
        Spacer(1, 12),
    ]

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    for raw in (draft_text or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            story.append(Spacer(1, 6))
            continue
        letters = [ch for ch in line if ch.isalpha()]
        is_heading = len(letters) >= 3 and all(ch.isupper() for ch in letters) and not line.startswith(("[", "-"))
        story.append(Paragraph(esc(line), S["section_title"] if is_heading else S["body"]))

    story += [
        Spacer(1, 20),
        HRFlowable(width="100%", thickness=0.6, color=colors.grey),
        Spacer(1, 6),
        Paragraph(
            "This draft is generated by an automated tool and is not legal advice. It is a starting "
            "point to be checked and completed with a qualified advocate before it is signed, filed, "
            "or sent. Points phrased as 'appears not to have' are inferences from missing information, "
            "not confirmed findings.",
            S["small"],
        ),
    ]
    doc.build(story)
    return output_path


if __name__ == "__main__":
    demo = {
        "extracted_fields": {
            "sections_cited": ["303(2)", "318(4)"],
            "arrest_datetime_full": "12-07-2026 09:30",
            "production_datetime_full": None,
        },
        "compliance": {
            "compliance_checks": [
                {"requirement": "S.35(3) BNSS notice before arrest [Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273]",
                 "status": "May be Non-Compliant",
                 "explanation": "Offence punishable up to 7 years; the record is silent on any prior notice to appear."},
                {"requirement": "Written grounds of arrest furnished to arrestee [Vihaan Kumar, 2025 INSC 162]",
                 "status": "Non-Compliant",
                 "explanation": "No separate written grounds of arrest were furnished."},
                {"requirement": "Default bail on chargesheet delay [S.187 BNSS / S.167(2) CrPC]",
                 "status": "Compliant",
                 "explanation": "No chargesheet filed yet. Default bail becomes available on 10-09-2026 if not filed before then."},
                {"requirement": "Produced before magistrate within 24 hours [Art. 22(2)/S.58 BNSS]",
                 "status": "Cannot Determine",
                 "explanation": "Production date/time not stated."},
            ]
        },
    }
    for t in ("understanding", "magistrate", "sp"):
        print("=" * 70)
        print(f"TARGET: {t}")
        print("=" * 70)
        print(draft_for(demo, t))
