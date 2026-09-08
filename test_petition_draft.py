"""
test_petition_draft.py

Unit tests for the deterministic criminal-petition builder. No Streamlit,
no LLM, no API calls. The PDF test is skipped if reportlab isn't importable.

Run with: python test_petition_draft.py
"""

import sys

import arrest_safeguard_checklist as asc
import petition_draft as pd
from arrest_safeguard_checklist import YES, NO, UNSURE, NOT_A_WOMAN

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


Q = ("My brother was arrested four nights ago in a cheating and forgery case tied to a "
     "property society. Nobody showed him or us anything in writing. He was produced "
     "before the magistrate only on the third day.")

ans = {
    "written_grounds": NO, "notice_before_arrest": NO, "family_informed": NO,
    "produced_24h": NO, "memo_witnessed": UNSURE, "medical_exam": UNSURE,
    "default_bail": UNSURE, "night_arrest_woman": NOT_A_WOMAN,
    "female_officer": NOT_A_WOMAN,
}
ev = asc.evaluate(ans)
txt = pd.from_checklist(Q, ev, civil_dispute=True, offence_sections=["318(4)", "336(3)"])

# ---- structure ----
for block in ("IN THE HIGH COURT OF", "IN THE MATTER OF:", "MOST RESPECTFULLY SHOWETH:",
              "GROUNDS", "PRAYER", "INTERIM PRAYER", "AFFIDAVIT", "OATH / VERIFICATION",
              "INDEX", "VERIFICATION"):
    check(block in txt, f"draft contains the {block!r} block")

check(txt.count("IN THE MATTER OF:") >= 4, "the IN THE MATTER OF cascade has >= 4 clauses")
check("-Versus-" in txt and "... Respondents" in txt, "cause title has parties + respondents")
check("[ ___ ]" in txt, "unknown facts are left as [ ___ ] placeholders")
check("NOT INDEPENDENTLY VERIFIED" in txt, "case passages carry the NOT-VERIFIED flag")

# ---- grounds: one per 'Not followed', in the FOR THAT form ----
for lead in ("the grounds of the arrest were not furnished", "no notice to appear was issued",
             "no relative or friend", "the arrested person was not produced before a Magistrate"):
    check(f"FOR THAT {lead}" in txt, f"ground present: {lead!r}")
check("Vihaan Kumar" in txt and "Arnesh Kumar" in txt and "D.K. Basu" in txt,
      "grounds cite the governing judgments")

# ---- 'to confirm' paragraph carries the unsure items + default bail ----
check("could not be confirmed from the information available" in txt,
      "matters-to-confirm paragraph is present")
check("M. Ravindran" in txt and "Rakesh Kumar Paul" in txt,
      "default-bail authorities appear in the to-confirm paragraph")

# ---- civil-dispute flag drives the quashing relief ----
check("quashing of the First Information Report" in txt or "quash the said First Information Report" in txt,
      "civil_dispute=True -> petition asks for quashing")
check("Md. Ibrahim" in txt and "Bhajan Lal" in txt,
      "civil_dispute=True -> abuse-of-process ground with its cases")

# ---- offence sections flow into the cause title ----
check("318(4), 336(3)" in txt, "offence sections appear in the cause title")

# ---- background seeded from the person's own words, verbatim, quoted ----
check('As stated by the Petitioner: "My brother was arrested four nights ago' in txt,
      "background paragraph quotes the person's own account")

# ---- no civil dispute, no sections: still a valid petition ----
ev2 = asc.evaluate({"written_grounds": NO})
t2 = pd.from_checklist("my cousin was arrested", ev2)
check("FOR THAT the grounds of the arrest were not furnished" in t2, "minimal input still builds a ground")
check("quash" not in t2.lower(), "no civil_dispute -> no quashing relief")
check("Sections [ ___ ] of the Bharatiya Nyaya Sanhita" in t2, "no sections -> placeholder in cause title")

# ---- all-clear: still produces the 'satisfy itself' fallback ground ----
ev3 = asc.evaluate({"written_grounds": YES, "produced_24h": YES})
t3 = pd.from_checklist("arrested", ev3)
check("no specific procedural defect is asserted" in t3,
      "all-compliant answers -> the 'Court may satisfy itself' fallback ground")

# ---- doc-check adapter ----
doc = {
    "ok": True, "is_arrest_document": True, "n_defects": 2, "n_unknown": 1,
    "overall": "2 safeguard(s) appear not to have been followed.",
    "checks": [
        {"plain": "Written grounds of arrest furnished (Prabir Purkayastha / s.47 BNSS)",
         "status": "Non-Compliant", "bucket": "bad",
         "explanation": "Per Vihaan Kumar (2025 INSC 162), failure to furnish written grounds violates Article 22(1)."},
        {"plain": "Produced before a magistrate within 24 hours",
         "status": "Non-Compliant", "bucket": "bad",
         "explanation": "Produced 41.0 hours after arrest — exceeds the constitutional 24-hour limit."},
        {"plain": "A medical examination was conducted at arrest",
         "status": "Cannot Determine", "bucket": "unknown",
         "explanation": "The document is silent on any medical examination."},
    ],
}
td = pd.from_doc_check("my brother was arrested and beaten", doc, civil_dispute=False)
check("FOR THAT the grounds of the arrest were not furnished" in td,
      "doc-check adapter -> written-grounds ground")
