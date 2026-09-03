"""
settled_doctrine_whitelist.py

The gate that decides whether Lane B's live "related judgments" panel is
shown to a chat user, or kept internal (review bundle only).

WHY (the middle-path decision, 2026-09-03): live-retrieved judgments are
unverified -- nobody has checked they are on point, still good law, or not
under appeal. Showing them is defensible ONLY where the underlying
doctrine is settled enough that a stray High Court judgment cannot state
the law wrongly, and even an appealed one still states the right rule.
This module is that "settled enough" list.

`is_covered(issues)` returns True only when EVERY decomposed issue maps to
a whitelisted topic. One non-whitelisted issue -> the whole panel is
suppressed for that question (the review bundle is still written for
hand-curation). Matching is pure Python -- a whitelisted section number
in the issue's section_hooks, or a tight keyword pattern on the issue
text. No model.

Each entry is a ONE-TIME human judgement that the doctrine is stable
across the IPC->BNS recodification. Widening this list is a deliberate
act, never a default. Same curated-map shape as statute_doctrine_map.py.
"""

import re

# name -> {
#   "sections": set of "ACT NUM" strings (BNS/BNSS or IPC/CrPC) that mark
#               this topic; matched against an issue's section_hooks AND
#               its concordance-resolved old_sections,
#   "patterns": list of compiled regexes matched against the issue text,
#   "note":     why it is considered settled (for the reviewer / bundle),
# }
_WHITELIST = {
    "fir_copy_right": {
        "sections": {"BNSS 173", "CrPC 154", "BNSS 230", "CrPC 207"},
        "patterns": [
            re.compile(r"\bF\.?I\.?R\.?\b.{0,40}\b(copy|copies|not (given|provided|supplied)|refus)", re.I),
            re.compile(r"\bcop(y|ies) of the (F\.?I\.?R|first information report)", re.I),
            re.compile(r"\b(F\.?I\.?R).{0,30}\b(upload|website|police station)", re.I),
        ],
        "note": "Youth Bar Association of India v Union of India (2016) 9 SCC 473 -- "
                "consistently applied for a decade; FIR-copy right is not in doubt.",
    },
    "arnesh_kumar_arrest_notice": {
        "sections": {"BNSS 35", "CrPC 41", "CrPC 41A", "CrPC 41(2)"},
        "patterns": [
            re.compile(r"\barrest(ed)?\b.{0,50}\b(without (a )?warrant|notice (before|to appear)|41A|35)", re.I),
            re.compile(r"\bnotice (to appear|before arrest|under section 41a|under section 35)", re.I),
            re.compile(r"\barrest(ed)?\b.{0,40}\b(not named|name (was )?not).{0,20}\bF\.?I\.?R", re.I),
            re.compile(r"\b(unnecessary|casual|routine|mechanical) arrest", re.I),
        ],
        "note": "Arnesh Kumar v State of Bihar (2014) 8 SCC 273 -- foundational, "
                "universally applied; the S.41A/S.35 notice requirement is settled.",
    },
    "grounds_of_arrest_communicated": {
        "sections": {"BNSS 47", "CrPC 50", "CrPC 50A"},
        "patterns": [
            re.compile(r"\bgrounds (of|for) (the )?arrest\b", re.I),
            re.compile(r"\b(reason|reasons) (for|of) (the )?arrest.{0,30}\bnot (told|informed|communicated|given|explained)", re.I),
            re.compile(r"\bnot (told|informed).{0,20}\bwhy\b.{0,20}\barrest", re.I),
        ],
        "note": "Pankaj Bansal (2024) 7 SCC 576 / Prabir Purkayastha (2024) 8 SCC 254 -- "
                "grounds of arrest must be meaningfully communicated. NOTE: the narrower "
                "question of whether grounds must be IN WRITING in every case is under a "
                "larger-bench reference (Vihaan Kumar) -- the general communication "
                "requirement is what is whitelisted here.",
    },
    "default_bail": {
        "sections": {"BNSS 187", "CrPC 167", "CrPC 167(2)"},
        "patterns": [
            re.compile(r"\bdefault bail\b", re.I),
            re.compile(r"\b(charge ?sheet|final report).{0,40}\b(not (filed|submitted)|delay|beyond|within|time limit)", re.I),
            re.compile(r"\b(60|sixty|90|ninety) days?\b.{0,40}\b(charge ?sheet|custody|bail|investigation)", re.I),
            re.compile(r"\b(kept|held|custody).{0,30}\b(60|sixty|90|ninety|two months|three months)\b", re.I),
        ],
        "note": "Section 167(2) CrPC / Section 187 BNSS -- decades of consistent Supreme "
                "Court law (Rakesh Kumar Paul, Bikramjit Singh, ...); the indefeasible "
                "default-bail right is settled.",
    },
    "dk_basu_safeguards": {
        "sections": {"CrPC 41B", "CrPC 41C", "CrPC 41D", "CrPC 46", "BNSS 43", "BNSS 46", "BNSS 48"},
        "patterns": [
            re.compile(r"\b(D\.?\s?K\.?\s?Basu|arrest memo|memo of arrest|inspection memo)\b", re.I),
            re.compile(r"\b(medical|doctor|physician|check-?up)\w*.{0,25}\b(not|never|no|denial|denied|refus|without)\b", re.I),
            re.compile(r"\b(not|never|no|denial|denied|refus|without)\b.{0,30}\b(medical|doctor|physician|check-?up)", re.I),
            re.compile(r"\b(custodial (violence|torture|abuse|assault)|third[- ]degree)\b", re.I),
            re.compile(r"\b(assault|beat(en|ing)?|slap(ped|ping)?|tortur|thrash|kept awake|deprivation of sleep|sleep\w* deprivation|denied sleep|not allowed to sleep|inhuman|degrading treatment|third[- ]degree)\b.{0,50}\b(custody|police station|lock[- ]?up|remand|interrogat|thana|detention)\b", re.I),
            re.compile(r"\b(custody|police station|lock[- ]?up|interrogat|detention|remand)\b.{0,50}\b(assault|beat(en|ing)?|slap(ped|ping)?|tortur|thrash|injur|bruis|kept awake|deprivation of sleep|not allowed to sleep|inhuman|degrading)\b", re.I),
            re.compile(r"\b(injur(y|ies)|bruis|marks on (his|her|the) body).{0,40}\b(not (record|document|note)|no medical|not examined)\b", re.I),
            re.compile(r"\b(family|relative|friend|next friend).{0,30}\b(not (informed|told)|never informed)\b", re.I),
            re.compile(r"\bhandcuff", re.I),
        ],
        "note": "D.K. Basu v State of West Bengal (1997) 1 SCC 416 -- foundational "
                "custodial safeguards (arrest memo, medical exam every 48h, injury "
                "recording, family intimation); not in doubt. Also the settled "
                "prohibition on custodial violence (Nilabati Behera, Prakash Kadam).",
    },
    "twenty_four_hour_production": {
        "sections": {"BNSS 58", "CrPC 57"},
        "patterns": [
            re.compile(r"\b(24|twenty[- ]four)[- ]hours?\b.{0,40}\b(magistrate|court|produc)", re.I),
            re.compile(r"\bnot produced\b.{0,30}\bmagistrate", re.I),
            re.compile(r"\bproduc(ed|tion)\b.{0,30}\bmagistrate\b.{0,30}\b(24|twenty)", re.I),
            re.compile(r"\barticle 22\s*\(?\s*2", re.I),
        ],
        "note": "Article 22(2) of the Constitution / Section 57 CrPC / Section 58 BNSS -- "
                "the 24-hour production rule is constitutional and settled.",
    },
    "right_to_lawyer_on_arrest": {
        "sections": {"BNSS 38", "CrPC 41D", "CrPC 303", "BNSS 340"},
        "patterns": [
            re.compile(r"\b(meet|consult|access to|see).{0,20}\b(a )?(lawyer|advocate|counsel)\b", re.I),
            re.compile(r"\b(lawyer|advocate|counsel).{0,25}\b(not (allowed|permitted)|denied|refused)\b", re.I),
            re.compile(r"\bright to (a )?(lawyer|advocate|legal (aid|representation))", re.I),
        ],
        "note": "Article 22(1) / Section 41D CrPC / Section 38 BNSS -- the right of an "
                "arrested person to consult a lawyer is settled.",
    },
}


