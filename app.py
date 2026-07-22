import streamlit as st
import re
from main import (
    analyze_document,
    extract_text_from_pdf,
    clean_text,
    check_default_bail,
    generate_compliance_brief,
    run_arrest_compliance_checks,
    run_freeze_compliance_checks,
    run_compliance_checks,
    get_document_checklist,
    BNS_SECTION_DATA,
    compute_severity,
)

# =============================================================
# PAGE SETUP
# =============================================================
st.title("Know Your Rights")
st.caption("Indian Legal Notice & Procedural Compliance Analyzer")
st.write(
    "Upload a legal notice PDF for analysis (currently supports Banking & Cheque Bounce "
    "notices, Police & Criminal Processes, and Procedures under 106/107 BNSS)"
)

mode = st.radio(
    "What would you like to do?",
    ["I have a document to upload", "I don't have any paper — ask me questions instead"]
)

st.divider()

# =============================================================
# SHARED HELPERS
# =============================================================
ALIASES = {
    "cheque bounce": "cheque", "bounced cheque": "cheque", "stealing": "theft",
    "fraud": "cheating", "cheat": "cheating", "domestic violence": "cruelty",
    "dowry harassment": "dowry", "rob": "robbery",
}

def find_sections_by_crime_name(typed_name):
    if not typed_name or not typed_name.strip():
        return []
    query = typed_name.strip().lower()
    query = ALIASES.get(query, query)
    return [sec for sec, data in BNS_SECTION_DATA.items() if query in data["offence"].lower()]

def yn(v):
    return {True: True, False: False, "unclear": "unclear"}.get(v, "unclear")

def render_compliance_ui(result):
    """Replaces raw st.json() calls with a readable, structured display."""

    classification = result.get("classification", {})
    compliance = result.get("compliance", {})
    missing = result.get("missing_info", {})
    checklist = result.get("checklist", [])
    urgency = result.get("urgency", {})

    # ---- BLOCK 1: What this is ----
    st.markdown("### 📄 What This Is")
    col1, col2 = st.columns(2)
    with col1:
        st.caption("Category")
        st.markdown(f"**{classification.get('document_type', 'N/A')}**")
    with col2:
        st.caption("Sub-type")
        st.markdown(f"**{classification.get('sub_type', 'N/A')}**")
    st.caption(classification.get("reasoning", ""))
    st.divider()

    # ---- BLOCK 2a: Urgency & Deadline — Section 138 (Banking & Cheque Bounce) ONLY ----
    document_type = classification.get("document_type", "")
    if document_type == "Banking & Cheque Bounce":
        st.markdown("### ⏱️ Urgency & Deadline")
        urgency_level = urgency.get("urgency_level", "Cannot Determine")
        urgency_colors = {
            "DEADLINE PASSED": "🔴", "CRITICAL": "🔴", "HIGH RISK": "🟠",
            "FORMAL": "🟡", "ROUTINE": "🟢", "Cannot Determine": "⚪",
        }
        icon = urgency_colors.get(urgency_level, "⚪")
        st.markdown(f"## {icon} {urgency_level}")
        if urgency.get("days_remaining") is not None:
            st.metric("Days remaining", urgency["days_remaining"])
        dm = urgency.get("deadline_message")
        if isinstance(dm, dict):
            for k, v in dm.items():
                st.write(f"**{k.replace('_', ' ').title()}:** {v}")
        elif dm:
            st.write(dm)
        st.divider()

    # ---- BLOCK 2b: Procedural Compliance Severity — ALL domains ----
    severity = result.get("severity", {})
    st.markdown("### 🛡️ Procedural Compliance Severity")
    severity_icons = {"green": "🟢", "amber": "🟡", "orange": "🟠", "red": "🔴"}
    icon = severity_icons.get(severity.get("severity_color"), "⚪")
    st.markdown(f"## {icon} {severity.get('severity_label', 'Not Available')}")
    st.markdown(f"# {severity.get('severity_meter', '')}")

    unresolved = severity.get("unresolved_checks", 0)
    if unresolved > 0:
        st.caption(f"{unresolved} check(s) could not be verified from the information given.")
    st.divider()
    
    
    
    

    # ---- BLOCK 3: Compliance findings ----
    st.markdown("### ⚖️ Was Correct Procedure Followed?")
    status_style = {
        "Compliant": ("✅", "green"),
        "Non-Compliant": ("❌", "red"),
        "May be Non-Compliant": ("⚠️", "orange"),
        "Cannot Determine": ("❔", "gray"),
        "Not Applicable": ("➖", "gray"),
    }
    for check in compliance.get("compliance_checks", []):
        emoji, color = status_style.get(check.get("status"), ("❔", "gray"))
        with st.container(border=True):
            st.markdown(f"{emoji} **{check.get('requirement', '')}**")
            st.markdown(f":{color}[{check.get('status', '')}]")
            st.caption(check.get("explanation", ""))

    overall = compliance.get("overall_assessment", "")
    if overall:
        st.info(overall)
    st.divider()

    # ---- BLOCK 4: What's missing ----
    flags = missing.get("missing_or_unclear", [])
    if flags:
        st.markdown("### 🔍 What's Missing or Unclear")
        for flag in flags:
            st.markdown(f"- {flag}")
        st.divider()

    # ---- BLOCK 5: Document checklist ----
    if checklist:
        st.markdown("### 📋 Documents to Gather")
        for item in checklist:
            st.checkbox(item, key=f"chk_{hash(item)}")
            
    # ---- Raw data, collapsed, for debugging only ----
    with st.expander("Show raw data"):
        st.json(result)
        
