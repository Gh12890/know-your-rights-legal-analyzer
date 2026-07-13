import fitz
import os
import json
import typing
from datetime import datetime, timedelta
from dotenv import load_dotenv
from anthropic import Anthropic
from bns_section_data import BNS_SECTION_DATA, get_max_years_from_sections


load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")
client = Anthropic(api_key=api_key)


def get_urgency_level(days_remaining):
    if days_remaining < 0:
        return "DEADLINE PASSED"
    elif days_remaining <= 3:
        return "CRITICAL"
    elif 4 <= days_remaining <= 10:
        return "HIGH RISK"
    elif 11 <= days_remaining <= 30:
        return "FORMAL"
    else:
        return "ROUTINE"


def get_action_plan(urgency_level):
    if urgency_level == "DEADLINE PASSED":
        return {
            "30_min": "Do not ignore this. The stated deadline has already passed.",
            "24_hr": "Consult a lawyer immediately — your options may be narrowing.",
            "3_day": "Prepare for possible legal proceedings; do not assume delay is safe."
        }
    elif urgency_level == "CRITICAL":
        return {
            "30_min": "Save this notice securely. Do not make verbal commitments to the sender.",
            "24_hr": "Gather all related documents and records immediately.",
            "3_day": "Seek professional review before any response — deadline is imminent."
        }
    elif urgency_level == "HIGH RISK":
        return {
            "30_min": "Save this notice and note the deadline clearly.",
            "24_hr": "Locate supporting documents and verify claimed facts.",
            "3_day": "Decide on response path: dispute, comply, or seek clarification."
        }
    elif urgency_level == "FORMAL":
        return {
            "30_min": "Save the notice and go through it.",
            "24_hr": "Find out the legal clauses.",
            "3_day": "Decide to talk to a lawyer."
        }
    else:
        return {
            "30_min": "Check who is the sender.",
            "24_hr": "Decide what are the allegations and violations.",
            "3_day": "Wait for 5 more days"
        }


def build_analysis_summary(days_remaining):
    urgency = get_urgency_level(days_remaining)
    message = get_action_plan(urgency)
    return {
        "urgency_level": urgency,
        "deadline_message": message,
        "days_remaining": days_remaining
    }


def extract_text_from_pdf(filepath):
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def clean_text(raw_text):
    lines = raw_text.split("\n")
    cleaned_lines = []
    for line in lines:
        if line.strip() != "":
            cleaned_lines.append(line.strip())
    return "\n".join(cleaned_lines)


def parse_json_response(response_text):
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


DATE_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y"]


def parse_date(raw: typing.Optional[str]) -> typing.Optional[datetime]:
    if not raw or str(raw).strip().lower() == "null":
        return None
    raw = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _result(requirement: str, status: str, explanation: str) -> dict:
    return {"requirement": requirement, "status": status, "explanation": explanation}


def check_30_day_window(fields: dict) -> dict:
    req = "Notice sent within 30 days of return memo [S.138(b)]"
    memo = parse_date(fields.get("return_memo_date"))
    notice = parse_date(fields.get("notice_date"))
    if memo is None or notice is None:
        return _result(req, "Cannot Determine", "Return-memo date or notice date is missing or unparseable.")
    gap = (notice - memo).days
    if gap < 0:
        return _result(req, "Non-Compliant", f"Notice dated {gap} days before the return memo, which is impossible/invalid.")
    status = "Compliant" if gap <= 30 else "Non-Compliant"
    return _result(req, status, f"Gap is {gap} calendar days (statutory limit: 30).")


def check_amount_match(fields: dict) -> dict:
    req = "Demand equals cheque face value; interest stated separately [Suman Sethi]"
    face = fields.get("cheque_face_value")
    demand = fields.get("demand_principal_amount")
    if face is None or demand is None:
        return _result(req, "Cannot Determine", "Cheque value or demand amount missing.")
    bundled = bool(fields.get("interest_bundled_in_principal_sentence", False))
    if face != demand:
        return _result(req, "Non-Compliant", f"Demand (Rs.{demand:,}) does not match cheque face value (Rs.{face:,}).")
    if bundled:
        return _result(req, "Non-Compliant", "Principal matches, but interest/costs are bundled into the demand sentence.")
    return _result(req, "Compliant", f"Demand matches face value (Rs.{face:,}); interest not improperly bundled.")


def check_enforceable_debt(fields: dict) -> dict:
    req = "Cheque issued for legally enforceable debt [Laxmi Dyechem]"
    purpose = str(fields.get("cheque_purpose", "unclear")).lower()
    if purpose == "debt":
        return _result(req, "Compliant", "Notice frames the cheque as issued for a debt/liability.")
    if purpose in ("security", "advance"):
        return _result(req, "Non-Compliant", f"Notice frames the cheque as '{purpose}', not an enforceable debt.")
    return _result(req, "Cannot Determine", "Purpose of the cheque is unclear from the text.")


def check_15_day_payment_window(fields: dict) -> dict:
    req = "At least 15 days granted to pay [S.138(c)]"
    window = fields.get("payment_window_days_granted")
    if window is None:
        return _result(req, "Cannot Determine", "Stated payment window not found in notice.")
    status = "Compliant" if window >= 15 else "Non-Compliant"
    return _result(req, status, f"Notice grants {window} days (statutory minimum: 15).")


