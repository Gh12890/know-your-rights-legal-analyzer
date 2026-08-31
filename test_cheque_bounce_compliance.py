
"""
test_cheque_bounce_compliance.py

Regression suite for main.py's cheque-bounce (Section 138 NI Act)
compliance and informational functions, covering the 6 real scenarios
manually verified on 2026-08-30, plus explicit regression coverage for
the two self-corrections made during today's sourcing work.

Run with: python test_cheque_bounce_compliance.py
No API cost -- pure Python, no LLM/embedding calls.
"""

import sys

from main import (
    run_compliance_checks,
    explain_debt_presumption_status,
    compute_settlement_cost_incentive,
)

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


def get_check(result, requirement_substring):
    for c in result["compliance_checks"]:
        if requirement_substring.lower() in c["requirement"].lower():
            return c
    return None


print("\n" + "=" * 70)
print("SCENARIO 1: Clean, fully compliant case")
print("=" * 70)
fields = {
    "return_memo_date": "01-01-2026", "notice_date": "15-01-2026",
    "cheque_face_value": 100000, "demand_principal_amount": 100000,
    "payment_window_days_granted": 15, "interest_bundled_in_principal_sentence": False,
    "cheque_was_blank_when_signed": False,
    "cheque_presentation_bank_location": "Mumbai", "complaint_filed_location": "Mumbai",
    "case_stage": "pre_trial",
}
result = run_compliance_checks(fields)
check(
    all(c["status"] == "Compliant" for c in result["compliance_checks"]),
    "All four checks are Compliant"
)
presumption = explain_debt_presumption_status(fields)
check(
    "blank cheque" not in presumption["explanation"].lower(),
    "Presumption explanation does NOT mention blank cheque when fully filled in"
)
settlement = compute_settlement_cost_incentive(fields)
check(
    settlement["pathway"] == "low_cost_compounding_available",
    "Pre-trial stage -> low-cost settlement pathway"
)


print("\n" + "=" * 70)
print("SCENARIO 2: Kaveri Plastics pattern (amount mismatch)")
print("=" * 70)
fields = {
    "return_memo_date": "01-01-2026", "notice_date": "20-01-2026",
    "cheque_face_value": 405000, "demand_principal_amount": 450000,
    "payment_window_days_granted": 15, "interest_bundled_in_principal_sentence": False,
    "cheque_was_blank_when_signed": False,
    "cheque_presentation_bank_location": "Chennai", "complaint_filed_location": "Chennai",
    "case_stage": "pre_trial",
}
result = run_compliance_checks(fields)
check(
    get_check(result, "Demand specifically states")["status"] == "Non-Compliant",
    "Amount mismatch -> Non-Compliant"
)
check(
    "Kaveri Plastics" in get_check(result, "Demand specifically states")["explanation"],
    "Explanation cites Kaveri Plastics by name"
)


print("\n" + "=" * 70)
print("SCENARIO 3: Interest bundled but amount matches (REGRESSION TEST)")
print("=" * 70)
fields = {
    "return_memo_date": "01-01-2026", "notice_date": "10-01-2026",
    "cheque_face_value": 50000, "demand_principal_amount": 50000,
    "payment_window_days_granted": 15, "interest_bundled_in_principal_sentence": True,
    "cheque_was_blank_when_signed": False,
    "cheque_presentation_bank_location": "Delhi", "complaint_filed_location": "Delhi",
    "case_stage": "pre_trial",
}
result = run_compliance_checks(fields)
check(
    get_check(result, "Demand specifically states")["status"] == "Compliant",
    "Interest bundled but amount matches and is severable -> Compliant "
    "(the core regression this correction fixed)"
)