# =============================================================
# DOMAIN 1: ARREST-RELATED — questions (unchanged from before)
# =============================================================
ARREST_QUESTIONS = [
    {"key": "arrestee_gender", "text": "Is the person who was arrested a man or a woman?",
     "type": "choice", "options": ["Man", "Woman"]},
    {"key": "arrest_datetime", "text": "When did the police take the person?",
     "type": "datetime"},
    {"key": "notice_before", "text": "Before taking them, did police give any paper asking them to come to the station?",
     "type": "yesno"},
    {"key": "grounds_given", "text": "At the time of arrest, did police give a paper explaining exactly why?",
     "type": "yesno"},
    {"key": "witness_present", "text": "Was a family member or neighbour present, and did they sign any paper?",
     "type": "yesno"},
    {"key": "family_informed", "text": "Was any family member told about the arrest?",
     "type": "yesno"},
    {"key": "medical_done", "text": "Was the person checked by a doctor around the time of arrest?",
     "type": "yesno"},
    {"key": "female_officer", "text": "Was a woman police officer present?",
     "type": "yesno"},
    {"key": "production_datetime", "text": "Has the person been taken in front of a judge yet? If yes, when?",
     "type": "datetime_optional"},
    {"key": "section_known", "text": "Do you know the name of the crime the police mentioned? (e.g. cheating, theft, dowry)",
     "type": "crime_name_search"},
    {"key": "chargesheet_filed", "text": "Has a formal charge-sheet been filed? If yes, when?",
     "type": "datetime_optional"},
]

def arrest_filter(questions, answers):
    if answers.get("arrestee_gender") != "Woman":
        return [q for q in questions if q["key"] != "female_officer"]
    return questions

def build_arrest_fields(answers):
    return {
        "arrestee_gender": "female" if answers.get("arrestee_gender") == "Woman" else "male",
        "arrest_datetime_full": answers.get("arrest_datetime"),
        "production_datetime_full": answers.get("production_datetime"),
        "sections_cited": answers.get("section_known", []),
        "punishment_years_upper_bound": None,
        "41A_or_35_BNSS_notice_issued_before_arrest": yn(answers.get("notice_before")),
        "grounds_of_arrest_in_writing_furnished_to_arrestee": yn(answers.get("grounds_given")),
        "witness_attested_memo": yn(answers.get("witness_present")),
        "family_or_friend_informed": yn(answers.get("family_informed")),
        "medical_exam_at_arrest_recorded": yn(answers.get("medical_done")),
        "female_officer_present_for_female_arrestee": (
            yn(answers.get("female_officer")) if answers.get("arrestee_gender") == "Woman" else "not applicable"
        ),
        "chargesheet_filed_date": answers.get("chargesheet_filed"),
    }
    