def run_compliance_checks(fields: dict) -> dict:
    checks = [
        check_30_day_window(fields),
        check_amount_match(fields),
        check_enforceable_debt(fields),
        check_15_day_payment_window(fields),
    ]
    non_compliant = [c for c in checks if c["status"] == "Non-Compliant"]
    undetermined = [c for c in checks if c["status"] == "Cannot Determine"]

    if non_compliant:
        overall = f"{len(non_compliant)} procedural defect(s) found. Notice may be legally vulnerable."
    elif undetermined:
        overall = f"No defects found, but {len(undetermined)} check(s) could not be verified from the document. Needs manual review."
    else:
        overall = "All four checks pass. No procedural defects detected in extracted fields."

    return {"compliance_checks": checks, "overall_assessment": overall}


document_checklists = {
    "Banking & Cheque Bounce": [
        "Original dishonoured cheque (if in your possession)",
        "Bank return memo / cheque bounce memo",
        "Bank statement showing the transaction",
        "Any written agreement or invoice related to the underlying debt",
        "Proof of postal delivery (RPAD receipt) if you are the sender"
    ],
    "Police & Criminal Process": [
        "Copy of the FIR (if registered)",
        "Any written notice received from police (Section 35/41A, Section 94/91)",
        "Identity proof",
        "Names and badge numbers of investigating officers, if known",
        "Any prior correspondence with the police station"
    ],
    "Tenancy & Property": [
        "Rental agreement or lease deed",
        "Rent payment receipts or bank transfer records",
        "Property registration documents, if applicable",
        "Any prior written communication with landlord/tenant"
    ],
    "Individual Tax Notices": [
        "Copy of the relevant ITR/GST filing referenced in the notice",
        "Form 26AS / AIS statement (for income tax notices)",
        "Bank statements for the relevant financial year",
        "Any prior correspondence with the tax department"
    ],
    "Government / Revenue Orders": [
        "Copy of the original order or circular",
        "Land records / mutation documents, if applicable",
        "Any prior applications or representations filed",
        "Identity and address proof"
    ]
}


def get_document_checklist(document_type):
    return document_checklists.get(document_type, ["No checklist available for this category yet."])


def calculate_days_remaining(deadline_fields, notice_date_str=None):
    today = datetime.now()

    explicit_date = parse_date(deadline_fields.get("deadline_date_if_explicit"))
    if explicit_date:
        return (explicit_date - today).days

    days_stated = deadline_fields.get("deadline_days_stated")
    parsed_notice_date = parse_date(notice_date_str)
    if days_stated is not None and parsed_notice_date:
        deadline_date = parsed_notice_date + timedelta(days=days_stated)
        return (deadline_date - today).days

    return None


EXTRACTION_PROMPT = """You are extracting factual fields from an Indian Section 138
cheque bounce notice. Do NOT judge compliance. Only report what the document states.
If a field is not present, use null.

Return ONLY valid JSON in this exact format, no other text:
{{"return_memo_date": "DD-MM-YYYY or null",
  "notice_date": "DD-MM-YYYY or null",
  "cheque_face_value": number or null,
  "demand_principal_amount": number or null,
  "payment_window_days_granted": number or null,
  "interest_bundled_in_principal_sentence": true or false,
  "cheque_purpose": "debt" or "security" or "advance" or "unclear"
}}

Document text:
{document_text}"""

# Police & CRIMINAL PROCESS- sub-type routing and checks#

POLICE_SUBTYPE_PROMPT= """Classify this Indian police/criminal process document into exactly one type.
- "Arrest-related"- arrest memo, 41A/35 BNSS notice to appear, grounds of arrest, remand related document.
- "Bank/Account Freezing"- freeze/attachment order or intimation under 106/107 BNSS or old 102 CrPc
- "Search & Seizure "- NDPS search memo, seizure memo of goods/devices/property, panchnama 
- "FIR Registration Dispute"- written rejection of FIR, delay-in-registration complaint, closure intimation, NC entry only 
- "Summons to Vulnerable Person"- 179 BNSS/old 160 CrPC summons to a woman, minor or elderly person
- "Other"- police document that fits none of the above 

Respond with only valid JSON:{{"police_subtype": "one of the above"}}

Document text:
{document_text}"""

ARREST_EXTRACTION_PROMPT = """Extract only what the arrest-related document explicitly states. Do NOT judge legality. If a field is not present, use null. Do not infer.

IMPORTANT DISTINCTION for grounds_of_arrest_in_writing_furnished_to_arrestee: this field means a SEPARATE written document was handed to the arrestee explaining the specific grounds for HIS arrest. It is NOT the same as an internal police checklist of justifications (e.g., checkboxes like "for proper investigation" or "to ensure presence in court") recorded in the memo for the police's own record. If the memo only shows internal justification checkboxes with no indication that a distinct grounds document was furnished to the arrestee, mark this field false, not true.

IMPORTANT INSTRUCTION for 41A_or_35_BNSS_notice_issued_before_arrest: if the document otherwise documents procedural steps carefully (e.g., witness attestation, family notification, medical examination are all explicitly recorded) but says NOTHING about a prior notice to appear being issued before the arrest, mark this field false, not "unclear". A memo that carefully documents several safeguards but is silent on this one specific step is evidence the step was likely skipped, not evidence that its status is unknown. Only use "unclear" if the document is generally sparse or unclear on procedural matters overall, not merely silent on this one field while being detailed elsewhere.

Sections_cited must contain ONLY the bare section number/sub-section (e.g. '305', '318(4)'), never including 'BNS', 'IPC', 'CrPC', or similar labels."
Return ONLY valid JSON in this format, no other text:
{{
  "document_date": "DD-MM-YYYY or null",
  "offence_date": "DD-MM-YYYY or null",
  "sections_cited": ["list of sections mentioned"],
  "punishment_years_upper_bound": number or null,
  "arrestee_gender": "male" or "female" or "not stated",
  "arrestee_age": number or null,
  "arrest_datetime_full": "DD-MM-YYYY HH:MM or null",
  "production_datetime_full": "DD-MM-YYYY HH:MM or null",
  "grounds_of_arrest_in_writing_furnished_to_arrestee": true or false or "unclear",
  "41A_or_35_BNSS_notice_issued_before_arrest": true or false or "unclear",
  "witness_attested_memo": true or false or "unclear",
  "family_or_friend_informed": true or false or "unclear",
  "medical_exam_at_arrest_recorded": true or false or "unclear",
  "female_officer_present_for_female_arrestee": true or false or "unclear" or "not applicable",
  "chargesheet_filed_date": "DD-MM-YYYY or null"
}}

Document text:
{document_text}"""

