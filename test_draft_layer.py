"""
test_draft_layer.py

Regression suite for draft_layer.py -- Project 3, the Bounded-Action /
Compliance-Drafting Layer (arrest, freeze and cheque-bounce domains).

Pure selection + templating: NO API calls, NO PDF at test time (a PDF
smoke check is one cheap call at the end). Every draft's substance comes
from an already-computed compliance finding; these tests pin that the
selection is faithful, the hedging is honest, and the envelope changes
with the target.

Run: python test_draft_layer.py
"""

import sys

from draft_layer import (
    assemble_draft_content,
    assemble_freeze_content,
    assemble_cheque_content,
    detect_draft_domain,
    available_targets,
    render_draft,
    draft_for,
    generate_draft_pdf,
)

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


def _fa(checks, fields=None):
    return {
        "extracted_fields": fields or {"sections_cited": ["303(2)"], "arrest_datetime_full": "12-07-2026 09:30"},
        "compliance": {"compliance_checks": checks},
    }


_NC_NOTICE = {
    "requirement": "S.35(3) BNSS notice before arrest [Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273]",
    "status": "Non-Compliant",
    "explanation": "Offence punishable up to 7 years; no prior notice to appear was issued.",
}
_MBNC_GROUNDS = {
    "requirement": "Written grounds of arrest furnished to arrestee [Vihaan Kumar, 2025 INSC 162]",
    "status": "May be Non-Compliant",
    "explanation": "The memo documents other safeguards but is silent on separate written grounds.",
}
_COMPLIANT_MEMO = {
    "requirement": "Arrest memo attested by witness [DK Basu (1997)]",
    "status": "Compliant",
    "explanation": "Witness attestation, family notification and medical exam are all recorded.",
}
_DEFAULT_BAIL_EXPIRED = {
    "requirement": "Default bail on chargesheet delay [S.187 BNSS / S.167(2) CrPC]",
    "status": "May be Non-Compliant",
    "explanation": "No chargesheet as of today. Default bail eligibility date was 20-08-2026 (13 days ago). "
                   "Default bail is now a matter of right.",
}
_CANNOT_DETERMINE = {
    "requirement": "Produced before magistrate within 24 hours [Art. 22(2)/S.58 BNSS]",
    "status": "Cannot Determine",
    "explanation": "Arrest date/time not stated; the clock cannot be computed.",
}

# ---- content assembly ----

c = assemble_draft_content(_fa([_NC_NOTICE, _MBNC_GROUNDS, _COMPLIANT_MEMO, _CANNOT_DETERMINE]))
check([g for g in c["grounds"] if "notice before arrest" in g["heading"].lower()],
      "a Non-Compliant check becomes a ground")
check([g for g in c["grounds"] if "Written grounds" in g["heading"]],
      "a May-be-Non-Compliant check also becomes a ground")
check(all(g["heading"] != "" for g in c["grounds"]) and not any("[" in g["heading"] for g in c["grounds"]),
      "ground headings have the '[citation]' tag stripped")
check(not any("Arrest memo attested" in g["heading"] for g in c["grounds"]),
      "a Compliant check is NOT turned into a ground")
check(c["grounds"][0]["hedged"] is False and c["grounds"][1]["hedged"] is True,
      "worst-first ordering: the Non-Compliant ground precedes the May-be one, and hedged flags are right")
check(all(g["citation"] for g in c["grounds"]),
      "every ground carries a non-empty citation")
check(c["grounds"][0]["citation"].startswith("Arnesh Kumar"),
      "citation is pulled from the requirement's bracket tag when no source_paragraphs")
check(c["consequences"] is True,
      "the Arnesh Kumar consequences flag fires when the notice check is actionable")
check(any("24 hours" in t for t in c["to_verify"]),
      "a Cannot Determine check lands in 'to_verify', not 'grounds'")

# ---- source_paragraphs citation beats the tag ----
c2 = assemble_draft_content(_fa([{
    "requirement": "Written grounds of arrest [Vihaan Kumar]",
    "status": "Non-Compliant",
    "explanation": "x",
    "source_paragraphs": [{"case_name": "Vihaan Kumar v. State of Punjab", "citation": "2025 INSC 162"}],
}]))
check(c2["grounds"][0]["citation"] == "Vihaan Kumar v. State of Punjab, 2025 INSC 162",
      "a real source_paragraphs citation is preferred over the requirement tag")