# =============================================================
# DOMAIN 2: BANK ACCOUNT FREEZING — new
# =============================================================
FREEZE_QUESTIONS = [
    {"key": "freeze_date", "text": "When did you find out the account was frozen or blocked?",
     "type": "datetime_optional"},
    {"key": "section_choice", "text": "Did the freeze letter or notice mention a specific legal section?",
     "type": "choice_or_text",
     "options": ["Section 106", "Section 107", "Some other section (type it)", "No section was mentioned", "I don't know — never received any freeze letter or notice"],
     "text_trigger": "Some other section (type it)"},
    {"key": "scope", "text": "Was the entire account frozen, or only a specific amount?",
     "type": "choice",
     "options": ["Entire account was frozen", "Only a specific amount was frozen", "Not sure"]},
    {"key": "specific_amount", "text": "Do you know the amount that was allegedly involved (the disputed amount)?",
     "type": "number_optional", "input_label": "Amount (Rs.)"},
    {"key": "account_holder_intimated",
     "text": "How did you find out about the freeze?",
     "type": "choice",
     "options": ["A written intimation was received", "Card / Payment decline", "Other"]},
    {"key": "magistrate_intimation", "text": "Do you know if a magistrate or court was informed about this freeze?",
     "type": "yesno"},
    {"key": "court_order_107", "text": "Was any court order mentioned or shown to you along with the freeze?",
     "type": "yesno"},
]

def freeze_filter(questions, answers):
    if answers.get("section_choice") != "Section 107":
        return [q for q in questions if q["key"] != "court_order_107"]
    return questions

def build_freeze_fields(answers):
    section_map = {
        "Section 106": "106 BNSS",
        "Section 107": "107 BNSS",
        "No section was mentioned": "none cited",
        "I don't know — never received any freeze letter or notice": "unclear",
    }
    raw_section = answers.get("section_choice", "unclear")
    if isinstance(raw_section, str) and raw_section.startswith("typed:"):
        section_invoked = raw_section.replace("typed:", "").strip() or "other"
    else:
        section_invoked = section_map.get(raw_section, "unclear")

    scope_map = {
        "Entire account was frozen": "entire account",
        "Only a specific amount was frozen": "specific disputed amount",
        "Not sure": "unclear",
    }

    intimation_map = {
        "A written intimation was received": True,
        "Card / Payment decline": False,
        "Other": "unclear",
    }

    return {
        "freeze_date": answers.get("freeze_date"),
        "section_invoked": section_invoked,
        "scope": scope_map.get(answers.get("scope"), "unclear"),
        "specific_amount_stated": answers.get("specific_amount"),
        "account_holder_intimated": intimation_map.get(answers.get("account_holder_intimated"), "unclear"),
        "magistrate_intimation_recorded": yn(answers.get("magistrate_intimation")),
        "magistrate_intimation_date": None,
        "court_order_referenced_for_107": (
            yn(answers.get("court_order_107")) if section_invoked == "107 BNSS" else "not applicable"
        ),
    }


# =============================================================
# DOMAIN 3: CHEQUE BOUNCE (Section 138 NI Act) — new
# =============================================================
CHEQUE_QUESTIONS = [
    {"key": "return_memo_date", "text": "When did the bank return or bounce the cheque?",
     "type": "datetime_optional"},
    {"key": "notice_date", "text": "When was the legal notice sent or received?",
     "type": "datetime_optional"},
    {"key": "cheque_face_value", "text": "What amount was written on the cheque?",
     "type": "number_optional", "input_label": "Amount (Rs.)"},
    {"key": "demand_amount", "text": "What amount is the notice asking you to pay?",
     "type": "number_optional", "input_label": "Amount (Rs.)"},
    {"key": "payment_window", "text": "How many days did the notice give you to pay?",
     "type": "number_optional", "input_label": "Number of days"},
    {"key": "interest_bundled",
     "text": "Does the notice mix interest or extra costs together with the main amount in the same sentence, rather than listing them separately?",
     "type": "yesno"},
    {"key": "cheque_purpose", "text": "Was the cheque given to repay a loan or debt, or as a security/advance?",
     "type": "choice", "options": ["To repay a loan or debt", "As a security or advance", "Not sure"]},
]

def cheque_filter(questions, answers):
    return questions  # no conditional questions in this domain

def build_cheque_fields(answers):
    purpose_map = {
        "To repay a loan or debt": "debt", "As a security or advance": "security", "Not sure": "unclear",
    }
    return {
        "return_memo_date": answers.get("return_memo_date"),
        "notice_date": answers.get("notice_date"),
        "cheque_face_value": answers.get("cheque_face_value"),
        "demand_principal_amount": answers.get("demand_amount"),
        "payment_window_days_granted": answers.get("payment_window"),
        "interest_bundled_in_principal_sentence": answers.get("interest_bundled") is True,
        "cheque_purpose": purpose_map.get(answers.get("cheque_purpose"), "unclear"),
    }


