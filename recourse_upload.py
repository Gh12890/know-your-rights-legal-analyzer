"""
recourse_upload.py  (Vibeathon Step 5 add-on, 2026-09-08)

The optional "have the papers?" step.

The scenario answer tells you what the law REQUIRES. This module takes the
actual document -- an arrest memo, an FIR copy, a remand order -- and checks
whether each safeguard was ACTUALLY FOLLOWED, using the same deterministic
compliance engine the wider tool has always used (main.py's check_* functions).

Nothing here is new legal logic. It is a thin adapter:
  1. pull the text out of the uploaded file,
  2. run it through main.run_police_pipeline (subtype routing + extraction +
     the arrest check_* functions),
  3. normalise the result for the Recourse UI, plus the IPC->BNS concordance
     note (which old section numbers the document cites and their current
     equivalents).

Honest by construction: the check_* functions return one of five states --
Compliant / Non-Compliant / May be Non-Compliant / Cannot Determine / Not
Applicable -- and this module passes them through unchanged. It never turns a
"Cannot Determine" into a verdict.
"""

import io
import logging

logger = logging.getLogger("recourse_upload")

_MAX_BYTES = 8 * 1024 * 1024          # 8 MB cap
_MIN_TEXT = 60                        # below this we assume extraction failed


def extract_text(uploaded_file) -> dict:
    """uploaded_file: a Streamlit UploadedFile. Returns
    {'ok': bool, 'text': str, 'error': str}."""
    if uploaded_file is None:
        return {"ok": False, "text": "", "error": "No file."}
    data = uploaded_file.getvalue()
    if len(data) > _MAX_BYTES:
        return {"ok": False, "text": "",
                "error": "That file is larger than 8 MB. Try a smaller PDF."}

    name = (uploaded_file.name or "").lower()
    text = ""
    if name.endswith(".txt"):
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = ""
    elif name.endswith(".pdf"):
        try:
            import fitz  # PyMuPDF, already a dependency
            with fitz.open(stream=io.BytesIO(data), filetype="pdf") as doc:
                text = "\n".join(page.get_text() for page in doc)
        except Exception:
            logger.exception("extract_text: PDF read failed")
            return {"ok": False, "text": "",
                    "error": "Couldn't open that PDF. It may be corrupted or password-protected."}
    else:
        return {"ok": False, "text": "",
                "error": "Please upload a PDF or a plain-text (.txt) file. "
                         "A photo of the document won't work yet -- it needs selectable text."}

    text = _tidy(text)
    if len(text) < _MIN_TEXT:
        return {"ok": False, "text": text,
                "error": "There isn't enough readable text in that file. If it's a scanned "
                         "image, try a PDF where you can select the text, or type the key "
                         "parts into the box above instead."}
    return {"ok": True, "text": text, "error": ""}


def _tidy(raw: str) -> str:
    return "\n".join(ln.strip() for ln in (raw or "").splitlines() if ln.strip())


# status -> (short label for the chip, semantic bucket)
_STATUS_UI = {
    "Compliant":            ("Followed",                 "ok"),
    "Non-Compliant":        ("Not followed",             "bad"),
    "May be Non-Compliant": ("Possibly not followed",    "warn"),
    "Cannot Determine":     ("Can't tell from this document", "unknown"),
    "Not Applicable":       ("Does not apply here",       "na"),
}

# requirement string (from main.py) -> a plain, short heading
_PLAIN_REQUIREMENT = [
    ("notice before arrest",        "A notice to appear was served before arrest (Arnesh Kumar / s.35(3) BNSS)"),
    ("S.35(3) BNSS notice",         "A notice to appear was served before arrest (Arnesh Kumar / s.35(3) BNSS)"),
    ("Threshold basis for arrest",  "There was a lawful basis to arrest without a warrant"),
    ("cognizab",                    "There was a lawful basis to arrest without a warrant"),
    ("grounds of arrest",           "The grounds of arrest were given in writing (Prabir Purkayastha / Vihaan Kumar)"),
    ("written grounds",             "The grounds of arrest were given in writing (Prabir Purkayastha / Vihaan Kumar)"),
    ("arrest memo",                 "The arrest-memo safeguards were followed -- witness, family, medical (D.K. Basu)"),
    ("D.K. Basu",                   "The arrest-memo safeguards were followed -- witness, family, medical (D.K. Basu)"),
    ("Night-arrest",                "The night-arrest protection for a woman was observed (s.43(5) BNSS)"),
    ("night arrest",                "The night-arrest protection for a woman was observed (s.43(5) BNSS)"),
    ("Female officer",              "A woman police officer was involved in arresting a woman"),
    ("female officer",              "A woman police officer was involved in arresting a woman"),
    ("24 hour",                     "The person was produced before a Magistrate within 24 hours (Article 22(2) / s.58 BNSS)"),
    ("24-hour",                     "The person was produced before a Magistrate within 24 hours (Article 22(2) / s.58 BNSS)"),
    ("Default bail",                "The chargesheet deadline for default bail (s.187 BNSS)"),
    ("223",                         "The Section 215 BNSS bar on taking cognizance without the public servant's complaint"),
]