# ---- clean analysis ----
c_clean = assemble_draft_content(_fa([_COMPLIANT_MEMO]))
check(c_clean["grounds"] == [] and c_clean["no_defect"] is True,
      "an all-Compliant analysis yields no grounds and no_defect=True")
u_clean = render_draft(c_clean, "understanding")
check("No procedural defect was identified" in u_clean and len(u_clean.strip()) > 0,
      "the 'understanding' draft still renders (non-empty) when there is nothing to raise")

# ---- unknown facts render as placeholders, never None/'unclear' ----
c_sparse = assemble_draft_content(_fa([_NC_NOTICE], fields={"sections_cited": []}))
txt_sparse = render_draft(c_sparse, "understanding")
check("[ ___ ]" in txt_sparse and "None" not in txt_sparse,
      "missing identifying facts render as [ ___ ], never as None")
check("[ date and time of arrest ]" in txt_sparse,
      "a missing arrest datetime renders as a bracketed blank, not 'unclear'")

# ---- hedging honesty: never asserts illegality ----
_ILLEGALITY_CLAIM = {
    "Non-Compliant": {
        "requirement": "S.35(3) BNSS notice before arrest [Arnesh Kumar (2014)]",
        "status": "Non-Compliant",
        "explanation": "No notice was issued. The arrest is illegal and the detention is without jurisdiction.",
    }
}["Non-Compliant"]

for target in ("understanding", "magistrate", "sp"):
    d = draft_for(_fa([_MBNC_GROUNDS]), target)
    low = d.lower()
    check(not any(p in low for p in ("was illegal", "is illegal", "arrest was unlawful",
                                     "arrest may be illegal", "arrest is illegal", "void", "vitiated")),
          f"[{target}] a May-be-Non-Compliant finding never becomes an assertion of illegality")
    check("appears not to have been complied with" in low or "does not appear to have been complied with" in low,
          f"[{target}] the May-be finding is phrased as a conspicuous silence")

    d2 = draft_for(_fa([_ILLEGALITY_CLAIM]), target).lower()
    check("illegal" not in d2 and "without jurisdiction" not in d2,
          f"[{target}] a conclusion sentence in the upstream finding ('the arrest is illegal') is dropped from the ground")

# ---- default-bail date surfaces in key_dates ----
c_bail = assemble_draft_content(_fa([_NC_NOTICE, _DEFAULT_BAIL_EXPIRED]))
check(any("20-08-2026" in d for d in c_bail["key_dates"]),
      "the computed default-bail date lands in key_dates verbatim")
mag = render_draft(c_bail, "magistrate")
check("POSITION ON DEFAULT BAIL" in mag and "20-08-2026" in mag,
      "the Magistrate draft carries the default-bail position with its date")

# ---- targets gate correctly ----
check(available_targets(_fa([_COMPLIANT_MEMO])) == ["understanding"],
      "only 'understanding' is offered when there is nothing actionable")
check(set(available_targets(_fa([_NC_NOTICE]))) == {"understanding", "magistrate", "sp"},
      "all three targets are offered once there is a ground")

# ---- envelopes differ by target ----
mag = draft_for(_fa([_NC_NOTICE]), "magistrate")
sp = draft_for(_fa([_NC_NOTICE]), "sp")
und = draft_for(_fa([_NC_NOTICE]), "understanding")
check("MOST RESPECTFULLY SHOWETH" in mag and "PRAYER" in mag and "VERIFICATION" in mag,
      "the Magistrate draft is a representation (showeth / prayer / verification)")
check("Superintendent of Police" in sp and "Yours faithfully," in sp,
      "the SP draft is a letter addressed to the Superintendent of Police")
check("PRAYER" not in und and "To,\nThe Superintendent" not in und and "MOST RESPECTFULLY" not in und,
      "the 'understanding' draft has no addressee and no prayer")
check(mag.count("Arnesh Kumar") >= 1 and "CONSEQUENCES OF NON-COMPLIANCE" in mag,
      "the Arnesh Kumar consequences block appears in the Magistrate draft when the notice check failed")

