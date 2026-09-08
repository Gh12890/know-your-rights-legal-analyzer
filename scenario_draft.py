"""
scenario_draft.py  (Vibeathon Step 4, 2026-09-08)

Turn a scenario answer into a first-draft document the person can hand to a
duty lawyer, a Legal Services Authority desk, or the Magistrate.

DETERMINISTIC. No LLM. The document is assembled from:
  - the scenario's paper_type (which document),
  - the rights the person's own facts raised (the legal basis section),
  - a few facts lifted from the person's message by plain regex, each shown
    as "[from what you told you]" / "[to confirm]" so nothing reads as a
    settled finding,
  - fixed prayer / relief text per document type.

This is the "the tool writes the paper" proof -- a chatbot cannot hand you a
representation that names the 9:40 pm arrest using facts from your own story.
It is a starting point, clearly marked, to be finished with a lawyer.
"""

import re
import textwrap

_WRAP = 92


# paper_type -> (document title, one-line description, prayer lines)
_DOC_SPEC = {
    "default_bail_application": {
        "title": "APPLICATION FOR RELEASE ON DEFAULT (STATUTORY) BAIL",
        "under": "Section 187(3) of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "forum": "In the Court of the [Magistrate / Court of Session], [_____________]",
        "prayer": [
            "It is respectfully prayed that this Hon'ble Court may be pleased to:",
            "  a. release the accused on default bail under the proviso to Section 187 BNSS, "
            "the statutory period for filing the police report having expired without the "
            "report being filed;",
            "  b. fix such terms of bail as the accused is in a position to meet; and",
            "  c. pass any further order this Hon'ble Court deems fit.",
            "",
            "The accused is ready and willing to furnish bail.",
        ],
    },
    "magistrate_representation": {
        "title": "REPRESENTATION ON BEHALF OF AN ARRESTED PERSON",
        "under": "Articles 21 and 22 of the Constitution and Sections 43, 47, 48 and 58 BNSS",
        "forum": "To the Learned [Judicial Magistrate], [_____________] "
                 "(to be placed before the Court at the time of production / remand)",
        "prayer": [
            "It is respectfully submitted that this Hon'ble Court may be pleased to:",
            "  a. verify, on the record, whether the grounds of arrest were communicated "
            "and whether the arrest and custody safeguards below were complied with;",
            "  b. direct that any non-compliance be recorded;",
            "  c. direct a medical examination of the arrested person and record any "
            "complaint of ill-treatment; and",
            "  d. consider the above while deciding the question of remand.",
        ],
    },
    "fir_complaint_to_magistrate": {
        "title": "APPLICATION FOR A DIRECTION TO REGISTER AN FIR AND INVESTIGATE",
        "under": "Section 175(3) of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "forum": "In the Court of the Learned [Judicial Magistrate], [_____________]",
        "prayer": [
            "It is respectfully prayed that this Hon'ble Court may be pleased to:",
            "  a. direct the officer in charge of Police Station [_______] to register an "
            "FIR on the complaint annexed and to investigate the cognizable offence(s) "
            "disclosed;",
            "  b. call for a report on the action taken; and",
            "  c. pass any further order this Hon'ble Court deems fit.",
            "",
            "A copy of the written complaint made to the police, and of the complaint "
            "sent to the Superintendent of Police, is annexed.",
        ],
    },
    "anticipatory_bail_note": {
        "title": "NOTE FOR AN APPLICATION FOR ANTICIPATORY (PRE-ARREST) BAIL",
        "under": "Section 482 of the Bharatiya Nagarik Suraksha Sanhita, 2023",
        "forum": "In the [High Court / Court of Session], [_____________]",
        "prayer": [
            "It is respectfully prayed that this Hon'ble Court may be pleased to:",
            "  a. direct that in the event of arrest in connection with FIR / complaint "
            "[_______], the applicant be released on bail;",
            "  b. grant interim protection pending disposal of this application; and",
            "  c. pass any further order this Hon'ble Court deems fit.",
        ],
    },
    "cheque_demand_notice": {
        "title": "STATUTORY DEMAND NOTICE",
        "under": "the proviso to Section 138 of the Negotiable Instruments Act, 1881",
        "forum": "To: [Drawer of the cheque], [address]",
        "prayer": [
            "You are hereby called upon to pay the sum of Rs. [_______], being the amount "
            "of the dishonoured cheque, within 15 days of receipt of this notice.",
            "Failing payment within that period, the undersigned will be constrained to "
            "initiate proceedings under Section 138 of the Negotiable Instruments Act, 1881.",
        ],
    },
}


_DAYS_RE = re.compile(r"\b(\d{1,3})\s*(day|days|week|weeks|month|months)\b", re.I)
_TIME_RE = re.compile(r"\b(\d{1,2})\s*[:.]?\s*(\d{2})?\s*(a\.?m\.?|p\.?m\.?)\b", re.I)
_NIGHT_RE = re.compile(r"\b(last night|at night|after sunset|late (?:at )?night|midnight|evening)\b", re.I)


def _facts_from(message: str, answer: dict) -> list:
    """A short list of '[from what you told us] ...' lines. Deliberately
    conservative: only what a plain regex can safely lift, each hedged."""
    msg = message or ""
    out = []

    m = _DAYS_RE.search(msg)
    if m:
        out.append(f"The person has been in custody for about {m.group(1)} {m.group(2)} "
                   f"(to be confirmed against the arrest memo / remand orders).")

    t = _TIME_RE.search(msg)
    if t:
        hh = t.group(1)
        mm = t.group(2) or "00"
        ap = t.group(3).replace(".", "").lower()
        out.append(f"The arrest is said to have taken place at about {hh}:{mm} {ap} "
                   f"(exact time to be confirmed).")
    elif _NIGHT_RE.search(msg):
        out.append("The arrest is said to have taken place after sunset / at night "
                   "(exact time to be confirmed).")

    off = (answer.get("offence_hint") or "").strip()
    if off:
        out.append(f"The matter is said to concern: {off} "
                   f"(the exact section(s) to be confirmed from the FIR / memo).")

    role = answer.get("role")
    if role == "family":
        out.append("This representation is made by a relative of the arrested person.")
    elif role == "complainant":
        out.append("This application is made by the complainant / informant.")

    return out