# =============================================================
# DOMAIN REGISTRY — one config per issue type
# =============================================================
INTERVIEW_CONFIGS = {
    "Arrest-related process": {
        "questions": ARREST_QUESTIONS,
        "filter_fn": arrest_filter,
        "build_fields": build_arrest_fields,
        "compliance_runner": run_arrest_compliance_checks,
        "checklist_category": "Police & Criminal Process",
        "sub_type_label": "Arrest — reported via guided interview (no document)",
    },
    "Bank Account Freezing": {
        "questions": FREEZE_QUESTIONS,
        "filter_fn": freeze_filter,
        "build_fields": build_freeze_fields,
        "compliance_runner": run_freeze_compliance_checks,
        "checklist_category": "Police & Criminal Process",
        "sub_type_label": "Bank/Account Freezing — reported via guided interview (no document)",
    },
    "Cheque Bounce": {
        "questions": CHEQUE_QUESTIONS,
        "filter_fn": cheque_filter,
        "build_fields": build_cheque_fields,
        "compliance_runner": run_compliance_checks,
        "checklist_category": "Banking & Cheque Bounce",
        "sub_type_label": "Section 138 NI Act — reported via guided interview (no document)",
    },
}
NOT_YET_AVAILABLE = ["Other"]


# =============================================================
# GENERIC INTERVIEW ENGINE — domain-agnostic
# =============================================================
def run_interview(domain_key):
    config = INTERVIEW_CONFIGS[domain_key]
    step_key = f"step__{domain_key}"
    answers_key = f"answers__{domain_key}"
    st.session_state.setdefault(step_key, 0)
    st.session_state.setdefault(answers_key, {})
    st.session_state.setdefault("crime_matches", None)

    step = st.session_state[step_key]

    if step == 0:
        st.subheader(f"Has this situation ({domain_key}) actually happened to you or someone you know?")
        col1, col2 = st.columns(2)
        if col1.button("Yes", use_container_width=True, key=f"gate_yes_{domain_key}"):
            st.session_state[step_key] = 1
            st.rerun()
        if col2.button("No, I'm just exploring", use_container_width=True, key=f"gate_no_{domain_key}"):
            st.info("No problem — feel free to explore the tool, or come back when you need it.")
        return

    questions = config["filter_fn"](config["questions"], st.session_state[answers_key])

    if step > len(questions):
        show_interview_results(domain_key, config)
        return

    q = questions[step - 1]
    st.progress(step / len(questions))

    if st.button("◀ Back", key=f"back_{domain_key}_{step}"):
        st.session_state[step_key] = step - 1
        st.rerun()

    st.subheader(q["text"])

    answer = None

    if q["type"] == "yesno":
        c1, c2, c3 = st.columns(3)
        if c1.button("Yes", use_container_width=True, key=f"y_{domain_key}_{q['key']}"):
            answer = True
        if c2.button("No", use_container_width=True, key=f"n_{domain_key}_{q['key']}"):
            answer = False
        if c3.button("Not sure", use_container_width=True, key=f"u_{domain_key}_{q['key']}"):
            answer = "unclear"

    elif q["type"] == "choice":
        for opt in q["options"]:
            if st.button(opt, use_container_width=True, key=f"c_{domain_key}_{q['key']}_{opt}"):
                answer = opt

    elif q["type"] == "choice_or_text":
        for opt in q["options"]:
            if st.button(opt, use_container_width=True, key=f"ct_{domain_key}_{q['key']}_{opt}"):
                if opt == q.get("text_trigger"):
                    st.session_state[f"showtext_{domain_key}_{q['key']}"] = True
                    st.rerun()
                else:
                    answer = opt
        if st.session_state.get(f"showtext_{domain_key}_{q['key']}"):
            typed = st.text_input("Type it here", key=f"typed_{domain_key}_{q['key']}")
            if st.button("Use this", use_container_width=True, key=f"usetyped_{domain_key}_{q['key']}"):
                if typed.strip():
                    answer = f"typed:{typed.strip()}"

    elif q["type"] == "datetime":
        d = st.date_input("Date", key=f"date_{domain_key}_{q['key']}")
        t = st.time_input("Approximate time", key=f"time_{domain_key}_{q['key']}")
        if st.button("Next", use_container_width=True, key=f"next_{domain_key}_{q['key']}"):
            answer = f"{d.strftime('%d-%m-%Y')} {t.strftime('%H:%M')}"

    elif q["type"] == "datetime_optional":
        known = st.radio("Do you know this?", ["Not yet / Don't know", "Yes, I know the date"],
                          key=f"radio_{domain_key}_{q['key']}")
        if known == "Yes, I know the date":
            d = st.date_input("Date", key=f"date2_{domain_key}_{q['key']}")
            if st.button("Next", use_container_width=True, key=f"next2_{domain_key}_{q['key']}"):
                answer = d.strftime("%d-%m-%Y")
        else:
            if st.button("Next", use_container_width=True, key=f"next3_{domain_key}_{q['key']}"):
                answer = "SKIPPED"

    elif q["type"] == "number_optional":
        known = st.radio("Do you know this?", ["Not sure / don't know", "Yes, I know it"],
                          key=f"radion_{domain_key}_{q['key']}")
        if known == "Yes, I know it":
            val = st.number_input(q.get("input_label", "Amount"), min_value=0, step=1,
                                   key=f"num_{domain_key}_{q['key']}")
            if st.button("Next", use_container_width=True, key=f"nextn_{domain_key}_{q['key']}"):
                answer = val
        else:
            if st.button("Next", use_container_width=True, key=f"nextn2_{domain_key}_{q['key']}"):
                answer = "SKIPPED"

    elif q["type"] == "crime_name_search":
        st.write("Type the name of the crime, in your own words:")
        typed = st.text_input("Crime name", key="crime_typed", placeholder="e.g. cheating, theft, dowry, murder")
        if st.button("Search", use_container_width=True, key=f"search_{domain_key}_{q['key']}") and typed.strip():
            st.session_state["crime_matches"] = find_sections_by_crime_name(typed)
        matches = st.session_state.get("crime_matches")
        if matches is not None:
            if len(matches) == 0:
                st.info("We couldn't match that to a known offence. That's fine — we'll say so honestly rather than guess.")
                if st.button("Continue without a match", use_container_width=True, key=f"cont_{domain_key}_{q['key']}"):
                    answer = []
            elif len(matches) == 1:
                sec = matches[0]
                st.success(f"Matched: {BNS_SECTION_DATA[sec]['offence']} (Section {sec})")
                if st.button("Confirm and continue", use_container_width=True, key=f"conf_{domain_key}_{q['key']}"):
                    answer = matches
            else:
                st.write("A few offences matched — please pick the one that fits best:")
                for sec in matches:
                    label = f"{BNS_SECTION_DATA[sec]['offence']} (Section {sec})"
                    if st.button(label, use_container_width=True, key=f"match_{domain_key}_{sec}"):
                        answer = [sec]
        st.caption("If we don't recognize the exact offence, we'll say so honestly rather than guess.")

    if answer is not None:
        stored = None if answer == "SKIPPED" else answer
        st.session_state[answers_key][q["key"]] = stored
        st.session_state["crime_matches"] = None
        st.session_state[step_key] += 1
        st.rerun()