check("FOR THAT the arrested person was not produced before a Magistrate" in td,
      "doc-check adapter -> 24-hour ground")
check("could not be confirmed" in td, "doc-check 'Cannot Determine' -> to-confirm paragraph")

# ---- cheque / freeze petitions from a chat-answer-shaped dict ----
_cheque_answer = {
    "state": "single_match", "redirect_domain": "cheque_bounce",
    "matches": [
        {"case_name": "Rangappa v Sri Mohan", "citation": "(2010) 11 SCC 441",
         "context_note": "Rangappa v Sri Mohan: the Section 139 presumption INCLUDES the "
                         "debt and is rebuttable on a preponderance of probabilities."},
        {"case_name": "Prakash Chimanlal Sheth v Jagruti Keyur Rajpopat",
         "citation": "2025 INSC 897",
         "context_note": "Prakash Chimanlal Sheth: jurisdiction lies where the payee's bank "
                         "branch is."},
    ],
}
ct = pd.from_cheque_answer("he filled in the amount on my blank cheque and it bounced", _cheque_answer)
_ctn = " ".join(ct.split())  # whitespace-normalised, for phrases that cross a wrap boundary
check("Section 138 of the Negotiable Instruments Act" in _ctn, "cheque petition names s.138 NI Act")
check("Section 528 of the Bharatiya Nagarik Suraksha Sanhita" in _ctn, "cheque petition invokes s.528 BNSS")
check("MOST RESPECTFULLY SHOWETH" in ct and "PRAYER" in ct and "AFFIDAVIT" in ct and "INDEX" in ct,
      "cheque petition has the full packet")
check("FOR THAT there was no legally enforceable debt" in ct, "cheque petition has the no-debt ground")
check("As held in Rangappa v Sri Mohan ((2010) 11 SCC 441)" in ct, "cheque petition cites Rangappa")
check("INCLUDES" not in ct, "emphasis-caps in the doctrine note are de-emphasised")
check("NOT INDEPENDENTLY VERIFIED" in ct, "cheque petition keeps the verified-flag discipline")
check("[ ___ ]" in ct, "cheque petition leaves unknowns as placeholders")
check("bail application before the Court of Session" not in ct,
      "cheque petition does NOT carry the arrest-specific header note")

_freeze_answer = {
    "state": "single_match", "redirect_domain": "freeze",
    "matches": [
        {"case_name": "State of Maharashtra v Tapas D. Neogy", "citation": "(1999) 7 SCC 685",
         "context_note": "Tapas D. Neogy: a bank account is property and police CAN direct "
                         "a freeze, subject to two preconditions."},
        {"case_name": "Neelkanth Pharma Logistics Pvt. Ltd. v Union of India",
         "citation": "2025 SCC OnLine Del 1055",
         "context_note": "Neelkanth Pharma: a blanket freeze when only a specific sum is "
                         "traceable is disproportionate; lien the identifiable amount."},
    ],
}
ft = pd.from_freeze_answer("my whole account was frozen over a payment from one customer", _freeze_answer)
_ftn = " ".join(ft.split())
check("Section 107 of the Bharatiya Nagarik Suraksha Sanhita" in _ftn,
      "freeze petition invokes BNSS s.107")
check("FOR THAT the account was frozen without any order of the jurisdictional Magistrate" in _ftn,
      "freeze petition has the no-Magistrate-order ground")
check("FOR THAT the freeze extends to the whole account" in _ftn,
      "freeze petition has the disproportionate-freeze ground")
check("As held in State of Maharashtra v Tapas D. Neogy" in _ftn, "freeze petition cites Tapas Neogy")
check("withdraw the freeze" in _ftn, "freeze petition prayer asks to lift the freeze")

# empty matches -> still a valid petition, no authorities block
_bare = {"state": "single_match", "redirect_domain": "cheque_bounce", "matches": []}
bt = pd.from_cheque_answer("cheque bounced", _bare)
check("FOR THAT there was no legally enforceable debt" in bt,
      "cheque petition with no authorities still has its contentions")
check("As held in" not in bt, "no authorities -> no 'legal position' block")


# ---- PDF ----
try:
    import os, tempfile
    for name, body in (("_test_petition", txt), ("_test_cheque", ct), ("_test_freeze", ft)):
        p = pd.to_pdf(body, output_path=os.path.join(tempfile.gettempdir(), name + ".pdf"))
        check(os.path.exists(p) and os.path.getsize(p) > 1500, f"to_pdf writes a non-trivial PDF ({name})")
        os.remove(p)
except ImportError:
    print("[SKIP] PDF test — reportlab not importable")


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
sys.exit(0)