def build_grounded_section_context(sections_cited):
    """Look up each cited section in the verified dictionary and produce a short, factual context string the model can reply on instead of guessing."""
    if not sections_cited:
        return "No sections were cited in the documen."
    lines=[]
    for sec in sections_cited:
        clean = re.sub(r'\s*(BNS|IPC|BNSS|CrPC)\s*$','', str(sec).strip(), flags=re.IGNORECASE).strip()
        data = BNS_SECTION_DATA.get(clean)
        if data:
            lines.append(f"-Section {clean}: {data['offence']} (max punishment: {'Life/Death' if data['life_or_death'] else str(data['max_years']) + ' years'})")
        else:
            lines.append(f"- Section {clean}: not in our verified reference table — do not assume or guess what this section covers.")
    return "\n".join(lines)  





import re

def get_max_years_from_sections(sections_cited):
    if not sections_cited:
        return None
    candidates = []
    for sec in sections_cited:
        clean = re.sub(r'\s*(BNS|IPC|BNSS|CrPC)\s*$', '', str(sec).strip(), flags=re.IGNORECASE).strip()
        data = BNS_SECTION_DATA.get(clean)
        if data is None:
            continue
        if data["life_or_death"]:
            return "LIFE_OR_DEATH"
        if data["max_years"] is not None:
            candidates.append(data["max_years"])
    return max(candidates) if candidates else None

FREEZE_EXTRACTION_PROMPT =""" Extract only what the bank/account freezing document explicitly states. DO NOT judge legality. Use null if not present.
 "If the document does not mention any BNS/BNSS/CrPC section number anywhere in connection with the freeze, you MUST answer 'none cited' — do not answer 'unclear' in this case. 'unclear' is only for when a section is mentioned but its exact identity is ambiguous."
 Return ONLY valid JSON:
 {{
     "freeze_date": "DD-MM-YYYY or null",
     "section_invoked": "106 BNSS" or "107 BNSS" or "102 CrPC" or "other" or "unclear",
     "scope" : "entire account" or "specific disputed amount" or "unclear",
     "specific_amount_stated": number or null,
     "account_holder_intimated": true or false or "unclear",
     "magistrate_intimation_recorded": true or false or "unclear",
     "magistrate_intimation_date": "DD-MM-YYYY or null",
     "court_order_referenced_for_107": true or false or "unclear" or "not applicable"
 }}
 Document text:
 {document_text}"""
 
SEARCH_EXTRACTION_PROMPT =""" Extract only what the search & seizure document expliclity states. DO NOT judge legality. Use null if not present.

Return ONLY valid JSON:
{{
    "search_target": "person" or "bag or vehicle or premises" or "unclear",
    "section_50_ndps_offer_recorded": true or false or "unclear" or "not applicable",
    "option_offered_to_accused":"magistrate or gazetted officer" or "police officer only" or "none offered" or "unclear" or "not applicable",
    "language_of_notice_understood_by_accused_confirmed": true or false or "unclear",
    "independent_witnesses_present": true or false or "unclear",
    "seizure_memo_signed_by_accused": true or false or "unclear"
}}
Document text:
{document_text} """

FIR_DISPUTE_EXTRACTION_PROMPT = """ Extract only what the document about FIR registration explicitly states. Use null if not present.
 
Return ONLY valid JSON:

{{
"complaint_date": "DD-MM-YYYY or null",
"offence_alleged_is_cognizable": true or false or "unclear",
"police_action": "refused to regsiter" or "delayed regsitration" or "NC entry only" or "closure intimation" or "unclear",
"delay_days": number or null, 
"written_response_given": true or false or "unclear",
"offence_category_falling_in_lalita_kumari_inquiry_exceptions": "matrimonial" or "commercial" or "medical negligence" or "corruption" or "none" or "unclear"
}}

Document text:
{document_text}"""

VULNERABLE_EXTRACTION_PROMPT ="""Extract only waht the summons to a vulnerable person explicitly states. Use null if not present.
Return ONLY valid JSON:

{{
    "summoned_person_gender": "male" or "female" or "not stated",
    "summoned_person_age": number or null,
    "summons_location": "police station" or "residence" or "unclear",
    "summons_datetime": "DD-MM-YYYY HH:MM or null,
    "female_officer_involved": true or false or "unclear" or "not applicable",
    "guardian_notified_for_minor": true or false or "unclear" or "not applicable"
    
}}

Document text:
{document_text}"""