def show_interview_results(domain_key, config):
    if st.button("◀ Back to last question", key=f"back_results_{domain_key}"):
        st.session_state[f"step__{domain_key}"] = len(config["questions"])
        st.rerun()
    answers = st.session_state[f"answers__{domain_key}"]
    fields = config["build_fields"](answers)
    compliance_result = config["compliance_runner"](fields)

    full_analysis = {
        "classification": {
            "document_type": config["checklist_category"],
            "sub_type": config["sub_type_label"],
            "reasoning": "Built from answers you gave, since no document was available."
        },
        "missing_info": {
            "missing_or_unclear": [],
            "completeness_assessment": "Based on interview answers only — not a document review."
        },
        "compliance": compliance_result,
        "checklist": get_document_checklist(config["checklist_category"]),
        "urgency": {"urgency_level": "Cannot Determine", "deadline_message": "N/A for interview mode", "days_remaining": None},
        "severity": compute_severity(compliance_result.get("compliance_checks", [])),
        "extracted_fields": fields
    }

    render_compliance_ui(full_analysis)

    default_bail_check = next(
        (c for c in compliance_result.get("compliance_checks", []) if "Default bail" in c["requirement"]),
        None
    )
    if default_bail_check and default_bail_check["status"] in ("Cannot Determine", "May be Non-Compliant"):
        st.subheader("One More Question")
        st.write("We couldn't fully resolve the default-bail deadline from your answers.")
        chargesheet_answer = st.radio("Has a chargesheet been filed in this case?",
                                       ["Not yet / Don't know", "Yes"], key=f"cs_radio_{domain_key}")
        if chargesheet_answer == "Yes":
            user_cs_date = st.date_input("Chargesheet filing date", key=f"cs_date_{domain_key}")
            updated_check = check_default_bail(fields, user_chargesheet_date=user_cs_date.strftime("%d-%m-%Y"))
            st.write("Updated result:")
            st.json(updated_check)

    if st.button("Generate Compliance Brief", key=f"genbrief_{domain_key}"):
        pdf_path = generate_compliance_brief(full_analysis, output_path=f"interview_brief_{domain_key}.pdf")
        with open(pdf_path, "rb") as f:
            st.session_state[f"brief_bytes__{domain_key}"] = f.read()

    if f"brief_bytes__{domain_key}" in st.session_state:
        st.download_button(
            "Download Compliance Brief (PDF)",
            data=st.session_state[f"brief_bytes__{domain_key}"],
            file_name="compliance_brief.pdf",
            mime="application/pdf",
            key=f"dl_{domain_key}"
        )

    if st.button("Start over", key=f"restart_{domain_key}"):
        st.session_state[f"step__{domain_key}"] = 0
        st.session_state[f"answers__{domain_key}"] = {}
        st.session_state.pop(f"brief_bytes__{domain_key}", None)
        st.rerun()


