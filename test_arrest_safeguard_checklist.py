"""
test_arrest_safeguard_checklist.py

Unit tests for the fixed no-document arrest-safeguard checklist added
2026-09-08. Pure logic -- no Streamlit, no LLM, no API calls.

Run with: python test_arrest_safeguard_checklist.py
"""

import sys

from arrest_safeguard_checklist import (
    evaluate, SAFEGUARDS, YES, NO, UNSURE, NOT_A_WOMAN, OVER_7_YEARS,
)

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


# ---- structure ----
check(len(SAFEGUARDS) >= 7, "at least 7 safeguards defined")
for sg in SAFEGUARDS:
    for k in ("id", "question", "section", "case", "options", "findings"):
        check(k in sg and sg[k], f"{sg.get('id','?')}: has non-empty {k}")
    codes = {c for c, _ in sg["options"]}
    check(codes <= set(sg["findings"]),
          f"{sg['id']}: every option code has a finding")
    for _b, (bucket, text) in sg["findings"].items():
        check(bucket in ("ok", "bad", "warn", "na") and text,
              f"{sg['id']}: finding bucket valid + text present")

ids = {s["id"] for s in SAFEGUARDS}
check("written_grounds" in ids and "produced_24h" in ids and "default_bail" in ids,
      "the load-bearing safeguards are present")


# ---- empty / partial input ----
r = evaluate({})
check(r["rows"] == [] and r["summary"]["band"] == "green",
      "no answers -> no rows, green (nothing asserted)")

r = evaluate({"unknown_id": YES})
check(r["rows"] == [], "unknown safeguard id is ignored, never raises")


# ---- all-clear ----
allgood = {
    "written_grounds": YES, "notice_before_arrest": YES, "family_informed": YES,
    "memo_witnessed": YES, "medical_exam": YES, "produced_24h": YES,
    "night_arrest_woman": NOT_A_WOMAN, "female_officer": NOT_A_WOMAN,
    "default_bail": NO,
}
r = evaluate(allgood)
check(len(r["rows"]) == 9, "all nine answered -> nine rows")
check(r["summary"]["violated"] == 0 and r["summary"]["band"] == "green",
      "all-compliant answers -> 0 violations, green")
check(all(row["bucket"] in ("ok", "na") for row in r["rows"]),
      "all-compliant answers -> only ok/na rows")


# ---- one confirmed violation ----
r = evaluate({**allgood, "written_grounds": NO})
check(r["summary"]["violated"] == 1 and r["summary"]["band"] == "amber",
      "one 'No' -> 1 violation, amber")
wg = next(row for row in r["rows"] if row["id"] == "written_grounds")
check(wg["bucket"] == "bad" and "Vihaan Kumar" in wg["finding"],
      "written_grounds=No -> bad + names Vihaan Kumar")


# ---- three violations -> orange "Serious" ----
r = evaluate({**allgood, "written_grounds": NO, "family_informed": NO, "produced_24h": NO})
check(r["summary"]["violated"] == 3 and r["summary"]["band"] == "orange",
      "three 'No' -> orange band")
check("Serious" in r["summary"]["label"], "three 'No' -> label says 'Serious'")

# ---- five violations -> red "Critical" ----
r = evaluate({**allgood, "written_grounds": NO, "family_informed": NO, "produced_24h": NO,
              "memo_witnessed": NO, "medical_exam": NO})
check(r["summary"]["violated"] == 5 and r["summary"]["band"] == "red",
      "five 'No' -> red band")
check("Critical" in r["summary"]["label"], "five 'No' -> label says 'Critical'")
check("🟥" in r["summary"]["meter"], "red band -> meter includes 🟥")

# ---- every summary carries a non-empty label ----
for n in (0, 1, 2, 3, 5):
    ans = {}
    keys = ["written_grounds", "family_informed", "produced_24h", "memo_witnessed", "medical_exam"]
    for i in range(n):
        ans[keys[i]] = NO
    check(bool(evaluate(ans)["summary"].get("label")),
          f"{n} violations -> summary has a label")


# ---- 'not sure' surfaces as a to-confirm, never a violation ----
r = evaluate({"written_grounds": UNSURE, "produced_24h": UNSURE})
check(r["summary"]["violated"] == 0 and r["summary"]["to_confirm"] == 2,
      "two 'Not sure' -> 0 violations, 2 to-confirm")
check(r["summary"]["band"] == "amber",
      "only 'Not sure' answers -> amber (nothing proven, points open)")
check(all(row["bucket"] == "warn" for row in r["rows"]),
      "'Not sure' -> warn bucket")


# ---- woman-specific safeguards ----
r = evaluate({"night_arrest_woman": NOT_A_WOMAN, "female_officer": NOT_A_WOMAN})
check(all(row["bucket"] == "na" for row in r["rows"]),
      "'not a woman' -> both woman-safeguards are N/A")
check(r["summary"]["violated"] == 0, "N/A rows never count as violations")

r = evaluate({"night_arrest_woman": YES})
row = r["rows"][0]
check(row["bucket"] == "bad" and "sunset" in row["finding"].lower(),
      "woman arrested after dark -> bad, mentions sunset/sunrise rule")


# ---- notice-before-arrest: 'over 7 years' is N/A, not a violation ----
r = evaluate({"notice_before_arrest": OVER_7_YEARS})
check(r["rows"][0]["bucket"] == "na" and r["summary"]["violated"] == 0,
      "notice_before_arrest='offence above 7 years' -> N/A, not a violation")

r = evaluate({"notice_before_arrest": NO})
check(r["rows"][0]["bucket"] == "bad" and "Arnesh Kumar" in r["rows"][0]["finding"],
      "arrested directly for a <=7yr offence -> bad + names Arnesh Kumar")


# ---- default bail: YES (past the limit) is the bad answer ----
r = evaluate({"default_bail": YES})
check(r["rows"][0]["bucket"] == "bad" and "M. Ravindran" in r["rows"][0]["finding"],
      "default_bail=Yes (past limit) -> bad + names M. Ravindran")
r = evaluate({"default_bail": NO})
check(r["rows"][0]["bucket"] == "ok", "default_bail=No -> ok")


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
sys.exit(0)