#------ Deterministic Python compliance checks----#

def parse_datetime_full(raw):
    if not raw or str(raw).strip().lower() == "null":
        return None
    from datetime import datetime as _dt
    for fmt in ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return _dt.strptime(str(raw).strip(),fmt)
        except ValueError:
            continue
    return None 

def check_arnesh_kumar_notice(f):
    req = "41A CrPC / Section 35 BNSS notice before arrest [Arnesh Kumar (2014) / Satender Kumar Antil (2026)]"
    
    looked_up = get_max_years_from_sections(f.get("sections_cited", []))
    
    if looked_up == "LIFE_OR_DEATH":
        return _result(req, "Not Applicable", "Offence carries life/death — outside Arnesh Kumar's under-7-years scope.")
    
    upper = looked_up if looked_up is not None else f.get("punishment_years_upper_bound")
    source = "looked up from cited section" if looked_up is not None else "as stated in document"
    
    if upper is None:
        return _result(req, "Cannot Determine", "Section not recognized in lookup table and punishment range not stated in document.")
    
    if upper > 7:
        return _result(req, "Not Applicable", f"Offence carries up to {upper} years ({source}) — outside Arnesh Kumar's under-7-years scope.")
    
    notice = f.get("41A_or_35_BNSS_notice_issued_before_arrest")
    if notice is True:
        return _result(req, "Compliant", f"Prior 41A/35 BNSS notice recorded before arrest for an offence punishable up to {upper} years ({source}).")
    if notice is False:
        return _result(req, "May be Non-Compliant", f"Offence punishable up to {upper} years ({source}). No mention of the mandatory 41A/35 BNSS notice in the document. The arrest may be illegal if this mandatory notice was not actually served. Police documents often omit this step without stating so directly.")
    return _result(req, "Cannot Determine", "Prior notice status is unclear from the document.")


def check_written_grounds(f):
    req= "Written grounds of arrest furnished to arrestee.[Prabir Purkayastha(2024)]"
    v= f.get("grounds_of_arrest_in_writing_furnished_to_arrestee")
    if v is True :
        return _result(req, "Compliant", "Written grounds of arrest were furnished to the arrestee.")
    if v is False:
        return _result(req, "May be Non-Compliant", "The document does not mention of written grounds of arrest recorded being furnished. Supreme Court holds arrest vitiated without this.")
    return _result(req, "Cannot Determine", "Whether written grounds were furnished cannot be determined from the document.")

def check_dk_basu_memo(f):
    req = "Arrest memo attested by witness, family informed , medical exam [D.K. Basu (1997)] "
    checks = [
        ("witness attested", f.get("witness_attested_memo")),
        ("family informed", f.get("family_or_friend_informed")),
        ("medical exam recorded", f.get("medical_exam_at_arrest_recorded")),
    ]
    
    missing = [ name for name ,v in checks if v is False]
    unclear = [name for name, v in checks if v == "unclear" or  v is None]
    if missing:
        return _result(req, "Non-Compliant", f"D.K Basu items misisng: { ','.join(missing)}. ")
    if unclear:
        return _result(req, "Cannot Determine", f" D.K Basu items unclear from document: {'.'.join(unclear)}.")
    return _result(req, "Compliant", "Witness attestation, family notification, and medical exam all recorded.")

def check_night_arrest_of_woman(f):
    req = "Woman not arrested between sunset and sunrise [S.46(4) CrPC/ Sheela Barse]"
    gender = f.get("arrestee_gender")
    if gender != "female":
        return _result(req, "Not Applicable", "Arrestee is not female.")
    dt = parse_datetime_full(f.get("arrest_datetime_full"))
    if dt is None:
        return _result(req, "Cannot Determine", "Arrest time not stated in full; night-arrest rule cannot be checked.")
    hour = dt.hour 
    if 6 <= hour < 18:
        return _result(req, "Compliant", f"Arrest at {dt.strftime('%H:%M')} is within daylight hours.")
    return _result(req, "Non-Compliant", f"Female arrestee taken at { dt.strftime('%H:%M')} (outside 06:00-18:00). Prior magistrate permission mandatory.")

def check_female_officer_involvement(f):
    req= "Female officer involved in custody/interrogation of female arrestee[Sheela Barse (1983)]"
    if f.get("arrestee_gender") != "female":
        return _result(req, "Not Applicable", "Arrestee is not female.")
    v= f.get("female_officer_present_for_female_arrestee")
    if v is True:
        return _result(req, "Compliant", "Female officer involvement recorded for this female arrestee.")
    if v is False:
        return _result(req, "May be Non-Compliant", "No female officer involvment recorded. Sheela Barse judgement requires a female officer for custody,interrogation , and search of a female arrestee. Silence on this point in an otherwise detailed memo suggests it may not have been observed.")
    return _result(req, "Cannot Determine", "Female Officer involvement status is unclear from the document.")



