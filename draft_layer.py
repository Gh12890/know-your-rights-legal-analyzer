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

Covers three domains, each detected from the compliance requirement text
(detect_draft_domain) and each with its own assembler + envelope set:
  - arrest  -> understanding / magistrate representation / SP complaint
  - freeze  -> understanding / application to the Magistrate to release
               the account / letter to the SP
  - cheque  -> understanding / reply to the Section 138 demand notice /
               (only when a jurisdiction defect exists) application to
               the Magistrate on territorial jurisdiction
Target keys are globally unique ("freeze_magistrate", "cheque_reply", ...)
so render_draft dispatches on the key alone.
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
# if no notice was served" -- or, for freeze, "this freeze may be
# unauthorised and legally vulnerable to challenge" -- reads as a bolder
# claim than the tool should be putting into a citizen's filing. Drop any
# sentence that states a conclusion about the arrest's / freeze's validity
# -- the draft's own "GROUNDS" / "appears not to have been complied with"
# framing is the bounded way to raise it, and the lawyer decides how hard
# to argue it. Cheque explanations are already attributed and hedged ("per
# Kaveri Plastics ... can be fatal to the complaint") -- those stay.
_CONCLUSION_SENT = re.compile(
    r"(?<![^.\s])(the\s+arrest|this|the\s+detention|(?:a|the)\s+freeze|the\s+attachment)\b[^.]*\b"
    r"(illegal|unlawful|vitiat\w*|void|bad\s+in\s+law|without\s+jurisdiction|"
    r"unauthoris\w*|legally\s+vulnerable)\b[^.]*\.\s*",
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


def _build_grounds(checks):
    """One ground per Non-Compliant / May-be-Non-Compliant check, worst
    first: heading with the '[citation]' tag stripped, finding with any
    illegality-conclusion sentence trimmed, citation, and a `hedged` flag
    that drives the 'appears not to have' vs 'was not' phrasing. Shared by
    all three domains."""
    actionable = sorted(
        (c for c in checks if c.get("status") in _ACTIONABLE),
        key=lambda c: _PRIORITY[c["status"]],
    )
    return [
        {
            "heading": _heading_of(c),
            "finding": _trim_conclusion(c.get("explanation")),
            "citation": _citation_for(c),
            "hedged": c.get("status") == "May be Non-Compliant",
        }
        for c in actionable
    ]


def _build_to_verify(checks):
    return [
        f"{_heading_of(c)} - {(c.get('explanation') or '').strip()}"
        for c in checks
        if c.get("status") == "Cannot Determine"
    ]


def assemble_draft_content(full_analysis):
    """The single body of arrest-draft substance, built from the findings.

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

    grounds = _build_grounds(checks)

    key_dates = []
    for c in checks:
        if "Default bail" in c.get("requirement", "") and c.get("explanation"):
            key_dates.append(c["explanation"].strip())

    to_verify = _build_to_verify(checks)

    consequences = any(
        ("41A" in c.get("requirement", "") or "35(3)" in c.get("requirement", "")
         or "notice before arrest" in c.get("requirement", "").lower())
        and c.get("status") in _ACTIONABLE
        for c in checks
    )

    return {
        "domain": "arrest",
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
_FREEZE_MARKERS = ("freeze", "attachment")
_CHEQUE_MARKERS = ("s.138", "138(", "cheque", "ni act", "return memo", "negotiable instrument")

# Order matters only in that the marker sets are disjoint on the real
# requirement strings of all three pipelines (verified in
# test_draft_layer.py) -- no requirement text triggers two domains.
_DOMAIN_MARKERS = (("freeze", _FREEZE_MARKERS), ("cheque", _CHEQUE_MARKERS),
                   ("arrest", _ARREST_MARKERS))


def detect_draft_domain(full_analysis):
    """Which drafting domain this analysis belongs to -- 'arrest',
    'freeze', 'cheque', or None if draft_layer has no template for it.
    Reads the compliance requirement text, not a classification label,
    so it works for both the document-upload and interview entry points."""
    checks = ((full_analysis or {}).get("compliance", {}) or {}).get("compliance_checks", []) or []
    reqs = " ".join(c.get("requirement", "").lower() for c in checks)
    for domain, markers in _DOMAIN_MARKERS:
        if any(m in reqs for m in markers):
            return domain
    return None


def is_arrest_analysis(full_analysis):
    """Back-compat shim -- kept because app.py and older callers import it.
    New code should use detect_draft_domain()."""
    return detect_draft_domain(full_analysis) == "arrest"


_ASSEMBLERS = {}  # filled in below, once the freeze/cheque assemblers are defined


def _clean_authorities(authorities):
    """Normalise the caller-supplied authorities list. Each item:
        {case_name, citation, court, para_number, quote, url, verified}
    A quote is mandatory (it is what gets reproduced verbatim); an item
    without one is dropped. Order preserved, deduped on (case_name, quote)."""
    out, seen = [], set()
    for a in authorities or []:
        if not isinstance(a, dict):
            continue
        quote = (a.get("quote") or "").strip()
        name = (a.get("case_name") or "").strip()
        if not quote or not name:
            continue
        key = (name.lower(), quote[:80].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "case_name": name,
            "citation": (a.get("citation") or "").strip(),
            "court": (a.get("court") or "").strip(),
            "para_number": a.get("para_number"),
            "quote": quote,
            "url": (a.get("url") or "").strip(),
            "verified": bool(a.get("verified")),
        })
    return out


_MEDICAL_MATTER_RE = re.compile(
    r"\b(bruis|injur|wound|beat|slap|assault|hit|thrash|tortur|hurt|blood|"
    r"marks on|handcuff|chained|medical|doctor|hospital|kept awake|sleep)\b", re.I)


def _wants_medical_prayer(checks, matters_raised):
    """True when the draft should ask the Court to order an immediate
    medical examination: the D.K. Basu medical item did not pass, OR the
    person has described injuries / custodial ill-treatment."""
    for c in checks or []:
        if "medical exam" in c.get("requirement", "").lower() and c.get("status") in _ACTIONABLE:
            return True
    return any(_MEDICAL_MATTER_RE.search(m or "") for m in (matters_raised or []))


def assemble_for(full_analysis, *, authorities=None, matters_raised=None):
    """Detect the domain and run its assembler. Returns the content dict
    (carrying its own 'domain' key) or None when no template applies.

    authorities: verbatim judgment passages to reproduce in the draft --
        see _clean_authorities. verified=True ones sit in the body;
        verified=False ones sit in a clearly-marked "not verified" block.
    matters_raised: things the person stated that no compliance check
        adjudicates (e.g. custodial assault) -- set out verbatim for the
        authority's attention, expressly unassessed.
    """
    domain = detect_draft_domain(full_analysis)
    if domain is None:
        return None
    content = _ASSEMBLERS[domain](full_analysis)
    checks = ((full_analysis or {}).get("compliance", {}) or {}).get("compliance_checks", []) or []
    content["authorities"] = _clean_authorities(authorities)
    content["matters_raised"] = [str(m).strip() for m in (matters_raised or []) if m and str(m).strip()]
    content["needs_medical_prayer"] = _wants_medical_prayer(checks, content["matters_raised"])
    return content


def _authorities_block(content):
    """The 'RELEVANT JUDICIAL AUTHORITY' section -- verbatim quotes, full
    citation, para number. verified in the body; the rest walled off in a
    'NOT VERIFIED' sub-block. [] when there are no authorities."""
    auths = content.get("authorities") or []
    if not auths:
        return []
    verified = [a for a in auths if a["verified"]]
    unverified = [a for a in auths if not a["verified"]]

    def _cite(a):
        bits = [a["case_name"]]
        if a["citation"]:
            bits.append(a["citation"])
        if a["court"]:
            bits.append(f"({a['court']})")
        loc = f", at paragraph {a['para_number']}" if a["para_number"] else ""
        return " ".join(bits) + loc

    out = ["RELEVANT JUDICIAL AUTHORITY",
           "The following passages are reproduced word-for-word from the judgments. "
           "Read each judgment in full before relying on it."]
    for i, a in enumerate(verified, 1):
        out.append(f"{i}. In {_cite(a)}, the Court observed:")
        out.append(f'   "{a["quote"]}"')

    if unverified:
        out += ["",
                "FURTHER JUDGMENTS FROM A LIVE SEARCH - NOT VERIFIED",
                "These were retrieved automatically and have NOT been checked by anyone. "
                "Before this draft is sent, read each judgment at the link given and satisfy "
                "yourself that it is on point and still good law. Delete any you are not sure of."]
        for j, a in enumerate(unverified):
            out.append(f"   {chr(ord('a') + j)}) In {_cite(a)}, the Court observed:")
            out.append(f'      "{a["quote"]}"')
            if a["url"]:
                out.append(f"      [ {a['url']} ]")
    return out + [""]


def _matters_block(content):
    """The 'MATTERS STATED BY THE ARRESTED PERSON / FAMILY' section --
    grievances no check adjudicates, set out verbatim, expressly
    unassessed. [] when there are none."""
    matters = content.get("matters_raised") or []
    if not matters:
        return []
    out = ["MATTERS STATED BY THE ARRESTED PERSON / FAMILY",
           "The following were stated in describing the situation. This tool does not "
           "assess or verify them. They are set out here for the attention of the "
           "authority addressed."]
    out += [f"- {m.rstrip('.')}." for m in matters]
    return out + [""]


def available_targets(full_analysis):
    """'<domain>_understanding' (or plain 'understanding' for arrest) is
    always offered. The addressed drafts are offered only when there is a
    ground -- and, for arrest, also when there is a forward-looking key
    date. Returns [] when draft_layer has no template for this analysis."""
    content = assemble_for(full_analysis)
    if content is None:
        return []
    domain = content["domain"]
    has_ground = bool(content["grounds"])
    if domain == "arrest":
        targets = ["understanding"]
        if has_ground or content["key_dates"]:
            targets += ["magistrate", "sp"]
        return targets
    if domain == "freeze":
        targets = ["freeze_understanding"]
        if has_ground:
            targets += ["freeze_magistrate", "freeze_sp"]
        return targets
    if domain == "cheque":
        targets = ["cheque_understanding"]
        if has_ground:
            targets += ["cheque_reply"]
        if any("presented for collection" in g["heading"].lower() for g in content["grounds"]):
            targets += ["cheque_magistrate"]
        return targets
    return ["understanding"]


TARGET_LABELS = {
    "understanding": "Just to understand where things stand",
    "magistrate": "As a representation to the Magistrate",
    "sp": "As a complaint to the Superintendent of Police",
    "freeze_understanding": "Just to understand where things stand",
    "freeze_magistrate": "As an application to the Magistrate to release the account",
    "freeze_sp": "As a letter to the Superintendent of Police",
    "cheque_understanding": "Just to understand where things stand",
    "cheque_reply": "As a reply to the demand notice",
    "cheque_magistrate": "As an application to the Magistrate on jurisdiction",
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

    out += _matters_block(c)
    out += _authorities_block(c)

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

    out += _matters_block(c)
    out += _authorities_block(c)

    out += ["PRAYER", "",
            "It is therefore most respectfully prayed that this Hon'ble Court may be pleased to:",
            "a) examine the legality of the arrest and the continued custody of the arrested "
            "person in the light of the grounds set out above;"]
    _pl = ord("b")
    if c.get("needs_medical_prayer"):
        out.append(f"{chr(_pl)}) direct that the arrested person be medically examined forthwith by a "
                   "Government medical officer / registered medical practitioner, that all injuries and "
                   "their approximate time of causation be recorded, and that the report be placed on "
                   "the record of this case;")
        _pl += 1
    if c["key_dates"]:
        out.append(f"{chr(_pl)}) consider the arrested person's entitlement to release, having regard to "
                   "the position on default bail set out below;")
        _pl += 1
    out.append(f"{chr(_pl)}) pass such further or other order as this Hon'ble Court may deem fit and "
               "proper in the interest of justice.")
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

    matters = _matters_block(c)
    if matters:
        out += [""] + matters
    auth = _authorities_block(c)
    if auth:
        out += auth

    if c.get("needs_medical_prayer"):
        out.append(f"{n}. It is requested that the arrested person be medically examined without delay "
                   "and any injuries recorded, with a copy of the report furnished.")
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


# ---------------------------------------------------------------------------
# 2b. freeze domain  --  account holder wanting the account released
# ---------------------------------------------------------------------------

def _KNOWN(v):
    """A field value the tool can actually put in a sentence -- not a
    missing / placeholder / 'unclear' marker from any of the three flows."""
    return v not in (None, "", "unclear", "SKIPPED", "not stated", "not applicable")

_FREEZE_CONTEXT = (
    "For an account freeze: ordinary seizure under Section 106 BNSS covers evidentiary "
    "seizure only and does not, by itself, authorise a debit-freeze or attachment of a "
    "bank account -- that requires an order of a competent Magistrate under Section 107 "
    "BNSS, with intimation to the Magistrate. The account holder is, at the least, "
    "entitled to be told the reasons for the freeze, and a freeze of the whole account "
    "rather than the specific disputed sum has been held disproportionate "
    "(Neelkanth Pharma Logistics (2025); Malabar Gold (2026); State of Maharashtra v "
    "Tapas D. Neogy, (1999) 7 SCC 685)."
)


def _freeze_fact_lines(fields):
    f = fields or {}
    lines = []

    scope = f.get("scope")
    amt = f.get("specific_amount_stated")
    amt_txt = f" (Rs. {amt})" if _KNOWN(amt) else ""
    if scope == "entire account":
        lines.append(f"the entire bank account was frozen, not only a specific disputed sum{amt_txt}")
    elif scope == "specific disputed amount":
        lines.append(f"a specific sum{amt_txt} was held, rather than the whole account")
    else:
        lines.append("whether the whole account or only a specific sum was frozen is [ to be confirmed ]")

    intimated = f.get("account_holder_intimated")
    if intimated is True:
        lines.append("the account holder was informed of the freeze")
    elif intimated is False:
        lines.append("the account holder was not informed of the freeze and came to know of it only "
                     "when a transaction failed")
    else:
        lines.append("how the account holder came to know of the freeze is [ to be confirmed ]")

    order_shown = f.get("written_order_shown")
    mentions_court = f.get("written_order_mentions_court")
    court_mentioned = f.get("court_or_magistrate_mentioned")
    if order_shown is True and mentions_court is True:
        lines.append("a written communication was received that referred to a court or a Magistrate's order")
    elif order_shown is True:
        lines.append("a written communication about the freeze was received, but it did not refer to any "
                     "court or Magistrate's order")
    elif court_mentioned is True:
        lines.append("a court or Magistrate was said to be involved, but no written order was shown to "
                     "the account holder")
    elif order_shown is False or court_mentioned is False:
        lines.append("no written order, and no reference to a court or Magistrate authorising the freeze, "
                     "was shown to the account holder")
    else:
        lines.append("whether any court order authorises the freeze is [ to be confirmed ]")

    return lines


def _freeze_party_lines(fields):
    return [
        f"Name of the account holder: {FILL}",
        f"Bank, branch and account number: {FILL}",
        f"FIR / case number and police station, if known: {FILL}",
        f"Investigating officer / agency, if known: {FILL}",
        f"Date the freeze was discovered or notified: {FILL}",
    ]


def assemble_freeze_content(full_analysis):
    """Freeze-domain content. Same {heading, finding, citation, hedged}
    grounds shape as arrest; facts/party are freeze-specific; no key_dates
    (a freeze has no running statutory clock the way default bail does)."""
    compliance = (full_analysis or {}).get("compliance", {}) or {}
    checks = compliance.get("compliance_checks", []) or []
    fields = (full_analysis or {}).get("extracted_fields", {}) or {}

    grounds = _build_grounds(checks)
    return {
        "domain": "freeze",
        "facts": _freeze_fact_lines(fields),
        "party": _freeze_party_lines(fields),
        "grounds": grounds,
        "key_dates": [],
        "to_verify": _build_to_verify(checks),
        "context_note": _FREEZE_CONTEXT,
        "no_defect": not grounds,
        "sections": ["106/107 BNSS"],
    }


def _render_freeze_understanding(c):
    out = ["NOTES ON THE POSITION REGARDING THE FROZEN ACCOUNT", "",
           f"[{_DRAFT_HEADER}]", "",
           "WHAT THE RECORD SHOWS", "On the information available:"]
    out += [f"- {line[0].upper() + line[1:]}." for line in c["facts"]]
    out += ["", "DETAILS TO FILL IN"]
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
        out += ["No procedural defect was identified on the information available. This does not mean "
                "none exists - only that nothing in what was provided shows one.", ""]

    if c["to_verify"]:
        out += ["STILL TO CONFIRM"]
        out += [f"- {t}" for t in c["to_verify"]]
        out += [""]

    out += ["WHAT THE LAW REQUIRES FOR AN ACCOUNT FREEZE", c["context_note"], ""]
    return "\n".join(out).rstrip() + "\n"


def _render_freeze_magistrate(c):
    out = [
        "IN THE COURT OF [ name of the Magistrate ], AT [ place ]",
        "",
        f"In the matter of FIR / Case No. {FILL}, Police Station {FILL}",
        "",
        "In the matter of: [ full name of the account holder ], "
        "[ address ], holder of Account No. [ ___ ] at [ bank / branch ]  ... Applicant",
        "",
        "APPLICATION FOR RELEASE / DE-FREEZING OF THE BANK ACCOUNT, OR FOR "
        "RESTRICTING THE FREEZE TO THE SPECIFIC DISPUTED AMOUNT",
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
        out.append("A. No specific defect is asserted; this application is made so that the Court may "
                   "satisfy itself that the freeze is properly authorised and proportionate.")
    out += ["", "LEGAL POSITION", c["context_note"], ""]

    out += ["PRAYER", "",
            "It is therefore most respectfully prayed that this Hon'ble Court may be pleased to:",
            "a) call upon the investigating agency to produce the order, if any, under which the "
            "account came to be frozen or attached;",
            "b) direct the de-freezing / release of the account, or in the alternative direct that "
            "the freeze be restricted to the specific disputed amount of [ Rs. ___ ];",
            "c) pass such further or other order as this Hon'ble Court may deem fit and proper in the "
            "interest of justice."]
    out += [""]

    if c["to_verify"]:
        out += ["MATTERS STATED TO BE UNVERIFIED (for the Court's information)"]
        out += [f"- {t}" for t in c["to_verify"]]
        out += [""]

    out += ["", "VERIFICATION", "",
            "Verified at [ place ] on [ date ] that the contents of the above application are true to "
            "the best of my knowledge and belief.",
            "",
            "[ place ]                                          [ signature ]",
            "[ date ]                                           [ name - the account holder / counsel ]"]
    return "\n".join(out).rstrip() + "\n"


def _render_freeze_sp(c):
    out = [
        "To,",
        "The Superintendent of Police,",
        "[ district ]",
        "",
        f"Subject: Freezing of Bank Account No. {FILL} of [ name of the account holder ] - request to "
        "produce the authorising order and to review the freeze.",
        "",
        f"[{_DRAFT_HEADER}]",
        "",
        "Sir / Madam,",
        "",
        "1. This is submitted on behalf of [ name of the account holder ], holder of the account "
        f"referred to above. On the information available, {c['facts'][0]}.",
        "2. It is submitted that, on the information available, the following requirements appear not "
        "to have been met in relation to this freeze:",
        "",
    ]
    if c["grounds"]:
        for idx, g in enumerate(c["grounds"]):
            letter = chr(ord("a") + idx)
            line = f"   {letter}) {g['heading']} - this {_ground_verb(g)}. {g['finding']}"
            if g["citation"]:
                line += f" (Reference: {g['citation']})"
            out.append(line)
    else:
        out.append("   (No specific defect is alleged; this is brought to your notice for verification.)")
    out += ["",
            "3. " + c["context_note"],
            "4. It is requested that the order (if any) authorising the freeze under Section 107 BNSS "
            "be furnished, that the freeze be restricted to the specific disputed amount or lifted, "
            "and that I be informed of the action taken.",
            "",
            "Yours faithfully,",
            "",
            "[ name ]",
            "[ address / contact number ]",
            "[ date ]"]
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# 2c. cheque domain  --  the drawer replying to a Section 138 demand notice
# ---------------------------------------------------------------------------

_CHEQUE_CONTEXT = (
    "A Section 138 demand notice must be sent within 30 days of the bank's return memo, must give at "
    "least 15 days to pay, and must specifically demand the exact cheque amount; the complaint lies "
    "only where the cheque was presented for collection. Raising these points in a written reply "
    "records them at the earliest stage. Note also that once the cheque signature is admitted or "
    "proved, Section 139 presumes the cheque was for a legally enforceable debt -- a bare denial is "
    "not enough to rebut that presumption."
)


def _cheque_fact_lines(fields):
    f = fields or {}
    lines = []
    face = f.get("cheque_face_value")
    demand = f.get("demand_principal_amount")
    ndate = f.get("notice_date")
    memo = f.get("return_memo_date")
    win = f.get("payment_window_days_granted")
    pres = f.get("cheque_presentation_bank_location")
    filed = f.get("complaint_filed_location")

    if _KNOWN(face):
        lines.append(f"the cheque was for Rs. {face}")
    if _KNOWN(memo):
        lines.append(f"the bank returned the cheque unpaid on {memo}")
    if _KNOWN(demand) and _KNOWN(ndate):
        lines.append(f"the demand notice, dated {ndate}, requires payment of Rs. {demand}")
    elif _KNOWN(demand):
        lines.append(f"the demand notice requires payment of Rs. {demand}")
    elif _KNOWN(ndate):
        lines.append(f"the demand notice is dated {ndate}")
    if _KNOWN(win):
        lines.append(f"the notice allows {win} days to pay")
    if _KNOWN(pres) and _KNOWN(filed):
        lines.append(f"the cheque was presented for collection at {pres}; the complaint is stated to be "
                     f"filed or expected at {filed}")
    elif _KNOWN(pres):
        lines.append(f"the cheque was presented for collection at {pres}")

    if not lines:
        lines.append("the key dates and amounts are [ to be filled in ]")
    return lines


def _cheque_party_lines(fields):
    return [
        f"Name of the person who issued the cheque (you): {FILL}",
        f"Name and address of the complainant / their advocate: {FILL}",
        f"Cheque number, date and drawee bank: {FILL}",
        f"Date the demand notice was received: {FILL}",
        f"Court where the complaint is, or may be, filed: {FILL}",
    ]


def assemble_cheque_content(full_analysis):
    """Cheque-domain content, written from the drawer's side (the person
    who issued the cheque and received the demand notice). Grounds are the
    notice / complaint defects the S.138 checks found."""
    compliance = (full_analysis or {}).get("compliance", {}) or {}
    checks = compliance.get("compliance_checks", []) or []
    fields = (full_analysis or {}).get("extracted_fields", {}) or {}

    grounds = _build_grounds(checks)
    return {
        "domain": "cheque",
        "facts": _cheque_fact_lines(fields),
        "party": _cheque_party_lines(fields),
        "grounds": grounds,
        "key_dates": [],
        "to_verify": _build_to_verify(checks),
        "context_note": _CHEQUE_CONTEXT,
        "no_defect": not grounds,
        "sections": ["138 NI Act"],
    }


def _render_cheque_understanding(c):
    out = ["NOTES ON THE POSITION REGARDING THE BOUNCED-CHEQUE NOTICE", "",
           f"[{_DRAFT_HEADER}]", "",
           "WHAT THE RECORD SHOWS", "On the information available:"]
    out += [f"- {line[0].upper() + line[1:]}." for line in c["facts"]]
    out += ["", "DETAILS TO FILL IN"]
    out += [f"- {p}" for p in c["party"]]
    out += [""]

    if c["grounds"]:
        out += ["POINTS IN THE NOTICE OR COMPLAINT THAT MAY NOT COMPLY"]
        for i, g in enumerate(c["grounds"], 1):
            line = f"{i}. {g['heading']} - this {_ground_verb(g)}. {g['finding']}"
            if g["citation"]:
                line += f" (Reference: {g['citation']})"
            out.append(line)
        out += [""]
    else:
        out += ["No procedural defect in the notice was identified on the information available. This "
                "does not mean none exists - only that nothing in what was provided shows one.", ""]

    if c["to_verify"]:
        out += ["STILL TO CONFIRM"]
        out += [f"- {t}" for t in c["to_verify"]]
        out += [""]

    out += ["HOW A SECTION 138 CASE WORKS", c["context_note"], ""]
    return "\n".join(out).rstrip() + "\n"


def _render_cheque_reply(c):
    out = [
        "To,",
        "[ name and address of the complainant / their advocate ]",
        "",
        "From,",
        "[ your name and address ]",
        "",
        f"Subject: Reply to the statutory notice under Section 138 of the Negotiable Instruments Act, "
        f"1881, dated {FILL}, concerning cheque no. {FILL}.",
        "",
        f"[{_DRAFT_HEADER}]",
        "",
        "Sir / Madam,",
        "",
        "1. The notice under reply is under consideration. This reply is issued without prejudice to, "
        "and with an express reservation of, all rights, contentions and defences available in law.",
        "2. On the information available, the notice / proposed complaint appears to suffer from the "
        "following defects:",
        "",
    ]
    if c["grounds"]:
        for idx, g in enumerate(c["grounds"]):
            letter = chr(ord("a") + idx)
            line = f"   {letter}) {g['heading']} - this {_ground_verb(g)}. {g['finding']}"
            if g["citation"]:
                line += f" (Reference: {g['citation']})"
            out.append(line)
    else:
        out.append("   (No specific procedural defect in the notice is presently identified; the "
                   "contents of the notice are not admitted and are put to strict proof.)")
    out += ["",
            "3. Without admitting any liability, and without prejudice to the above, the claim in the "
            "notice is not admitted and is disputed for the reasons set out above and for such further "
            "reasons as may be raised.",
            "4. You are called upon to take the above on record. All rights and contentions of the "
            "sender are expressly reserved.",
            "",
            "Yours faithfully,",
            "",
            "[ name ]",
            "[ address / contact number ]",
            "[ date ]",
            "",
            "[ Send this reply promptly and by a mode that gives proof of despatch and delivery "
            "(registered post / courier with tracking), and keep the receipts. ]"]
    return "\n".join(out).rstrip() + "\n"


def _render_cheque_magistrate(c):
    jur = [g for g in c["grounds"] if "presented for collection" in g["heading"].lower()]
    other = [g for g in c["grounds"] if g not in jur]
    ordered = jur + other
    out = [
        "IN THE COURT OF [ name of the Magistrate ], AT [ place where the complaint is filed ]",
        "",
        f"In Complaint Case No. {FILL} under Section 138 of the Negotiable Instruments Act, 1881",
        "",
        "[ complainant's name ]  ... Complainant",
        "versus",
        "[ your name ]  ... Accused",
        "",
        "APPLICATION ON BEHALF OF THE ACCUSED REGARDING THE TERRITORIAL "
        "JURISDICTION OF THIS HON'BLE COURT",
        "",
        f"[{_DRAFT_HEADER}]",
        "",
        "MOST RESPECTFULLY SHOWETH:",
        "",
    ]
    for i, fact in enumerate(c["facts"], 1):
        out.append(f"{i}. That {fact}.")
    out += ["", "GROUNDS", ""]
    for idx, g in enumerate(ordered):
        letter = chr(ord("A") + idx)
        verb = "does not appear to have been complied with" if g["hedged"] else "was not complied with"
        body = f"{letter}. {g['heading']}: it is submitted that this requirement {verb}. {g['finding']}"
        if g["citation"]:
            body += f" This is contrary to {g['citation']}."
        out.append(body)
    out += ["", "PRAYER", "",
            "It is therefore most respectfully prayed that this Hon'ble Court may be pleased to:",
            "a) return the complaint for presentation before the court having territorial jurisdiction, "
            "the cheque having been presented for collection at [ place ];",
            "b) pass such further or other order as this Hon'ble Court may deem fit and proper in the "
            "interest of justice."]
    out += ["", "", "VERIFICATION", "",
            "Verified at [ place ] on [ date ] that the contents of the above application are true to "
            "the best of my knowledge and belief.",
            "",
            "[ place ]                                          [ signature ]",
            "[ date ]                                           [ name - the accused / counsel ]"]
    return "\n".join(out).rstrip() + "\n"


_ASSEMBLERS.update({
    "arrest": assemble_draft_content,
    "freeze": assemble_freeze_content,
    "cheque": assemble_cheque_content,
})

_RENDERERS = {
    "understanding": _render_understanding,
    "magistrate": _render_magistrate,
    "sp": _render_sp,
    "freeze_understanding": _render_freeze_understanding,
    "freeze_magistrate": _render_freeze_magistrate,
    "freeze_sp": _render_freeze_sp,
    "cheque_understanding": _render_cheque_understanding,
    "cheque_reply": _render_cheque_reply,
    "cheque_magistrate": _render_cheque_magistrate,
}


def _section_number_note(content):
    """A trailing 'NOTE ON SECTION NUMBERS' block when any part of the
    draft's substance still cites the pre-2024 codes (IPC / CrPC) -- the
    grounds carry citation tags like '[S.187 BNSS / S.167(2) CrPC]' and
    '[S.46(4) CrPC / Sheela Barse]', and a repealed provision with no
    successor (e.g. IPC 124A) must never stand unannotated in a citizen's
    filing. Uses statute_concordance.scan_old_refs -- a checked lookup, no
    LLM. Returns a list of lines, or [] when nothing old is cited."""
    parts = list(content.get("facts", []))
    for g in content.get("grounds", []):
        parts += [g.get("heading", ""), g.get("finding", ""), g.get("citation", "")]
    parts += list(content.get("to_verify", []))
    parts += list(content.get("key_dates", []))
    parts += list(content.get("matters_raised", []))
    for a in content.get("authorities", []):
        parts += [a.get("quote", ""), a.get("citation", "")]
    if content.get("context_note"):
        parts.append(content["context_note"])
    parts += [str(s) for s in content.get("sections", [])]

    try:
        from statute_concordance import scan_old_refs
    except Exception:
        return []
    refs = scan_old_refs("\n".join(p for p in parts if p))
    if not refs:
        return []

    out = ["NOTE ON SECTION NUMBERS",
           "Some references above are to the pre-2024 codes (the Indian Penal Code / the Code of "
           "Criminal Procedure). Under the codes now in force:"]
    for r in refs:
        if r["new"] is None:
            out.append(f"- {r['old']}: no corresponding provision in the recodified law "
                       "(repealed without re-enactment) - do not rely on it as current law.")
        else:
            tail = (" (renumbered AND substantively altered - confirm the specific point relied on)"
                    if r["changed"] else "")
            out.append(f"- {r['old']} now corresponds to {r['new']}{tail}.")
    out.append("These correspondences follow the official NCRB reference tables and should be "
               "confirmed against the current bare Act for the specific point relied on.")
    return out


def render_draft(content, target):
    """`content` from assemble_for() / assemble_*_content(); `target` a key
    of _RENDERERS. Returns plain text. A 'NOTE ON SECTION NUMBERS' block is
    appended when the draft still cites the old IPC/CrPC numbering."""
    if target not in _RENDERERS:
        raise ValueError(f"unknown draft target {target!r}; expected one of {list(_RENDERERS)}")
    body = _RENDERERS[target](content)
    note = _section_number_note(content)
    if note:
        body = body.rstrip() + "\n\n" + "\n".join(note) + "\n"
    return body


def draft_for(full_analysis, target, *, authorities=None, matters_raised=None):
    """Convenience: detect domain, assemble, render in one call.
    `authorities` / `matters_raised` -- see assemble_for."""
    content = assemble_for(full_analysis, authorities=authorities, matters_raised=matters_raised)
    if content is None:
        raise ValueError("draft_layer has no template for this analysis")
    return render_draft(content, target)


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
    freeze_demo = {
        "extracted_fields": {
            "scope": "entire account", "specific_amount_stated": "40000",
            "account_holder_intimated": False, "written_order_shown": False,
            "court_or_magistrate_mentioned": False,
        },
        "compliance": {"compliance_checks": [
            {"requirement": "Attachment/freeze authorized via Section 107 BNSS court order [Malabar Gold (2026) / Tapas D. Neogy (1999)]",
             "status": "May be Non-Compliant",
             "explanation": "No legal section was cited to justify this freeze at all. A freeze effected "
                            "without invoking this process, on bare police request alone, may be illegal -- see Malabar Gold (2026)."},
            {"requirement": "Blanket freeze under 106/107 BNSS restricted to disputed amount [Neelkanth Pharma Logistics (2025) / Malabar Gold (2026)]",
             "status": "Non-Compliant",
             "explanation": "Entire account frozen despite a specific disputed amount (Rs. 40000) being identifiable."},
            {"requirement": "Account holder intimated of freeze after the fact [Malabar Gold (2026)]",
             "status": "May be Non-Compliant",
             "explanation": "Account holder not intimated -- the freeze was discovered only at the bank/ATM."},
        ]},
    }
    cheque_demo = {
        "extracted_fields": {
            "cheque_face_value": 250000, "demand_principal_amount": 300000,
            "notice_date": "05-08-2026", "return_memo_date": "20-07-2026",
            "payment_window_days_granted": 10,
            "cheque_presentation_bank_location": "Pune", "complaint_filed_location": "Nagpur",
        },
        "compliance": {"compliance_checks": [
            {"requirement": "Demand specifically states the correct cheque amount [Suman Sethi (2000) via Kaveri Plastics (2025)]",
             "status": "Non-Compliant",
             "explanation": "Demand (Rs.300,000) does not match cheque face value (Rs.250,000). Per Kaveri "
                            "Plastics (2025), a notice demanding an amount that does not match the actual cheque can be fatal to the complaint."},
            {"requirement": "At least 15 days granted to pay [S.138(c)]",
             "status": "Non-Compliant", "explanation": "Notice grants 10 days (statutory minimum: 15)."},
            {"requirement": "Complaint filed where cheque was presented for collection [Prakash Chimanlal Sheth (2025) / S.142(2) NI Act]",
             "status": "Non-Compliant",
             "explanation": "The complaint is recorded as filed at 'Nagpur', but the cheque was presented for collection at 'Pune'."},
        ]},
    }
    for demo_fa, targets in ((demo, ("understanding", "magistrate", "sp")),
                             (freeze_demo, ("freeze_understanding", "freeze_magistrate", "freeze_sp")),
                             (cheque_demo, ("cheque_understanding", "cheque_reply", "cheque_magistrate"))):
        for t in targets:
            print("=" * 70)
            print(f"TARGET: {t}")
            print("=" * 70)
            print(draft_for(demo_fa, t))
