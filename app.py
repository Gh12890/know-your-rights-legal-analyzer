import streamlit as st
import re
from main import (
    analyze_document,
    extract_text_from_pdf,
    clean_text,
    check_default_bail,
    generate_compliance_brief,
    run_arrest_compliance_checks,
    get_document_checklist,
    BNS_SECTION_DATA,
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
# CRIME-NAME -> SECTION LOOKUP (reuses the verified BNS table only)
# =============================================================
ALIASES = {
    "cheque bounce": "cheque",
    "bounced cheque": "cheque",
    "stealing": "theft",
    "fraud": "cheating",
    "cheat": "cheating",
    "domestic violence": "cruelty",
    "dowry harassment": "dowry",
    "rob": "robbery",
}

def find_sections_by_crime_name(typed_name):
    """Search the verified BNS_SECTION_DATA offence descriptions for keyword
    matches. Never guesses beyond what's in the table — honest empty result
    if nothing matches."""
    if not typed_name or not typed_name.strip():
        return []
    query = typed_name.strip().lower()
    query = ALIASES.get(query, query)
    matches = []
    for section, data in BNS_SECTION_DATA.items():
        if query in data["offence"].lower():
            matches.append(section)
    return matches


# =============================================================
# GUIDED INTERVIEW — Arrest-related only, no document required
# =============================================================
INTERVIEW_QUESTIONS = [
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


def get_active_questions():
    questions = INTERVIEW_QUESTIONS
    if st.session_state["interview_answers"].get("arrestee_gender") != "Woman":
        questions = [q for q in questions if q["key"] != "female_officer"]
    return questions


def run_interview():
    st.session_state.setdefault("interview_step", 0)
    st.session_state.setdefault("interview_answers", {})
    st.session_state.setdefault("crime_matches", None)

    step = st.session_state["interview_step"]

    # ---- Gate question ----
    if step == 0:
        st.subheader("Has someone you know been arrested by police recently?")
        col1, col2 = st.columns(2)
        if col1.button("Yes", use_container_width=True):
            st.session_state["interview_step"] = 1
            st.rerun()
        if col2.button("No — something else happened", use_container_width=True):
            st.warning(
                "Right now this tool can only check arrest situations without a document. "
                "Please try uploading any paper you do have, or check back soon."
            )
        return

    questions = get_active_questions()

    # ---- All questions answered -> show results ----
    if step > len(questions):
        show_interview_results()
        return

    q = questions[step - 1]
    st.progress(step / len(questions))
    st.subheader(q["text"])

    answer = None

    if q["type"] == "yesno":
        c1, c2, c3 = st.columns(3)
        if c1.button("Yes", use_container_width=True):
            answer = True
        if c2.button("No", use_container_width=True):
            answer = False
        if c3.button("Not sure", use_container_width=True):
            answer = "unclear"

    elif q["type"] == "choice":
        for opt in q["options"]:
            if st.button(opt, use_container_width=True):
                answer = opt

    elif q["type"] == "datetime":
        d = st.date_input("Date")
        t = st.time_input("Approximate time")
        if st.button("Next", use_container_width=True):
            answer = f"{d.strftime('%d-%m-%Y')} {t.strftime('%H:%M')}"

    elif q["type"] == "datetime_optional":
        known = st.radio("Do you know this?", ["Not yet / Don't know", "Yes, I know the date"])
        if known == "Yes, I know the date":
            d = st.date_input("Date")
            if st.button("Next", use_container_width=True):
                answer = d.strftime("%d-%m-%Y")
        else:
            if st.button("Next", use_container_width=True):
                answer = "SKIPPED"

    elif q["type"] == "crime_name_search":
        st.write("Type the name of the crime, in your own words:")
        typed = st.text_input("Crime name", key="crime_typed", placeholder="e.g. cheating, theft, dowry, murder")

        if st.button("Search", use_container_width=True) and typed.strip():
            st.session_state["crime_matches"] = find_sections_by_crime_name(typed)

        matches = st.session_state.get("crime_matches")

        if matches is not None:
            if len(matches) == 0:
                st.info("We couldn't match that to a known offence. That's fine — we'll say so honestly in your report rather than guess.")
                if st.button("Continue without a match", use_container_width=True):
                    answer = []
            elif len(matches) == 1:
                sec = matches[0]
                st.success(f"Matched: {BNS_SECTION_DATA[sec]['offence']} (Section {sec})")
                if st.button("Confirm and continue", use_container_width=True):
                    answer = matches
            else:
                st.write("A few offences matched — please pick the one that fits best:")
                for sec in matches:
                    label = f"{BNS_SECTION_DATA[sec]['offence']} (Section {sec})"
                    if st.button(label, use_container_width=True, key=f"match_{sec}"):
                        answer = [sec]

        st.caption("If we don't recognize the exact offence, we'll say so honestly rather than guess.")

    if answer is not None:
        st.session_state["interview_answers"][q["key"]] = None if answer == "SKIPPED" else answer
        st.session_state["crime_matches"] = None
        st.session_state["interview_step"] += 1
        st.rerun()


def build_fields_from_interview(answers):
    """Translate plain-language interview answers into the exact schema
    run_arrest_compliance_checks already expects — reusing it unchanged."""
    def yn(v):
        return {True: True, False: False, "unclear": "unclear"}.get(v, "unclear")

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


def show_interview_results():
    fields = build_fields_from_interview(st.session_state["interview_answers"])
    compliance_result = run_arrest_compliance_checks(fields)  # same function, zero new legal logic

    full_analysis = {
        "classification": {
            "document_type": "Police & Criminal Process",
            "sub_type": "Arrest — reported via guided interview (no document)",
            "reasoning": "Built from answers you gave, since no document was available."
        },
        "missing_info": {
            "missing_or_unclear": [],
            "completeness_assessment": "Based on interview answers only — not a document review."
        },
        "compliance": compliance_result,
        "checklist": get_document_checklist("Police & Criminal Process"),
        "urgency": {"urgency_level": "Cannot Determine", "deadline_message": "N/A for interview mode", "days_remaining": None},
        "extracted_fields": fields
    }

    st.subheader("Compliance Check")
    st.json(compliance_result)

    # ---- Default-bail follow-up, same pattern as the document flow ----
    default_bail_check = next(
        (c for c in compliance_result.get("compliance_checks", []) if "Default bail" in c["requirement"]),
        None
    )
    if default_bail_check and default_bail_check["status"] in ("Cannot Determine", "May be Non-Compliant"):
        st.subheader("One More Question")
        st.write("We couldn't fully resolve the default-bail deadline from your answers.")
        chargesheet_answer = st.radio("Has a chargesheet been filed in this case?", ["Not yet / Don't know", "Yes"])
        if chargesheet_answer == "Yes":
            user_cs_date = st.date_input("Chargesheet filing date")
            updated_check = check_default_bail(fields, user_chargesheet_date=user_cs_date.strftime("%d-%m-%Y"))
            st.write("Updated result:")
            st.json(updated_check)

    if st.button("Generate Compliance Brief"):
        pdf_path = generate_compliance_brief(full_analysis, output_path="interview_brief.pdf")
        with open(pdf_path, "rb") as f:
            st.session_state["interview_brief_bytes"] = f.read()

    if "interview_brief_bytes" in st.session_state:
        st.download_button(
            "Download Compliance Brief (PDF)",
            data=st.session_state["interview_brief_bytes"],
            file_name="compliance_brief.pdf",
            mime="application/pdf"
        )

    if st.button("Start over"):
        st.session_state["interview_step"] = 0
        st.session_state["interview_answers"] = {}
        st.session_state.pop("interview_brief_bytes", None)
        st.rerun()


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

            st.subheader("Classification")
            st.json(result["classification"])

            st.subheader("Missing Information")
            st.json(result["missing_info"])

            st.subheader("Document Checklist")
            st.json(result["checklist"])

            st.subheader("Compliance Check")
            st.json(result["compliance"])

            st.subheader("Urgency & Action Plan")
            st.json(result["urgency"])

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
# MODE ROUTER
# =============================================================
if mode == "I have a document to upload":
    run_document_flow()
else:
    run_interview()