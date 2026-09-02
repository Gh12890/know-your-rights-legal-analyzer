"""
test_results_surface.py

Covers the UX-redesign plumbing (2026-09-02): the audience-split PDFs
(main._build_kyr_pdf), the plain-language register of layman_summary,
the freeze/cheque payload -> full_analysis wrapper, and the
deterministic plain fallback. No API calls (layman_summary's client is
absent under a bare import, so it returns None and the fallback path is
what actually runs here).

Run: python test_results_surface.py
"""

import os
import sys

import fitz  # pymupdf

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


def _pdf_text(path):
    return " ".join(pg.get_text() for pg in fitz.open(path))


_FA = {
    "classification": {"document_type": "Police & Criminal Process", "sub_type": "Arrest", "reasoning": "t"},
    "missing_info": {"missing_or_unclear": ["Arrest time not stated"], "completeness_assessment": "x"},
    "compliance": {"compliance_checks": [
        {"requirement": "S.35(3) BNSS notice before arrest [Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273]",
         "status": "Non-Compliant", "explanation": "No notice was issued."},
        {"requirement": "Produced before magistrate within 24 hours [Art. 22(2)/S.58 BNSS]",
         "status": "Cannot Determine", "explanation": "Arrest time not stated."},
    ], "overall_assessment": "x"},
    "checklist": ["Arrest memo", "FIR copy"],
    "urgency": {"urgency_level": "Cannot Determine", "deadline_message": "", "days_remaining": None},
    "severity": {"severity_score": 4, "severity_label": "Serious concerns", "unresolved_checks": 1},
    "bail_pathway": None,
    "extracted_fields": {"sections_cited": ["303"]},
}

# ---- the two diagnostic PDFs are audience-separated ----

import main

a = main.generate_analysis_pdf(_FA, "scratch_a.pdf")
n = main.generate_next_steps_pdf(_FA, plain_text="You were arrested. Ask for the arrest memo.", output_path="scratch_n.pdf")
at, nt = _pdf_text(a), _pdf_text(n)

check("Procedural Compliance Findings" in at,
      "analysis PDF has the clause-by-clause compliance findings")
check("Arnesh Kumar" in at,
      "analysis PDF keeps the case-law citation")
check("Documents to gather" not in at and "Documents to Gather" not in at,
      "analysis PDF has NO 'documents to gather' checklist")
check("Recommended Action" not in at,
      "analysis PDF has NO 'recommended action plan'")

check("Documents to gather" in nt,
      "next-steps PDF DOES have the 'documents to gather' checklist")
check("Ask for the arrest memo" in nt,
      "next-steps PDF carries the plain-language summary text")
check("Procedural Compliance Findings" not in nt,
      "next-steps PDF does NOT repeat the clause-by-clause audit")

check(main.generate_compliance_brief(_FA, "scratch_c.pdf") and _pdf_text("scratch_c.pdf") == at,
      "generate_compliance_brief back-compat alias == the analysis PDF")

for f in ("scratch_a.pdf", "scratch_n.pdf", "scratch_c.pdf"):
    os.remove(f)

# ---- layman_summary: plain register formats without crashing, strips citations ----

from layman_summary import _format_compliance_for_prompt, PLAIN_SUMMARY_PROMPT, generate_layman_summary

plain_fmt = _format_compliance_for_prompt(_FA["compliance"], keep_citations=False)
check("[Arnesh Kumar" not in plain_fmt and "Arnesh Kumar" not in plain_fmt,
      "plain register strips the [citation] bracket before the prompt")
check("[Arnesh Kumar" in _format_compliance_for_prompt(_FA["compliance"], keep_citations=True),
      "counsel register keeps the [citation] bracket")
check("{compliance_summary}" in PLAIN_SUMMARY_PROMPT and "{statute_text}" not in PLAIN_SUMMARY_PROMPT,
      "PLAIN_SUMMARY_PROMPT has no statute_text slot (plain path never quotes statute)")
# the plain register runs end to end (real API if a key is present, else None)
_plain = generate_layman_summary(_FA["compliance"], _FA["severity"], None,
                                 offence_name="theft", audience="plain")
check(_plain is None or (isinstance(_plain, str) and len(_plain) > 20),
      "generate_layman_summary(audience='plain') returns a string or None, never raises")
if _plain:
    low = _plain.lower()
    check("section 35" not in low and "arnesh kumar" not in low and "cognizable" not in low,
          "the plain summary carries no section numbers, case names, or jargon")

# ---- app helpers: freeze/cheque wrapper + plain fallback ----

import app

fa_freeze = app._assessment_full_analysis("freeze", {
    "compliance_result": {"compliance_checks": [
        {"requirement": "Freeze cites a legal section", "status": "May be Non-Compliant", "explanation": "No section cited."}],
        "overall_assessment": "x"},
    "severity": {"severity_label": "Some concerns"},
    "fields_known": {"amount": "2 lakh"},
})
check(fa_freeze["classification"]["document_type"] == "Bank / Account Freezing"
      and fa_freeze["bail_pathway"] is None
      and fa_freeze["compliance"]["compliance_checks"][0]["status"] == "May be Non-Compliant",
      "_assessment_full_analysis('freeze', ...) produces a full_analysis-shaped dict")
check("checklist" in fa_freeze and isinstance(fa_freeze["checklist"], list),
      "the wrapped freeze analysis carries a document checklist")

fa_cheque = app._assessment_full_analysis("cheque_bounce", {
    "compliance_result": {"compliance_checks": [], "overall_assessment": "x"},
    "severity": {}, "fields_known": {}, "presumption_info": {"explanation": "e", "note": "n"},
})
check(fa_cheque["classification"]["document_type"] == "Cheque Bounce"
      and fa_cheque.get("presumption_info", {}).get("explanation") == "e",
      "_assessment_full_analysis('cheque_bounce', ...) carries presumption_info through")

fb = app._plain_fallback(_FA)
check("What was found" in fb and "What you can do now" in fb,
      "_plain_fallback has the plain structure")
check("Section 35" not in fb and "Arnesh Kumar" not in fb and "[" not in fb,
      "_plain_fallback strips section numbers and citation brackets")
check("District Legal Services Authority" in fb,
      "_plain_fallback points to a concrete free-help route, not just 'consult a lawyer'")

fb_clean = app._plain_fallback({"compliance": {"compliance_checks": [
    {"requirement": "X", "status": "Compliant", "explanation": "ok"}]}})
check("Nothing in the information given shows a clear procedural problem" in fb_clean,
      "_plain_fallback handles an all-clean analysis without implying wrongdoing")

# ---- the menu is exactly 4 options ----

check(len(app._MENU) == 4 and set(app._MENU.values()) == {"chat", "document", "guided", "triage"},
      "the entry menu is exactly 4 options -> chat/document/guided/triage")
check(app._HANDOFF_ROUTES == {"arrest_assess", "freeze_assess", "cheque_assess"},
      "the 3 handoff-only routes are defined")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