def _wrap(s: str) -> str:
    return "\n".join(textwrap.fill(line, _WRAP) if line.strip() else ""
                     for line in s.split("\n"))


def build_document(answer: dict, message: str) -> dict:
    """Returns {'available': bool, 'title', 'target', 'text'}.
    available is False for an out-of-scope answer or a paper_type with no
    template."""
    if answer.get("status") != "answered":
        return {"available": False, "title": "", "target": "", "text": ""}

    spec = _DOC_SPEC.get(answer.get("paper_type"))
    if spec is None:
        return {"available": False, "title": "", "target": answer.get("paper_type", ""),
                "text": ""}

    L = []
    L.append("RECOURSE  --  DRAFT DOCUMENT  (not legal advice; complete with a lawyer)")
    L.append("=" * _WRAP)
    L.append("")
    L.append(spec["title"])
    L.append(f"under {spec['under']}")
    L.append("")
    L.append(spec["forum"])
    L.append("")
    L.append("-" * _WRAP)
    L.append("1. WHAT IS SAID TO HAVE HAPPENED")
    L.append("-" * _WRAP)
    L.append(_wrap("In the person's own words: “" + (message or "").strip() + "”"))
    facts = _facts_from(message, answer)
    if facts:
        L.append("")
        for f in facts:
            L.append(_wrap("[from what you told us] " + f))
    L.append("")
    L.append("-" * _WRAP)
    L.append("2. THE LEGAL POSITION RELIED ON")
    L.append("-" * _WRAP)
    for i, r in enumerate(answer.get("rights", []), 1):
        L.append("")
        L.append(_wrap(f"{i}. {r['plain_text']}"))
        cite = []
        if r.get("section_label"):
            cite.append(r["section_label"])
        if r.get("case"):
            cite.append(r["case"] + (f", {r['case_excerpt'].get('citation')}"
                                     if r.get("case_excerpt", {}).get("citation") else ""))
        elif r.get("case_ref"):
            cite.append(f"see {r['case_ref']}, above")
        if cite:
            L.append(_wrap("   Authority: " + "; ".join(cite)))
    negs = answer.get("negations", [])
    if negs:
        L.append("")
        L.append("For completeness, the following does not arise on the facts stated:")
        for n in negs:
            L.append(_wrap("  - " + n["line"]))
    L.append("")
    L.append("-" * _WRAP)
    L.append("3. PRAYER")
    L.append("-" * _WRAP)
    for line in spec["prayer"]:
        L.append(_wrap(line) if line.strip() else "")
    L.append("")
    L.append("-" * _WRAP)
    L.append("")
    L.append("Place: ____________________            ____________________________")
    L.append("Date:  ____________________            (signature / name of the person"
             " or the person's advocate)")
    L.append("")
    L.append("=" * _WRAP)
    L.append(_wrap(
        "This draft was generated by Recourse from what you typed. It is a starting "
        "point, not a finished document and not legal advice. The blanks in square "
        "brackets must be filled in, the facts checked against your papers (FIR, arrest "
        "memo, remand orders), and the whole thing reviewed by a lawyer or a Legal "
        "Services Authority before it is signed, filed or sent. Points shown as "
        "'[from what you told us]' are your account, not findings."))

    return {
        "available": True,
        "title": spec["title"],
        "target": answer.get("paper_type"),
        "text": "\n".join(L),
    }


def document_pdf(doc: dict, out_path: str) -> str:
    """Lay the draft text into a simple branded PDF. Returns out_path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13.5)
    head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=15,
                          textColor=colors.HexColor("#1b3a4b"), spaceAfter=2)
    sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=8.5,
                         textColor=colors.HexColor("#5b6b73"), spaceAfter=8)
    sect = ParagraphStyle("sect", fontName="Helvetica-Bold", fontSize=10,
                          textColor=colors.HexColor("#1b3a4b"), spaceBefore=8, spaceAfter=3)

    d = SimpleDocTemplate(out_path, pagesize=A4, topMargin=0.85 * inch,
                          bottomMargin=0.85 * inch, leftMargin=0.9 * inch,
                          rightMargin=0.9 * inch)
    story = [Paragraph("Recourse", head),
             Paragraph("Draft document &mdash; not legal advice", sub),
             HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1b3a4b")),
             Spacer(1, 8)]

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    for raw in (doc.get("text") or "").split("\n"):
        line = raw.rstrip()
        if not line.strip() or set(line) <= {"=", "-", " "}:
            story.append(Spacer(1, 5))
            continue
        letters = [c for c in line if c.isalpha()]
        is_head = len(letters) >= 3 and all(c.isupper() for c in letters)
        story.append(Paragraph(esc(line), sect if is_head else body))
    d.build(story)
    return out_path


if __name__ == "__main__":
    from scenario_answer import build_scenario_answer
    for msg in [
        "the police have kept my brother 70 days and still haven't filed any chargesheet",
        "my sister was arrested last night around 9 pm, nobody told us why, she's a nursing mother",
        "the police won't register my complaint about the goods stolen from my shop",
    ]:
        ans = build_scenario_answer(msg)
        doc = build_document(ans, msg)
        print("\n\n" + "#" * 92)
        print(doc["text"] if doc["available"] else f"(no document for {doc['target']})")