print("\n" + "=" * 70)
print("SCENARIO 4: Bir Singh pattern (blank cheque)")
print("=" * 70)
fields = {
    "return_memo_date": "01-02-2026", "notice_date": "20-02-2026",
    "cheque_face_value": 200000, "demand_principal_amount": 200000,
    "payment_window_days_granted": 15, "interest_bundled_in_principal_sentence": False,
    "cheque_was_blank_when_signed": True,
    "cheque_presentation_bank_location": "Pune", "complaint_filed_location": "Pune",
    "case_stage": "convicted_at_trial_court",
}
presumption = explain_debt_presumption_status(fields)
check(
    "blank cheque" in presumption["explanation"].lower(),
    "Presumption explanation mentions blank cheque when applicable"
)
check(
    "Bir Singh" in presumption["explanation"],
    "Explanation cites Bir Singh v Mukesh Kumar by name"
)
check(
    "friendly loan" not in presumption["explanation"].lower()
    and "informal" not in presumption["explanation"].lower(),
    "Explanation does NOT claim informal/friendly loans defeat the presumption "
    "(REGRESSION TEST: an earlier draft incorrectly attributed this to Bir Singh; "
    "confirmed via direct re-check no such holding exists -- must never silently return)"
)
settlement = compute_settlement_cost_incentive(fields)
check(
    settlement["pathway"] == "escalated_cost_compounding",
    "Convicted at trial court -> escalated-cost pathway"
)
check(
    "10%" in settlement["message"],
    "Post-conviction message references the 10% cost band"
)


print("\n" + "=" * 70)
print("SCENARIO 5: Jurisdiction defect (Prakash Chimanlal Sheth pattern)")
print("=" * 70)
fields = {
    "return_memo_date": "01-01-2026", "notice_date": "10-01-2026",
    "cheque_face_value": 75000, "demand_principal_amount": 75000,
    "payment_window_days_granted": 20, "interest_bundled_in_principal_sentence": False,
    "cheque_was_blank_when_signed": False,
    "cheque_presentation_bank_location": "Ahmedabad", "complaint_filed_location": "Mumbai",
    "case_stage": "unclear",
}
result = run_compliance_checks(fields)
check(
    get_check(result, "Complaint filed where cheque was presented")["status"] == "Non-Compliant",
    "Presentation/filing locations differ -> jurisdiction check is Non-Compliant"
)
check(
    "Prakash Chimanlal Sheth" in get_check(result, "Complaint filed where cheque was presented")["explanation"],
    "Explanation cites Prakash Chimanlal Sheth by name"
)
settlement = compute_settlement_cost_incentive(fields)
check(
    settlement["pathway"] == "unknown",
    "Unclear case stage -> settlement pathway is honestly 'unknown'"
)


print("\n" + "=" * 70)
print("SCENARIO 6: 30-day notice window breach")
print("=" * 70)
fields = {
    "return_memo_date": "01-01-2026", "notice_date": "15-02-2026",
    "cheque_face_value": 60000, "demand_principal_amount": 60000,
    "payment_window_days_granted": 15, "interest_bundled_in_principal_sentence": False,
    "cheque_was_blank_when_signed": False,
    "cheque_presentation_bank_location": "Kolkata", "complaint_filed_location": "Kolkata",
    "case_stage": "pre_trial",
}
result = run_compliance_checks(fields)
check(
    get_check(result, "Notice sent within 30 days")["status"] == "Non-Compliant",
    "45-day gap -> 30-day check is Non-Compliant"
)
check(
    get_check(result, "Demand specifically states")["status"] == "Compliant",
    "30-day defect does not affect the independent amount-match check"
)
check(
    get_check(result, "Complaint filed where cheque was presented")["status"] == "Compliant",
    "30-day defect does not affect the independent jurisdiction check"
)


print("\n" + "=" * 70)
print("CHECK: check_enforceable_debt is genuinely retired")
print("=" * 70)
try:
    from main import check_enforceable_debt
    check(False, "check_enforceable_debt still importable -- should be fully retired")
except ImportError:
    check(True, "check_enforceable_debt is correctly no longer importable (retired)")


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
    sys.exit(0)
    
