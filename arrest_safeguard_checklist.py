"""
arrest_safeguard_checklist.py

The "no papers" companion to recourse_upload.py's document check.

recourse_upload.py runs the deterministic compliance engine
(main.check_*) against an uploaded arrest memo / FIR / remand order.
Most families do not have that document -- police often do not hand it
over, which is the whole point of the Prabir Purkayastha / Vihaan Kumar
line of cases. This module does the same job from a fixed set of plain
yes/no questions, one per safeguard.

There is NO LLM here and NO free-text parsing. The person's answer to
"were you produced before a magistrate within 24 hours?" IS the finding
-- there is nothing to infer. Each safeguard's governing section, its
Supreme Court authority, and the wording of a "not followed" finding are
taken from the corresponding check_* function in main.py, so the legal
substance is identical to the document path; only the input route
differs (a human toggle instead of document extraction).

evaluate() is pure: dict in, dict out, no Streamlit, no I/O.
"""

# ---- answer codes (what the UI stores per question) -----------------------
YES = "yes"
NO = "no"
UNSURE = "unsure"
NOT_A_WOMAN = "not_a_woman"
OVER_7_YEARS = "over_7_years"

# ---- verdict buckets (match recourse_app.py's .r-verdict CSS classes) -----
#   ok   -> green   "Followed"
#   bad  -> red     "Not followed"
#   warn -> amber   "Needs to be on the record"
#   na   -> grey    "Does not apply here"
_BUCKET_LABEL = {
    "ok": "Followed",
    "bad": "Not followed",
    "warn": "Get this on the record",
    "na": "Does not apply here",
}