def _plain(req: str) -> str:
    low = (req or "").lower()
    for needle, plain in _PLAIN_REQUIREMENT:
        if needle.lower() in low:
            return plain
    return req or "A procedural safeguard"


def check_arrest_document(text: str) -> dict:
    """Run the uploaded arrest document through the deterministic engine.

    Returns:
      {
        "ok": bool,
        "is_arrest_document": bool,   # False -> we say so, no fake checks
        "subtype": str,
        "checks": [ {plain, status, label, bucket, explanation}, ... ],
        "n_defects": int, "n_unknown": int,
        "overall": str,
        "old_code": [ {old, new, changed}, ... ],   # IPC/CrPC -> BNS/BNSS
        "note": str,
      }
    """
    try:
        from main import run_police_pipeline
    except Exception:
        logger.exception("check_arrest_document: engine import failed")
        return {"ok": False, "is_arrest_document": False, "checks": [],
                "note": "The compliance engine isn't available right now."}

    try:
        pipeline = run_police_pipeline(text)
    except Exception:
        logger.exception("check_arrest_document: run_police_pipeline failed")
        return {"ok": False, "is_arrest_document": False, "checks": [],
                "note": "Couldn't analyse that document -- try again, or type the key parts above."}

    subtype = pipeline.get("police_subtype", "Other")
    raw_checks = (pipeline.get("compliance") or {}).get("compliance_checks", []) or []

    # The affordance is shown on arrest situations and asks for an arrest memo,
    # FIR copy or remand order. Only those police sub-types get a verdict; a
    # freeze notice or a cheque notice lands here by mistake and is turned away
    # honestly rather than checked against the wrong rules.
    _ARREST_LIKE = {"Arrest-related", "FIR / Complaint - No Arrest Yet",
                    "Summons to Vulnerable Person"}
    if subtype not in _ARREST_LIKE or not raw_checks:
        redirect = {
            "Bank/Account Freezing":
                "This looks like a bank-account freeze notice -- a different kind of "
                "matter. Recourse's chat can point you to the right check for that.",
            "Search & Seizure":
                "This looks like a search-and-seizure document. Recourse checks arrest "
                "safeguards here, not search procedure -- take it to a lawyer.",
        }.get(subtype,
              "This doesn't read like an arrest memo, FIR copy or remand order. "
              "Recourse can only check the arrest safeguards against those documents. "
              "The rights above still apply -- take them, and the document, to a lawyer.")
        return {
            "ok": True, "is_arrest_document": False, "subtype": subtype, "checks": [],
            "old_code": _old_code(text), "note": redirect,
        }

    use_plain = subtype == "Arrest-related"
    checks = []
    for c in raw_checks:
        status = c.get("status", "Cannot Determine")
        label, bucket = _STATUS_UI.get(status, ("Unclear", "unknown"))
        req = c.get("requirement", "")
        checks.append({
            "plain": _plain(req) if use_plain else req,
            "status": status,
            "label": label,
            "bucket": bucket,
            "explanation": (c.get("explanation") or "").strip(),
        })

    n_defects = sum(1 for c in checks if c["bucket"] in ("bad", "warn"))
    n_unknown = sum(1 for c in checks if c["bucket"] == "unknown")
    if n_defects:
        overall = (f"{n_defects} safeguard(s) appear not to have been followed. "
                   f"The arrest and continued custody may be open to challenge -- "
                   f"raise this with the Magistrate and a lawyer.")
    elif n_unknown:
        overall = (f"Nothing is clearly wrong on the face of the document, but "
                   f"{n_unknown} safeguard(s) can't be checked from it alone.")
    else:
        overall = "On the face of this document, the safeguards that could be checked were followed."

    return {
        "ok": True, "is_arrest_document": True, "subtype": subtype,
        "checks": checks, "n_defects": n_defects, "n_unknown": n_unknown,
        "overall": overall, "old_code": _old_code(text), "note": "",
    }


def _old_code(text: str) -> list:
    """IPC/CrPC section numbers the document cites, with their current
    BNS/BNSS equivalents. Thin wrapper over the shared concordance primitive."""
    try:
        from statute_concordance import scan_old_refs
        return scan_old_refs(text) or []
    except Exception:
        return []