# =============================================================
# NO-DOCUMENT FLOW: issue-type selector -> routes to the right interview
# =============================================================
def run_no_document_flow():
    issue_type = st.selectbox(
        "What kind of legal issue are you facing?",
        list(INTERVIEW_CONFIGS.keys()) + NOT_YET_AVAILABLE
    )

    if "active_domain" not in st.session_state:
        st.session_state["active_domain"] = issue_type
    elif st.session_state["active_domain"] != issue_type:
        # domain switched mid-session — reset so old answers don't leak in
        st.session_state["active_domain"] = issue_type

    if issue_type in NOT_YET_AVAILABLE:
        st.info(
            f"Guided questions for **{issue_type}** aren't available yet — this is still being built. "
            "If you have any paper related to this issue, even a partial one, please try uploading it instead."
        )
        return

    run_interview(issue_type)


# =============================================================
# DOCUMENT UPLOAD FLOW — unchanged from before
# =============================================================
def run_document_flow():
    uploaded_file = st.file_uploader("Choose a PDF", type="pdf")

    if uploaded_file is not None:
        with open("temp_uploaded.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())

        if st.button("Analyze"):
            with st.spinner("Analyzing..."):
                document_text = clean_text(extract_text_from_pdf("temp_uploaded.pdf"))
                st.session_state["result"] = analyze_document(document_text)

        if "result" in st.session_state:
            result = st.session_state["result"]
            render_compliance_ui(result)

           

            if st.button("Generate Compliance Brief"):
                pdf_path = generate_compliance_brief(result, output_path="compliance_brief.pdf")
                with open(pdf_path, "rb") as f:
                    st.session_state["brief_bytes"] = f.read()

            if "brief_bytes" in st.session_state:
                st.download_button(
                    label="Download Compliance Brief (PDF)",
                    data=st.session_state["brief_bytes"],
                    file_name="compliance_brief.pdf",
                    mime="application/pdf"
                )

            default_bail_check = next(
                (c for c in result["compliance"].get("compliance_checks", []) if "Default bail" in c["requirement"]),
                None
            )
            if default_bail_check and default_bail_check["status"] in ("Cannot Determine", "May be Non-Compliant"):
                st.subheader("One More Question")
                st.write("This document alone couldn't fully resolve the default-bail deadline.")
                chargesheet_answer = st.radio("Has a chargesheet been filed in this case?", ["Not yet / Don't know", "Yes"])
                if chargesheet_answer == "Yes":
                    user_cs_date = st.date_input("Chargesheet filing date")
                    updated_check = check_default_bail(
                        result["extracted_fields"],
                        user_chargesheet_date=user_cs_date.strftime("%d-%m-%Y")
                    )
                    st.write("Updated result:")
                    st.json(updated_check)


# =============================================================
# ROUTER
# =============================================================
if mode == "I have a document to upload":
    run_document_flow()
else:
    run_no_document_flow()