# ---- unknown target ----
try:
    render_draft(c, "collector")
    check(False, "an unknown target should raise ValueError")
except ValueError:
    check(True, "an unknown target raises ValueError")

# ---- a high-severity fact pattern with no confirmed offence must not assert wrongdoing ----
# (mirrors the interview flow returning only a redirect / no real grounds)
c_none = assemble_draft_content(_fa([]))
d_none = render_draft(c_none, "understanding")
check(c_none["grounds"] == [] and "may not comply" not in d_none.lower(),
      "no compliance checks at all -> no grounds section, no implied wrongdoing")

# =====================================================================
# FREEZE DOMAIN
# =====================================================================

_FZ_SCOPE_NC = {
    "requirement": "Blanket freeze under 106/107 BNSS restricted to disputed amount [Neelkanth Pharma Logistics (2025) / Malabar Gold (2026)]",
    "status": "Non-Compliant",
    "explanation": "Entire account frozen despite a specific disputed amount (Rs. 40000) being identifiable.",
}
_FZ_AUTH_MBNC = {
    "requirement": "Attachment/freeze authorized via Section 107 BNSS court order [Malabar Gold (2026) / Tapas D. Neogy (1999)]",
    "status": "May be Non-Compliant",
    "explanation": "No legal section was cited to justify this freeze at all. A freeze effected without "
                   "invoking this process, on bare police request alone, may be illegal -- see Malabar Gold (2026).",
}
_FZ_INTIMATION_CD = {
    "requirement": "Account holder intimated of freeze after the fact [Malabar Gold (2026)]",
    "status": "Cannot Determine",
    "explanation": "Account holder intimation status unclear.",
}
_FZ_CLEAN = {
    "requirement": "Seizure/freeze intimated forthwith to Magistrate [S.106 BNSS]",
    "status": "Compliant", "explanation": "Intimation to jurisdictional Magistrate is recorded.",
}


def _fz(checks, fields=None):
    return {"extracted_fields": fields if fields is not None else {
        "scope": "entire account", "specific_amount_stated": "40000",
        "account_holder_intimated": False, "court_or_magistrate_mentioned": False,
    }, "compliance": {"compliance_checks": checks}}


check(detect_draft_domain(_fz([_FZ_SCOPE_NC])) == "freeze",
      "a freeze requirement string is detected as the freeze domain")
check(detect_draft_domain(_fz([_FZ_SCOPE_NC, _FZ_AUTH_MBNC])) != "arrest",
      "freeze checks never misdetect as arrest")

fc = assemble_freeze_content(_fz([_FZ_SCOPE_NC, _FZ_AUTH_MBNC, _FZ_INTIMATION_CD]))
check(fc["domain"] == "freeze", "assemble_freeze_content tags domain='freeze'")
check([g for g in fc["grounds"] if "Blanket freeze" in g["heading"]]
      and fc["grounds"][0]["hedged"] is False,
      "the Non-Compliant scope check is the first (worst-first) freeze ground")
check(any("intimated" in t.lower() for t in fc["to_verify"]),
      "a Cannot Determine freeze check lands in to_verify")
check(fc["key_dates"] == [], "freeze content has no key_dates")

# the freeze auth explanation's 'may be illegal' conclusion clause is trimmed
fg = next(g for g in fc["grounds"] if "Section 107" in g["heading"])
check("may be illegal" not in fg["finding"].lower() and "no legal section was cited" in fg["finding"].lower(),
      "the 'may be illegal' conclusion sentence is dropped from a freeze ground, the fact kept")

check(available_targets(_fz([_FZ_CLEAN])) == ["freeze_understanding"],
      "a clean freeze analysis offers only freeze_understanding")
check(set(available_targets(_fz([_FZ_SCOPE_NC]))) == {"freeze_understanding", "freeze_magistrate", "freeze_sp"},
      "a freeze ground unlocks freeze_magistrate + freeze_sp")

fz_u = draft_for(_fz([_FZ_SCOPE_NC]), "freeze_understanding")
fz_m = draft_for(_fz([_FZ_SCOPE_NC]), "freeze_magistrate")
fz_s = draft_for(_fz([_FZ_SCOPE_NC]), "freeze_sp")
check("PRAYER" not in fz_u and "MOST RESPECTFULLY" not in fz_u,
      "freeze_understanding has no prayer / showeth")
