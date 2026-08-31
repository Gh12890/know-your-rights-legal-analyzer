
"""
test_freeze_compliance.py

Regression suite for main.py's bank-account-freezing compliance
functions, covering the 6 real scenarios manually verified via
test_freeze_scenarios.py and the live Streamlit UI on 2026-08-30 --
NOT hypothetical edge cases.

Every scenario here corresponds to a real fact pattern from a sourced,
verified judgment (Malabar Gold, Neelkanth Pharma Logistics, Tapas D.
Neogy) or a genuine edge case already confirmed correct by hand. This
file exists so the same correctness is caught automatically going
forward, not re-verified by hand every time this code is touched.

Run with: python test_freeze_compliance.py
No API cost -- pure Python, no LLM/embedding calls.
"""

import sys

from main import run_freeze_compliance_checks

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
print("SCENARIO 1: Malabar Gold pattern (Section 106 used to freeze)")
print("=" * 70)
result = run_freeze_compliance_checks({
    "section_invoked": "106 BNSS", "scope": "entire account", "specific_amount_stated": None,
    "magistrate_intimation_recorded": True, "account_holder_intimated": False,
    "court_order_referenced_for_107": "not applicable",
})
check(
    get_check(result, "Attachment/freeze authorized")["status"] == "Non-Compliant",
    "Section 106 used to freeze -> 107-authorization check is Non-Compliant"
)
check(
    get_check(result, "Blanket freeze")["status"] == "Non-Compliant",
    "Entire account frozen -> scope check is Non-Compliant"
)
check(
    get_check(result, "Account holder intimated")["status"] == "May be Non-Compliant",
    "Holder not intimated -> intimation check is May be Non-Compliant"
)


print("\n" + "=" * 70)
print("SCENARIO 2: Neelkanth pattern (authorized but disproportionate)")
print("=" * 70)
result = run_freeze_compliance_checks({
    "section_invoked": "107 BNSS", "scope": "entire account", "specific_amount_stated": 200,
    "court_order_referenced_for_107": True, "magistrate_intimation_recorded": True,
    "account_holder_intimated": True,
})
check(
    get_check(result, "Attachment/freeze authorized")["status"] == "Compliant",
    "Real S.107 court order exists -> authorization check is Compliant"
)
check(
    get_check(result, "Blanket freeze")["status"] == "Non-Compliant",
    "Entire account frozen despite Rs.200 disputed amount -> scope check is Non-Compliant "
    "(REGRESSION TEST: this scenario was found returning the WRONG result once during this "
    "session, traced to a stale Python module cache, not a real code defect)"
)
check(
    "200" in get_check(result, "Blanket freeze")["explanation"],
    "Scope explanation specifically references the Rs. 200 disputed amount"
)


print("\n" + "=" * 70)
print("SCENARIO 3: Clean, fully compliant freeze")
print("=" * 70)
result = run_freeze_compliance_checks({
    "section_invoked": "107 BNSS", "scope": "specific disputed amount", "specific_amount_stated": 50000,
    "court_order_referenced_for_107": True, "magistrate_intimation_recorded": True,
    "account_holder_intimated": True,
})
check(
    all(c["status"] == "Compliant" for c in result["compliance_checks"]),
    "All four checks are Compliant"
)
check(
    "compliant" in result["overall_assessment"].lower(),
    "Overall assessment reflects clean compliance"
)


print("\n" + "=" * 70)
print("SCENARIO 4: No section cited at all (bare police request)")
print("=" * 70)
result = run_freeze_compliance_checks({
    "section_invoked": "none cited", "scope": "entire account", "specific_amount_stated": None,
    "magistrate_intimation_recorded": False, "account_holder_intimated": False,
    "court_order_referenced_for_107": "not applicable",
})
check(
    get_check(result, "Attachment/freeze authorized")["status"] == "May be Non-Compliant",
    "No section cited -> authorization check is May be Non-Compliant"
)
check(
    get_check(result, "Blanket freeze")["status"] == "Non-Compliant",
    "No section cited, entire account frozen -> scope check is Non-Compliant"
)
check(
    len([c for c in result["compliance_checks"] if c["status"] in ("Non-Compliant", "May be Non-Compliant")]) >= 3,
    "Worst-case scenario correctly surfaces multiple real defects"
)


print("\n" + "=" * 70)
print("SCENARIO 5: Everything unknown (no crash on missing data)")
print("=" * 70)
try:
    result = run_freeze_compliance_checks({
        "section_invoked": None, "scope": None, "specific_amount_stated": None,
        "magistrate_intimation_recorded": None, "account_holder_intimated": None,
        "court_order_referenced_for_107": None,
    })
    check(
        all(c["status"] == "Cannot Determine" for c in result["compliance_checks"]),
        "All checks correctly return Cannot Determine on fully missing data, no crash"
    )
except Exception as e:
    check(False, f"run_freeze_compliance_checks raised an unexpected exception: {e}")


print("\n" + "=" * 70)
print("SCENARIO 6: Pre/post-freeze notice distinction")
print("=" * 70)
result = run_freeze_compliance_checks({
    "section_invoked": "107 BNSS", "scope": "specific disputed amount", "court_order_referenced_for_107": True,
    "magistrate_intimation_recorded": True, "account_holder_intimated": False,
})
check(
    get_check(result, "Blanket freeze")["status"] == "Compliant",
    "Scope is proportionate -> scope check stays Compliant even though holder wasn't intimated"
)
holder_check = get_check(result, "Account holder intimated")
check(
    holder_check["status"] == "May be Non-Compliant",
    "Holder not intimated after the fact -> May be Non-Compliant"
)
check(
    "before" in holder_check["explanation"].lower() and "does not require" in holder_check["explanation"].lower(),
    "Explanation correctly distinguishes pre-freeze notice (not required) from post-freeze "
    "intimation (the real entitlement)"
)


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
    sys.exit(0)
    