# Each safeguard: the question, its section + case, the fixed options the
# UI should offer (code -> button label), and the finding text for every
# code. `default_bucket` covers any code not in `findings` (defensive).
SAFEGUARDS = [
    {
        "id": "written_grounds",
        "question": "Were the grounds of the arrest given in writing — the actual "
                    "reasons, not just the name of the offence or a section number?",
        "section": "Section 47, BNSS",
        "case": "Prabir Purkayastha v State (NCT of Delhi); Vihaan Kumar v State of Haryana",
        "options": [(YES, "Yes, in writing"),
                    (NO, "No / only told the offence"),
                    (UNSURE, "Not sure")],
        "findings": {
            YES: ("ok", "Written grounds of arrest were furnished. This safeguard was met."),
            NO: ("bad", "The Supreme Court in Vihaan Kumar held that failing to give the "
                        "grounds of arrest in writing violates Article 22(1), can make the "
                        "arrest itself illegal, and is a ground for bail — and the burden is "
                        "on the police to prove the grounds were furnished."),
            UNSURE: ("warn", "The record must show that written grounds were furnished. Ask "
                             "the police or the court for the arrest memo and the "
                             "grounds-of-arrest document."),
        },
    },
    {
        "id": "notice_before_arrest",
        "question": "If the offence carries up to 7 years' jail — was a written notice to "
                    "appear served first, instead of arresting the person straight away?",
        "section": "Section 35(3), BNSS",
        "case": "Arnesh Kumar v State of Bihar; Satender Kumar Antil v CBI",
        "options": [(YES, "Yes, a notice came first"),
                    (NO, "No, arrested directly"),
                    (OVER_7_YEARS, "The offence is above 7 years"),
                    (UNSURE, "Not sure")],
        "findings": {
            YES: ("ok", "A notice to appear was served before arrest. This is what "
                        "Section 35(3) requires for offences up to 7 years."),
            NO: ("bad", "For an offence punishable with up to 7 years, Arnesh Kumar and "
                        "Satender Kumar Antil hold that a notice to appear is the rule and "
                        "arrest the exception — the officer must record in writing why the "
                        "arrest was necessary. A direct arrest without that is a defect."),
            OVER_7_YEARS: ("na", "The notice-first rule under Section 35(3) is for offences "
                                 "up to 7 years. It does not apply here — but written "
                                 "grounds, the D.K. Basu safeguards and 24-hour production "
                                 "still apply in full."),
            UNSURE: ("warn", "Check the maximum punishment for the exact section(s) charged. "
                             "If it is 7 years or less, a notice to appear should ordinarily "
                             "have come first."),
        },
    },
    {
        "id": "family_informed",
        "question": "Was a family member or friend told about the arrest and where the "
                    "person was being held?",
        "section": "Section 48, BNSS",
        "case": "D.K. Basu v State of West Bengal",
        "options": [(YES, "Yes"), (NO, "No"), (UNSURE, "Not sure")],
        "findings": {
            YES: ("ok", "A relative or friend was informed of the arrest and the place of "
                        "custody, as D.K. Basu and Section 48 require."),
            NO: ("bad", "D.K. Basu requires that a relative or friend be told of the arrest "
                        "and where the person is held, as soon as practicable. Not doing so "
                        "is a recognised violation."),
            UNSURE: ("warn", "Ask which relative or friend was informed and when — the "
                             "police station must keep an entry of this."),
        },
    },
    {
        "id": "memo_witnessed",
        "question": "Was the arrest memo signed by a witness — a family member, or a "
                    "respectable person from the locality?",
        "section": "Section 47 / 48, BNSS",
        "case": "D.K. Basu v State of West Bengal",
        "options": [(YES, "Yes"), (NO, "No"), (UNSURE, "Not sure")],
        "findings": {
            YES: ("ok", "The arrest memo was attested by a witness, as D.K. Basu requires."),
            NO: ("bad", "D.K. Basu requires the arrest memo to be attested by at least one "
                        "witness — a family member or a respectable local person — and "
                        "countersigned by the arrestee. An unwitnessed memo is a defect."),
            UNSURE: ("warn", "Ask for a copy of the arrest memo and check whose signature it "
                             "carries as a witness."),
        },
    },
    {
        "id": "medical_exam",
        "question": "Was a medical examination of the arrested person done at the time of "
                    "arrest and recorded?",
        "section": "Section 53 / 55, BNSS",
        "case": "D.K. Basu v State of West Bengal",
        "options": [(YES, "Yes"), (NO, "No"), (UNSURE, "Not sure")],
        "findings": {
            YES: ("ok", "A medical examination at the time of arrest was recorded, as "
                        "D.K. Basu requires."),
            NO: ("bad", "D.K. Basu requires that the arrested person be medically examined "
                        "at the time of arrest, with any injuries recorded in an inspection "
                        "memo. Skipping this is a recognised violation and matters most "
                        "where custodial ill-treatment is alleged."),
            UNSURE: ("warn", "Ask for the medical examination / inspection memo from the "
                             "time of arrest."),
        },
    },
    {
        "id": "produced_24h",
        "question": "Was the person produced before a magistrate within 24 hours of the "
                    "arrest (not counting the time needed to travel to the court)?",
        "section": "Section 58, BNSS / Article 22(2)",
        "case": "D.K. Basu v State of West Bengal; Arnesh Kumar v State of Bihar",
        "options": [(YES, "Yes, within 24 hours"),
                    (NO, "No, it took longer"),
                    (UNSURE, "Not sure")],
        "findings": {
            YES: ("ok", "The person was produced before a magistrate within 24 hours — "
                        "the constitutional limit under Article 22(2) and Section 58."),
            NO: ("bad", "Article 22(2) and Section 58 require production before a magistrate "
                        "within 24 hours of arrest, excluding travel time. Exceeding this "
                        "makes the detention unlawful for that period."),
            UNSURE: ("warn", "Check the exact arrest time and the first production date on "
                             "the remand order / order sheet."),
        },
    },
    {
        "id": "night_arrest_woman",
        "question": "If the person arrested is a woman — was she arrested between sunset "
                    "and sunrise?",
        "section": "Section 43(5), BNSS",
        "case": "Sheela Barse v State of Maharashtra",
        "options": [(NO, "No, during the day"),
                    (YES, "Yes, after dark"),
                    (NOT_A_WOMAN, "The person is not a woman"),
                    (UNSURE, "Not sure")],
        "findings": {
            NO: ("ok", "The arrest was during daytime hours, so the night-arrest "
                       "restriction is not engaged."),
            YES: ("bad", "As a rule a woman is not to be arrested between sunset and "
                         "sunrise; where exceptional circumstances require it, a woman "
                         "police officer must first obtain the written permission of a "
                         "Judicial Magistrate. An after-dark arrest without that permission "
                         "is a defect."),
            NOT_A_WOMAN: ("na", "This safeguard is specific to the arrest of a woman."),
            UNSURE: ("warn", "Check the exact time of arrest recorded in the memo."),
        },
    },
    {
        "id": "female_officer",
        "question": "If the person arrested is a woman — was a woman police officer "
                    "involved in the arrest and custody?",
        "section": "Section 43(1) proviso, BNSS",
        "case": "Sheela Barse v State of Maharashtra",
        "options": [(YES, "Yes"),
                    (NO, "No"),
                    (NOT_A_WOMAN, "The person is not a woman"),
                    (UNSURE, "Not sure")],
        "findings": {
            YES: ("ok", "A woman police officer was involved, as required for the arrest "
                        "and custody of a woman."),
            NO: ("bad", "Sheela Barse requires a woman police officer for the custody, "
                        "interrogation and search of a woman arrestee. Absence of one is a "
                        "recognised defect."),
            NOT_A_WOMAN: ("na", "This safeguard is specific to the arrest of a woman."),
            UNSURE: ("warn", "Ask whether a woman officer was present at the arrest and "
                             "during custody."),
        },
    },
    {
        "id": "default_bail",
        "question": "Has the person been in jail more than 60 days (or 90 days for the "
                    "most serious offences) without the police filing a chargesheet?",
        "section": "Section 187(3), BNSS",
        "case": "M. Ravindran v Intelligence Officer; Rakesh Kumar Paul v State of Assam",
        "options": [(NO, "No / a chargesheet was filed in time"),
                    (YES, "Yes — past the limit, still no chargesheet"),
                    (UNSURE, "Not sure of the dates")],
        "findings": {
            NO: ("ok", "If the chargesheet was filed within the 60 or 90-day limit, the "
                       "default-bail right under Section 187 was not triggered."),
            YES: ("bad", "If the investigation is not completed and no chargesheet is filed "
                         "within 60 days (90 for offences carrying 10 years or more), the "
                         "accused acquires a right to be released on default bail under "
                         "Section 187. M. Ravindran holds this right is indefeasible once "
                         "applied for; Rakesh Kumar Paul holds even an oral request is "
                         "enough and the court must inform the accused of it. This is "
                         "separate from any bail rejection on merits."),
            UNSURE: ("warn", "Pin down three dates: the first remand date, the date any "
                             "chargesheet was actually filed, and whether a bail request "
                             "(even oral) was pending between day 60/90 and that filing."),
        },
    },
]