def check_24_hour_production(f):
    req = "Produced before magistrate within 2 hours [Art. 22(2)/S. 58 BNSS]"
    a = parse_datetime_full(f.get("arrest_datetime_full"))
    p= parse_datetime_full(f.get("production_datetime_full"))
    if a is None:
        return _result(req, "Cannot Determine", "Arrest time not fully stated. ")
    if p is None:
        return _result(req, "Cannot Determine", "Production-before-magistrate time not stated in this document.")
    gap_hrs = (p-a).total_seconds()/3600.0
    if gap_hrs <= 24:
        return _result(req, "Compliant", f"Produced {gap_hrs:.1f} hours after arrest — within 24 hours.")
    return _result(req, "Non-Compliant", f"Produced {gap_hrs:.1f} hours after arrest — exceeds constitutional 24-hour limit.")

def check_default_bail(f, user_chargesheet_date=None):
    req = "Default bail on chargesheet delay [S.187 BNSS / S.167(2) CrPC]"

    a = parse_datetime_full(f.get("arrest_datetime_full"))
    if a is None:
        return _result(req, "Cannot Determine", "Arrest date/time not stated; default-bail clock cannot be computed.")

    looked_up = get_max_years_from_sections(f.get("sections_cited", []))
    if looked_up == "LIFE_OR_DEATH":
        threshold_days = 90
        upper_desc = "life/death"
    else:
        upper = looked_up if looked_up is not None else f.get("punishment_years_upper_bound")
        if upper is None:
            return _result(req, "Cannot Determine", "Section not recognized in lookup table and punishment range not stated; 60-day vs 90-day threshold unknown.")
        threshold_days = 90 if upper >= 10 else 60
        upper_desc = f"{upper} years"

    p = parse_datetime_full(f.get("production_datetime_full"))
    if p is not None:
        remand_start = p
        remand_basis = "actual production-before-magistrate date stated in document"
    else:
        remand_start = a + timedelta(days=1)
        remand_basis = "ASSUMED as one day after arrest (production date not stated in document) — verify against the actual remand order"

    deadline_date = remand_start + timedelta(days=threshold_days)
    today = datetime.now()

    # user-supplied answer takes priority over document extraction, since the
    # document almost never contains this — it's created before a chargesheet exists
    cs_str = user_chargesheet_date if user_chargesheet_date is not None else f.get("chargesheet_filed_date")
    cs_dt = parse_date(cs_str)

    if cs_dt is not None:
        if cs_dt <= deadline_date:
            return _result(req, "Compliant", f"Chargesheet filed {cs_dt.strftime('%d-%m-%Y')}, within the {threshold_days}-day window (offence up to {upper_desc}; {remand_basis}).")
        return _result(req, "Non-Compliant", f"Chargesheet filed {cs_dt.strftime('%d-%m-%Y')}, AFTER the {threshold_days}-day window that expired {deadline_date.strftime('%d-%m-%Y')}. Default bail rights had accrued (offence up to {upper_desc}; {remand_basis}).")

    days_remaining = (deadline_date - today).days
    if days_remaining < 0:
        return _result(req, "May be Non-Compliant", f"No chargesheet filed as of today. Default bail eligibility date was {deadline_date.strftime('%d-%m-%Y')} ({-days_remaining} days ago) — {threshold_days}-day window (offence up to {upper_desc}; {remand_basis}). Default bail is now a matter of right.")
    return _result(req, "Compliant", f"No chargesheet filed yet. Default bail becomes available on {deadline_date.strftime('%d-%m-%Y')} if chargesheet is not filed before then — {days_remaining} days remain ({threshold_days}-day window; offence up to {upper_desc}; {remand_basis}).")



def run_arrest_compliance_checks(fields, user_chargesheet_date=None):
    checks = [
        check_arnesh_kumar_notice(fields),
        check_written_grounds(fields),
        check_dk_basu_memo(fields),
        check_night_arrest_of_woman(fields),
        check_female_officer_involvement(fields),
        check_24_hour_production(fields),
        check_default_bail(fields, None),
    ]
    non_compliant = [c for c in checks if c["status"] in ("Non-Compliant", "May be Non-Compliant")]
    undetermined = [c for c in checks if c["status"] == "Cannot Determine"]
    if non_compliant:
        overall = f"{len(non_compliant)} procedural defect(s) found or suspected. Arrest may be legally vulnerable."
    elif undetermined:
        overall = f"No defects proven, but {len(undetermined)} check(s) could not be verified. Manual review recommended."
    else:
        overall = "All applicable procedural checks pass."
    return {"compliance_checks": checks, "overall_assessment": overall}


def check_freeze_section_and_scope(f):
    req = "Blanket freeze under 106/107 BNSS restrcited to disputed amount [High Court trend]"
    scope = f.get("scope")
    if scope == "specific disputed amount":
        return _result (req, "Compliant", "Freeze scope limited to specific disputed amount.")
    if scope == "entire account":
        return _result(req, "Non-Compliant", "Entire account frozen. High Courts (Karnataka, Kerala,Bombay) have held blanket freezes disproportionate.")
    return _result (req, "Cannot Determine", "Freeze scope not stated in document.")

def check_freeze_magistrate_intimation(f):
    req = "Seizure/freeze intimated forthwith to Magistrate [S.106 BNSS]"
    v= f.get("magistrate_intimation_recorded")
    if v is True:
        return _result(req, "Compliant", "Intimation to jurisdictional Magistrate is recorded.")
    if v is False:
        return _result( req, "Non-Compliant", " No record of intimation to Magistrate. S.106 BNSS requires forthwith intimation.")
    return _result(req, "Cannot Determine", "magistrate intimation not clearly stated.")