check("DE-FREEZING" in fz_m and "MOST RESPECTFULLY SHOWETH" in fz_m and "VERIFICATION" in fz_m,
      "freeze_magistrate is an application to release the account (showeth / prayer / verification)")
check("Superintendent of Police" in fz_s and "Section 107 BNSS" in fz_s and "Yours faithfully," in fz_s,
      "freeze_sp is a letter to the SP asking for the authorising order")
for t in (fz_u, fz_m, fz_s):
    low = t.lower()
    check("is illegal" not in low and "was illegal" not in low and "unauthorised and legally vulnerable" not in low,
          "no freeze draft asserts the freeze is illegal")

# =====================================================================
# CHEQUE-BOUNCE DOMAIN
# =====================================================================

_CQ_AMOUNT_NC = {
    "requirement": "Demand specifically states the correct cheque amount [Suman Sethi (2000) via Kaveri Plastics (2025)]",
    "status": "Non-Compliant",
    "explanation": "Demand (Rs.300,000) does not match cheque face value (Rs.250,000). Per Kaveri Plastics (2025), "
                   "a notice demanding an amount that does not match the actual cheque can be fatal to the complaint.",
}
_CQ_WINDOW_NC = {
    "requirement": "At least 15 days granted to pay [S.138(c)]",
    "status": "Non-Compliant", "explanation": "Notice grants 10 days (statutory minimum: 15).",
}
_CQ_JURIS_NC = {
    "requirement": "Complaint filed where cheque was presented for collection [Prakash Chimanlal Sheth (2025) / S.142(2) NI Act]",
    "status": "Non-Compliant",
    "explanation": "The complaint is recorded as filed at 'Nagpur', but the cheque was presented for collection at 'Pune'.",
}
_CQ_30DAY_CLEAN = {
    "requirement": "Notice sent within 30 days of return memo [S.138(b)]",
    "status": "Compliant", "explanation": "Gap is 16 calendar days (statutory limit: 30).",
}


def _cq(checks, fields=None):
    return {"extracted_fields": fields if fields is not None else {
        "cheque_face_value": 250000, "demand_principal_amount": 300000,
        "notice_date": "05-08-2026", "payment_window_days_granted": 10,
        "cheque_presentation_bank_location": "Pune", "complaint_filed_location": "Nagpur",
    }, "compliance": {"compliance_checks": checks}}


check(detect_draft_domain(_cq([_CQ_AMOUNT_NC])) == "cheque",
      "a Section 138 requirement string is detected as the cheque domain")

cc = assemble_cheque_content(_cq([_CQ_AMOUNT_NC, _CQ_WINDOW_NC, _CQ_JURIS_NC]))
check(cc["domain"] == "cheque", "assemble_cheque_content tags domain='cheque'")
check(len(cc["grounds"]) == 3 and all(g["citation"] for g in cc["grounds"]),
      "every cheque ground carries a citation")
check(any("Rs. 250000" in f for f in cc["facts"]) and any("10 days to pay" in f for f in cc["facts"]),
      "cheque facts recite the cheque amount and the payment window from the fields")

check(available_targets(_cq([_CQ_30DAY_CLEAN])) == ["cheque_understanding"],
      "a clean cheque analysis offers only cheque_understanding")
check(available_targets(_cq([_CQ_AMOUNT_NC])) == ["cheque_understanding", "cheque_reply"],
      "an amount defect unlocks cheque_reply but NOT cheque_magistrate (no jurisdiction ground)")
check("cheque_magistrate" in available_targets(_cq([_CQ_JURIS_NC])),
      "a jurisdiction defect additionally unlocks cheque_magistrate")

cq_u = draft_for(_cq([_CQ_AMOUNT_NC]), "cheque_understanding")
cq_r = draft_for(_cq([_CQ_AMOUNT_NC]), "cheque_reply")
cq_m = draft_for(_cq([_CQ_JURIS_NC]), "cheque_magistrate")
check("Reply to the statutory notice under Section 138" in cq_r and "without prejudice" in cq_r.lower()
      and "not admitted" in cq_r.lower(),
      "cheque_reply is a without-prejudice reply that does not admit liability")