_SAFEGUARDS_BY_ID = {s["id"]: s for s in SAFEGUARDS}


def evaluate(answers: dict) -> dict:
    """answers: {safeguard_id: answer_code}. Missing / unknown ids are
    skipped. Returns:

        {
          "rows": [ {id, question, section, case, bucket, label, finding}, ... ],
          "summary": {
              "violated": int,      # confirmed "not followed"
              "to_confirm": int,    # needs the record
              "meter": str,         # 🟩🟨🟧🟥 style
              "band": "green"|"amber"|"orange"|"red",
              "label": str,         # short banner, e.g. "Critical — rights likely violated"
              "headline": str,      # one-sentence explanation
          },
        }
    """
    rows = []
    for sg in SAFEGUARDS:
        code = (answers or {}).get(sg["id"])
        if code is None:
            continue
        bucket, finding = sg["findings"].get(code, ("warn", "Not answered."))
        rows.append({
            "id": sg["id"],
            "question": sg["question"],
            "section": sg["section"],
            "case": sg["case"],
            "bucket": bucket,
            "label": _BUCKET_LABEL.get(bucket, "—"),
            "finding": finding,
        })

    violated = sum(1 for r in rows if r["bucket"] == "bad")
    to_confirm = sum(1 for r in rows if r["bucket"] == "warn")

    if violated >= 5:
        band, meter = "red", "🟩🟨🟧🟥"
        label = "Critical — rights likely violated"
        headline = (f"{violated} safeguards were not followed. On this account the arrest "
                    f"and continued custody look legally vulnerable — put this before a "
                    f"lawyer or the Magistrate now.")
    elif violated >= 3:
        band, meter = "orange", "🟩🟨🟧⬜"
        label = "Serious — several safeguards not followed"
        headline = (f"{violated} safeguards were not followed. Each is a recognised ground "
                    f"to raise before the Magistrate and in a bail application.")
    elif violated == 2:
        band, meter = "amber", "🟩🟨⬜⬜"
        label = "Concerns — 2 safeguards not followed"
        headline = ("2 safeguards were not followed. Each is a recognised ground to "
                    "raise before the Magistrate and in a bail application.")
    elif violated == 1:
        band, meter = "amber", "🟩🟨⬜⬜"
        label = "Concern — 1 safeguard not followed"
        headline = ("1 safeguard was not followed. It is a recognised ground to raise "
                    "before the Magistrate and in a bail application.")
    elif to_confirm:
        band, meter = "amber", "🟩🟨⬜⬜"
        label = f"{to_confirm} point(s) to confirm from the record"
        headline = (f"Nothing here is clearly broken, but {to_confirm} point(s) depend on "
                    f"what the record shows. The items marked below tell you what to ask for.")
    else:
        band, meter = "green", "🟩⬜⬜⬜"
        label = "No safeguard clearly broken"
        headline = ("On the answers given, none of these safeguards was clearly broken. "
                    "This is not a ruling on the case — only a check of the procedure.")

    return {
        "rows": rows,
        "summary": {
            "violated": violated,
            "to_confirm": to_confirm,
            "meter": meter,
            "band": band,
            "label": label,
            "headline": headline,
        },
    }