def check_freeze_107_court_order(f):
    req = "Attachment/freeze authorized via Section 107 BNSS court intimation"
    section = f.get("section_invoked")
    if section == "107 BNSS":
        v = f.get("court_order_referenced_for_107")
        if v is True:
            return _result(req, "Compliant", "Court order under S.107 BNSS is referenced.")
        if v is False:
            return _result(req, "Non-Compliant", "S.107 BNSS invoked but no referenced court order. Attachment requires prior judicial sanction.")
        return _result(req, "Cannot Determine", "Court order referenced for S.107 unclear.")
    if section == "none cited":
        return _result(req, "May be Non-Compliant", "No legal section was cited to justify this freeze at all. Account/property attachment is supposed to proceed under Section 107 BNSS with Magistrate intimation. A freeze effected without invoking this process, on bare police request alone, may be illegal.")
    return _result(req, "Cannot Determine", f"Freeze invoked under '{section}', not Section 107 BNSS — verify whether the correct attachment procedure was followed.")

def check_freeze_holder_intimation(f):
    req ="Account holder intimated of freeze"
    v = f.get("account_holder_intimated")
    if v is True:
        return _result(req, "Compliant", "Account holder intimated of the freeze.")
    if v is False:
        return _result(req, "Non-Compliant", "Account holder not intimated. Freeze discovered only at bank/ATM violated basic notice principles.")
    return _result(req, "Cannot Determine", "Account holder intimation status unclear.")

def run_freeze_compliance_checks(fields):
    checks = [
        check_freeze_section_and_scope(fields),
        check_freeze_magistrate_intimation(fields),
        check_freeze_107_court_order(fields),
        check_freeze_holder_intimation(fields),
    ]
    
    non_compliant = [c for c in checks if c["status"] in  ("Non-Compliant", "May be Non-Compliant")]
    undetermined = [c for c in checks if c["status"] == "Cannot Determine"]
    if non_compliant:
        overall = f" {len(non_compliant)} defect(s) found or suspected in freeze procedure. Freeze may be legally vulnerable."
    elif undetermined:
        overall = f"{len(undetermined)} check(s) unverifiable. Manual review recommended."
    else:
        overall = "Freeze procedure appears compliant on the face of the document." 
    return {"compliance_checks": checks, "overall_assessment": overall}

def check_ndps_section_50_offer(f):
    req = "Right to be searched before Magistrate/Gazetted Officer offered[ S.50 NDPS/ Baldev Singh]"
    target = f.get("search_target")
    if target!= "person":
        return _result(req, "Not Applicable", "recovery not from the person; S. 50 does not apply(Ranjan Kumar Chadha).")
    offered = f.get("option_offered_to_accused")
    if offered == "magistrate or gazetted officer":
        return _result(req, "Compliant", "Correct S. 50 option offered- Magistrate or Gazetted officer.")
    if offered in ("police officer only", "none offered"):
        return _result (req, "Non-Compliant", f"S.50 requires Magistrate/Gazetted Officer option. Instead :{offered}. Searcg rendered illegal. (Baldev Singh).")
    return _result (req, "Cannot Determine", "S.50 option status unclear from memo.")

def check_ndps_language(f):
    req = "S.50 notice given in language understood by accused[Paramanand]"
    target = f.get("seacrh_target")
    if target != "person":
        return _result(req, "Not Applicable", "S.50 does not apply to this search.")
    v= f.get("language_of_notice_understood_by_accused_confirmed")
    if v is True:
        return _result(req, "Compliant", "Language of notice confirmed understood by accused.")
    if v is False:
        return _result (req, "Non-Compliant", "Notice not confirmed to be in a language the accused understood.")
    return _result (req, "Cannot Determine", "Language comprehension by accused not stated.")

def check_seizure_witnesses(f):
    req= "Independent witnesses present at seizure"
    v= f.get("Independent_witnesses_present")
    if v is True:
        return _result(req, "Compliant", "Independent witnesses recorded as present.")
    if v is False:
        return _result(req, "Non-Compliant", "No independent witnesses recorded. Seizure evidentiary value weakened.")
    return _result(req, "Cannot Determine", "Independent witness presence unclear.")

def run_search_compliance_checks(fields):
    checks= [
        check_ndps_section_50_offer(fields),
        check_ndps_language(fields),
        check_seizure_witnesses(fields),
    ]
    non_compliant = [c for c in checks if c["status"] == "Non-Compliant"]
    undetermined = [c for c in checks if c["status"]== "Cannot Determine"]
    if non_compliant:
        overall = f"{len(non_compliant)} search/seizure defect(s). Recovery may be inadmissible. "
    elif undetermined:
        overall = f"{len(undetermined)} check(s) unverifiable. Manual review recommended."
    else:
        overall = "Search procedure appears compliant on face of the memo."
    return {"compliance_checks": checks, "overall_assessment":overall}