def _issue_section_labels(issue):
    """All section labels attached to an issue -- the model's section_hooks
    plus, if present, the concordance-resolved old_sections that
    build_anchors adds. Normalised to 'ACT NUM'."""
    labels = set()
    for key in ("section_hooks", "new_sections", "old_sections"):
        for lbl in issue.get(key, []) or []:
            labels.add(str(lbl).strip())
    return labels


def match_issue(issue):
    """The whitelist topic name this issue maps to, or None.

    A keyword-pattern match is tried across ALL topics FIRST, then a
    section-number match. The decomposition's section_hooks are a coarse
    guess -- a theft arrest gets 'BNSS 35' tagged onto every issue,
    including 'denied a medical exam' -- so a specific phrase ('medical
    check-up denied' -> D.K. Basu) must beat a broad section ('BNSS 35'
    -> Arnesh Kumar). The gate decision (is_covered) is unaffected by the
    order; the topic LABEL is what this fixes."""
    if not isinstance(issue, dict):
        return None
    text = f"{issue.get('issue', '')} {issue.get('hook_phrase', '')}"
    for name, entry in _WHITELIST.items():
        if any(p.search(text) for p in entry["patterns"]):
            return name
    sections = _issue_section_labels(issue)
    for name, entry in _WHITELIST.items():
        if sections & entry["sections"]:
            return name
    return None