check("registered post" in cq_r.lower(),
      "cheque_reply reminds the sender to send it with proof of delivery")
check("TERRITORIAL JURISDICTION" in cq_m and "return the complaint" in cq_m,
      "cheque_magistrate is a jurisdiction application asking for the complaint to be returned")
check(cq_m.index("Complaint filed where cheque was presented") < cq_m.index("Demand specifically states")
      if "Demand specifically states" in cq_m else True,
      "cheque_magistrate leads with the jurisdiction ground")
check("PRAYER" not in cq_u and "Yours faithfully" not in cq_u,
      "cheque_understanding has no prayer / sign-off")

# arrest analysis is unaffected by the new domains
check(detect_draft_domain(_fa([_NC_NOTICE])) == "arrest",
      "an arrest requirement string still detects as arrest after the freeze/cheque additions")

# =====================================================================
# STATUTE CONCORDANCE WIRED INTO THE TEMPLATES
# =====================================================================

_OLD_CODE_GROUND = {
    "requirement": "Woman not arrested between sunset and sunrise [S.46(4) CrPC / Sheela Barse (1983)]",
    "status": "Non-Compliant",
    "explanation": "Arrest of a woman recorded at 22:10; no exceptional-circumstances authorisation on record.",
}
_REPEALED_GROUND = {
    "requirement": "Written grounds of arrest furnished to arrestee [Vihaan Kumar (2025)]",
    "status": "May be Non-Compliant",
    "explanation": "The FIR is recorded under Section 124A of the Indian Penal Code; the memo is "
                   "silent on separate written grounds.",
}

d_oldcode = draft_for(_fa([_OLD_CODE_GROUND]), "sp")
check("NOTE ON SECTION NUMBERS" in d_oldcode,
      "a draft whose grounds cite an old CrPC/IPC number gets a NOTE ON SECTION NUMBERS block")
check("CrPC 46(4) now corresponds to BNSS 43(5)" in d_oldcode,
      "the note gives the checked modern equivalent from statute_concordance")

d_clean_note = draft_for(_fa([_NC_NOTICE]), "sp")
check("NOTE ON SECTION NUMBERS" not in d_clean_note,
      "a draft that cites only current-code / case-name references gets NO section-number note")

d_repealed = draft_for(_fa([_REPEALED_GROUND]), "understanding")
check("NOTE ON SECTION NUMBERS" in d_repealed
      and "no corresponding provision in the recodified law" in d_repealed,
      "a repealed-without-successor provision (IPC 124A) is flagged, not left to stand as current law")

# the note rides along for the new domains too (cheque cites NI Act sections,
# which are NOT old-code -> no note; a freeze citing an old CrPC number -> note)
_FZ_OLD = {
    "requirement": "Attachment/freeze authorized via Section 107 BNSS court order [Tapas D. Neogy (1999)]",
    "status": "May be Non-Compliant",
    "explanation": "The freeze rests on a bare request; the Section 102 of the Code of Criminal "
                   "Procedure investigative nexus is not shown on record.",
}
d_fz_old = draft_for(_fz([_FZ_OLD]), "freeze_sp")
check("NOTE ON SECTION NUMBERS" in d_fz_old and "CrPC 102 now corresponds to BNSS 106" in d_fz_old,
      "a freeze draft citing an old CrPC number also gets the section-number note")
check("NOTE ON SECTION NUMBERS" not in draft_for(_cq([_CQ_AMOUNT_NC]), "cheque_reply"),
      "a cheque reply citing only NI Act sections (not recodified) gets no section-number note")

# ---- PDF smoke (one cheap call, no API) ----
import os
p = generate_draft_pdf(draft_for(_fa([_NC_NOTICE]), "magistrate"), "magistrate", "scratch_test_draft.pdf")
check(os.path.exists(p) and os.path.getsize(p) > 1500, "generate_draft_pdf writes a non-trivial PDF")
os.remove(p)
p2 = generate_draft_pdf(draft_for(_fz([_FZ_SCOPE_NC]), "freeze_magistrate"), "freeze_magistrate", "scratch_test_draft_fz.pdf")
check(os.path.exists(p2) and os.path.getsize(p2) > 1500, "generate_draft_pdf writes a non-trivial PDF for a freeze draft")
os.remove(p2)