def check_fir_registration_regime(f):
    req = "FIR registration inquiry compliant with regime[lalita Kumari (2014)/ S.173(3) BNSS]"
    complaint_dt = parse_date(f.get("complaint_date"))
    is_cognizable = f.get("offence_alleged_is_cognizable")
    action = f.get("police_action")
    delay = f.get("delay_days")
    
    if is_cognizable is False:
        return _result(req, "Not Applicable", "Alleged offence is not cognizable.")
    if is_cognizable in("unclear", None):
        return _result(req, "Cannot Determine", "Cognizable/non-cognizable status unclear.")
    
    bnss_cutoff= datetime(2024,7,1)
    regime ="BNSS" if complaint_dt and complaint_dt>= bnss_cutoff else "CrPC"
    inquiry_window = 14 if regime == "BNSS" else 7 
    
    if action == "refused to register":
        return _result(req, "Non-Compliant", f"Cognizable offence alleged; refusal to violates Lalita Kumari mandate.")
    if action == "delayed registration" and delay is not None and delay > inquiry_window:
        return _result(req, "Non-Compliant", f"Delay of {delay} days exceeds {inquiry_window}-day inquiry window under {regime}.")
    if action == "NC entry only":
        return _result(req, "Non-Compliant", "NC entry made for a cognizable offence. FIR registartion was mandatory.")
    if action in ("delayed registartion", "closure intimation"):
        return _result(req, "Compliant" , f"Action within {regime} regime; no immediate defect.")
    return _result(req, "Cannot Determine", "Police action on complaint not clearly stated.")


def run_fir_compliance_checks(fields):
    checks = [check_fir_registration_regime(fields)]
    non_compliant = [ c for c in checks if c["status"] == "Non-Compliant"]
    if non_compliant:
        overall =" FIR registration violation identified. Approach Magistrate under S.175(3) BNSS. "
    else:
        overall = "No FIR registartion defecr proven from document."
    return {"Compliance_checks": checks, "overall_assessment": overall}

def check_vulnerable_location(f):
    req = " Woman/minor/senior summoned at residence, not station[S.179 BNSS/ S. 160(1) CrPC]"
    gender= f.get("summoned_person_gender")
    age = f.get("summoned_person_age")
    protected= gender == "female" or (age is not None and (age <18 or age >60))
    if not protected:
        return _result(req, "Not Applicable", "Person does not fall in protected category.")
    loc= f.get("summons_location")
    if loc=="residence":
        return _result(req, "Compliant", "Summons issued for examination at residence.")
    if loc=="police station":
        return _result (req, "Non-Compliant", "Protected person summoned to police station-direct S.179 BNSS violation.")
    return _result(req, "Cannot Determine", "Summons location not clearly stated.")

def check_vulnerable_female_officer(f):
    req = "Female officer involvement for female summoned person [Sheela Barse]"
    if f.get("summoned_person_gender")!= "female":
        return _result(req, "Not Applicable", "Person is not female.")
    v= f.get("female_officer_involved")
    if v is True:
        return _result(req, "Compliant", "Female officer involvement recorded.")
    if v is False:
        return _result(req, "Non-Compliant", "No female officer involvement for a female person- Sheela Barse violation." )
    return _result(req, "Cannot Determine", "Female officer involvment unclear.")

def run_vulnerable_compliance_checks(fields):
    checks =[
        check_vulnerable_location(fields),
        check_vulnerable_female_officer(fields),
    ]
    non_compliant = [ c for c in checks if c["status"] == "Non-Compliant"]
    if non_compliant:
        overall = f"{len(non_compliant)} defect(s) in summons procedure."
    else:
        overall= "Summons procedure appears compliant on face of document."
    return {"compliance_checks": checks, "overall_assessment":overall}

#-------Router :subtype-> (extraction prompt, runner)-------------------------
POLICE_ROUTES ={
     "Arrest-related" : (ARREST_EXTRACTION_PROMPT, run_arrest_compliance_checks),
     "Bank/Account Freezing": ( FREEZE_EXTRACTION_PROMPT, run_freeze_compliance_checks),
     "Search & Seizure" : ( SEARCH_EXTRACTION_PROMPT, run_search_compliance_checks),
     "FIR Registration Dispute": (FIR_DISPUTE_EXTRACTION_PROMPT, run_fir_compliance_checks),
     "Summons to Vulnerable Person": (VULNERABLE_EXTRACTION_PROMPT, run_vulnerable_compliance_checks)
}
 
def run_police_pipeline(document_text):
    """Classify a police document into a sub type , extract fields  , run subtype-specific checks."""
    r = client.messages.create(
        model = "claude-haiku-4-5-20251001",
        max_tokens= 200,
        temperature=0,
        messages=[{"role": "user", "content": POLICE_SUBTYPE_PROMPT.format(document_text=document_text)}]
    )
    try :
        subtype_obj = parse_json_response(r.content[0].text)
        subtype = subtype_obj.get("police_subtype", "Other")
    except json.JSONDecodeError:
        subtype="Other"
    route = POLICE_ROUTES.get(subtype)
    if route is None:
        return {
            "police_subtype": subtype,
            "extracted_fields": {},
            "compliance": {"compliance_checks": [], "overall_assessment": "No sub-type-specific check available."}
        }
    extraction_prompt, runner = route
    r= client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        temperature=0,
        messages =[{"role": "user", "content": extraction_prompt.format(document_text=document_text)}]
        
    )
    try:
        extracted = parse_json_response(r.content[0].text)
    except json.JSONDecodeError:
        extracted= {"error": "Failed to parse extractio", "raw": r.content[0].text}
    return {
        "police_subtype" : subtype,
        "extracted_fields": extracted,
        "compliance": runner(extracted)
    }
     
    
  