def is_covered(issues):
    """True only when EVERY issue maps to a whitelisted settled-doctrine
    topic. Empty / falsy -> False (nothing to show safely)."""
    if not issues:
        return False
    return all(match_issue(i) is not None for i in issues)


def coverage_report(issues):
    """{'covered': bool, 'by_issue': [(issue_text, topic_or_None), ...],
    'uncovered': [issue_text, ...]} -- for the review bundle and logs, so
    a human can see exactly which issue kept the panel hidden."""
    by_issue = [((i.get("issue") if isinstance(i, dict) else str(i)), match_issue(i))
                for i in (issues or [])]
    uncovered = [txt for txt, topic in by_issue if topic is None]
    return {
        "covered": bool(issues) and not uncovered,
        "by_issue": by_issue,
        "uncovered": uncovered,
    }


def list_topics():
    """The whitelisted topic names + their 'settled because' notes."""
    return {name: entry["note"] for name, entry in _WHITELIST.items()}


if __name__ == "__main__":
    import json
    samples = [
        [{"issue": "arrest of a person not named in the FIR", "hook_phrase": "name was not in the FIR", "section_hooks": ["BNSS 35"]},
         {"issue": "chargesheet not filed within the time limit", "hook_phrase": "no chargesheet", "section_hooks": ["BNSS 187"]}],
        [{"issue": "police froze my bank account", "hook_phrase": "bank account was frozen", "section_hooks": ["BNSS 107"]}],
        [{"issue": "denied access to a lawyer in custody", "hook_phrase": "not allow a lawyer to meet him", "section_hooks": []},
         {"issue": "charged under the organised crime provision", "hook_phrase": "organised crime", "section_hooks": ["BNS 111"]}],
    ]
    for s in samples:
        print(json.dumps(coverage_report(s), indent=1, default=str))