# ---- authorities + matters_raised + medical prayer (the chat-draft additions) ----

_AUTHS = [
    {"case_name": "D.K. Basu v State of West Bengal", "citation": "(1997) 1 SCC 416",
     "court": "Supreme Court", "para_number": 8,
     "quote": "The arrestee should be subjected to medical examination by a trained doctor every 48 hours.",
     "url": "https://indiankanoon.org/doc/235756/", "verified": True},
    {"case_name": "Mujeeb Rahman v State of Kerala", "citation": "",
     "court": "Kerala High Court", "para_number": 12,
     "quote": "The right to be produced before a Magistrate within twenty-four hours is an absolute safeguard.",
     "url": "https://indiankanoon.org/doc/999/", "verified": False},
    {"case_name": "Nope", "quote": "", "verified": True},  # no quote -> dropped
]
_MATTERS = ["he had bruises on both arms and said he was slapped and kept awake all night"]

dm = draft_for(_fa([_NC_NOTICE]), "magistrate", authorities=_AUTHS, matters_raised=_MATTERS)
check("RELEVANT JUDICIAL AUTHORITY" in dm, "the authority section appears in the magistrate draft")
check('"The arrestee should be subjected to medical examination by a trained doctor every 48 hours."' in dm,
      "the verified authority's paragraph is reproduced verbatim")
check("In D.K. Basu v State of West Bengal (1997) 1 SCC 416 (Supreme Court), at paragraph 8" in dm,
      "verbatim quote carries the full citation and paragraph number")
check("FURTHER JUDGMENTS FROM A LIVE SEARCH - NOT VERIFIED" in dm
      and "Mujeeb Rahman" in dm.split("NOT VERIFIED", 1)[1],
      "an unverified authority is walled off in the 'NOT VERIFIED' block, not the body")
check("https://indiankanoon.org/doc/999/" in dm, "the unverified authority carries its source link")
check("MATTERS STATED BY THE ARRESTED PERSON / FAMILY" in dm
      and "bruises on both arms" in dm and "does not assess or verify" in dm,
      "custodial-assault allegation is set out verbatim and expressly unassessed")
check("medically examined forthwith by a Government medical officer" in dm,
      "the medical-examination prayer clause is added when injuries are alleged")
check("Nope" not in dm, "an authority with no quote is dropped")

# medical prayer also fires when the D.K. Basu medical check itself is Non-Compliant
_MED_NC = {"requirement": "Arrest memo attested by witness, family informed, medical exam [DK Basu (1997)]",
           "status": "Non-Compliant", "explanation": "D.K Basu items missing: medical exam recorded."}
check("medically examined forthwith" in draft_for(_fa([_MED_NC]), "magistrate"),
      "the medical prayer also fires from a failed D.K. Basu medical check (no matters_raised needed)")

# no authorities / no matters -> those sections simply absent, draft still renders
plain = draft_for(_fa([_NC_NOTICE]), "magistrate")
check("RELEVANT JUDICIAL AUTHORITY" not in plain and "MATTERS STATED" not in plain,
      "with nothing passed in, the new sections don't appear and the draft is unchanged")

# an old-code reference inside a quoted authority still triggers the section-number note
d_old_q = draft_for(_fa([_COMPLIANT_MEMO]), "magistrate", authorities=[
    {"case_name": "X v State", "quote": "Section 41 of the Cr.P.C. lists the cases where arrest may be made.",
     "verified": True}])
check("NOTE ON SECTION NUMBERS" in d_old_q and "CrPC 41" in d_old_q,
      "an old CrPC number quoted inside an authority passage is caught by the section-number note")

# SP letter also carries both sections
ds = draft_for(_fa([_NC_NOTICE]), "sp", authorities=_AUTHS, matters_raised=_MATTERS)
check("RELEVANT JUDICIAL AUTHORITY" in ds and "MATTERS STATED BY THE ARRESTED PERSON / FAMILY" in ds,
      "the SP complaint carries the authority and matters sections too")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