def analyze_document(document_text):
    classification_prompt = f"""You are analyzing an Indian legal or administrative document. Classify it into exactly one of these categories:

- Banking & Cheque Bounce — examples: Section 138 NI Act notice, loan default demand notice, EMI default reminder
- Police & Criminal Process — examples: notice to appear for investigation (Section 35 BNSS / old 41A CrPC), summons to produce documents or devices (Section 94 BNSS), notice to join investigation (Section 179 BNSS), arrest memo, FIR copy served to accused, notice in dowry/cruelty complaint (Section 85 BNS), notice in cyber fraud investigation, notice to vehicle owner in accident case, bail condition compliance notice, externment/bound-over notice under Section 125 CrPC / Section 126 BNSS, police closure report served to complainant
- Tenancy & Property — examples: eviction notice, rent recovery notice, property dispute notice
- Individual Tax Notices — examples: Income Tax demand notice, GST notice for small traders — not corporate/enterprise tax matters
- Government / Revenue Orders — examples: revenue department orders, land record notices, government circulars affecting citizens

If the document doesn't clearly fit one of these five, classify it as "Other" rather than forcing a fit.

Respond with only valid JSON in this exact format, no other text:
{{"document_type": "category name", "sub_type": "specific notice type within that category", "confidence": "high/medium/low", "reasoning": "one sentence explanation"}}
"document_type" must be exactly the category name only, never including the examples in parentheses

Document text:
{document_text}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        temperature=0,
        messages=[{"role": "user", "content": classification_prompt}]
    )
    try:
        classification_result = parse_json_response(response.content[0].text)
    except json.JSONDecodeError:
        classification_result = {"error": "Failed to parse model response", "raw": response.content[0].text}

    # ---- Category-aware compliance routing now happens FIRST, before missing_info ----
    top_category = classification_result.get("document_type", "")
    extracted_fields = {}

    if top_category == "Police & Criminal Process":
        police_result = run_police_pipeline(document_text)
        compliance_result = police_result["compliance"]
        classification_result["police_subtype"] = police_result["police_subtype"]
        extracted_fields = police_result["extracted_fields"]
        classification_result["extracted_fields"] = extracted_fields
    elif top_category == "Banking & Cheque Bounce":
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            temperature=0,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(document_text=document_text)}]
        )
        try:
            extracted_fields = parse_json_response(response.content[0].text)
        except json.JSONDecodeError:
            extracted_fields = {"error": "Failed to parse extraction response", "raw": response.content[0].text}
        compliance_result = run_compliance_checks(extracted_fields)
    else:
        compliance_result = {
            "compliance_checks": [],
            "overall_assessment": f"No compliance checker built yet for category: {top_category}. See README roadmap."
        }

    # ---- NOW build missing_info_prompt, grounded with whatever sections were actually extracted ----
    section_context = build_grounded_section_context(extracted_fields.get("sections_cited", []))

    missing_info_prompt = f"""You are reviewing an Indian legal notice for completeness. Identify what information is missing, vague, or unsupported by evidence — not what the notice contains.

VERIFIED SECTION CONTEXT (use this, do not guess or rely on your own knowledge of what these sections mean):
{section_context}

Do not state or assume what any cited section legally covers or means beyond what is given above. If a section is marked "not in our verified reference table," say only that its scope could not be verified — do not fill in your own answer.

Check specifically for:
- Whether a clear calculation or amount breakdown is provided (not just a total figure)
- Whether supporting documents are actually attached/referenced (not just claimed to exist)
- Whether the deadline for response is stated explicitly and unambiguously
- Whether the issuing party's authority or standing to send this notice is clear
- Whether the underlying facts (dates, transaction details) are specific or vague

Respond with only valid JSON in this exact format, no other text:
{{"missing_or_unclear": ["flag 1", "flag 2", ...], "completeness_assessment": "one sentence overall judgment"}}

If nothing is missing, return an empty list for "missing_or_unclear" and say so in the assessment.

Document text:
{document_text}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        temperature=0,
        messages=[{"role": "user", "content": missing_info_prompt}]
    )
    try:
        missing_info_result = parse_json_response(response.content[0].text)
    except json.JSONDecodeError:
        missing_info_result = {"error": "Failed to parse model response", "raw": response.content[0].text}

    # ---- deadline extraction and urgency, unchanged ----
    deadline_extraction_prompt = f"""...same as before..."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        temperature=0,
        messages=[{"role": "user", "content": deadline_extraction_prompt}]
    )
    try:
        deadline_fields = parse_json_response(response.content[0].text)
    except json.JSONDecodeError:
        deadline_fields = {"error": "Failed to parse deadline extraction", "raw": response.content[0].text}

    days_remaining = calculate_days_remaining(deadline_fields, deadline_fields.get("notice_date"))
    if days_remaining is None:
        urgency_result = {
            "urgency_level": "Cannot Determine",
            "deadline_message": "Deadline could not be extracted from this document. Manual review required.",
            "days_remaining": None
        }
    else:
        urgency_result = build_analysis_summary(days_remaining)

    full_analysis = {
        "classification": classification_result,
        "missing_info": missing_info_result,
        "compliance": compliance_result,
        "checklist": get_document_checklist(classification_result.get("document_type", "")),
        "urgency": urgency_result,
        "extracted_fields": extracted_fields
    }

    return full_analysis


if __name__ == "__main__":
    document_text = clean_text(extract_text_from_pdf("Sample_Bank_Freeze_Notice_NoSection.pdf"))
    #print("DEBUG:", repr(document_text[:200]))
    result = analyze_document(document_text)
    print(json.dumps(result, indent=2))

