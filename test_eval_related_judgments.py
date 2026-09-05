"""
test_eval_related_judgments.py

No-API coverage for the Lane B eval harness (eval_related_judgments.py,
Phase 6).  Keeps the harness itself from bit-rotting: the pure check
helpers, and a full run of every OFFLINE fixture case asserting the gates
and invariants land where the fixtures say they should.

Run: python test_eval_related_judgments.py
"""

import sys

import eval_related_judgments as E

FAILURES = []


def check(condition, description):
    print(f"[{'PASS' if condition else 'FAIL'}] {description}")
    if not condition:
        FAILURES.append(description)


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
_CAND = lambda title, **kw: {"triage": {"title": title}, **kw}

check(E._title(_CAND("D.K. Basu v State")) == "d.k. basu v state",
      "_title lowercases the candidate title")
check(E._title({"triage": {}}) == "" and E._title({}) == "",
      "_title is safe on a candidate with no title / no triage")

ok, detail = E._check_group(["arnesh kumar vs state of bihar", "ramesh v state"], ("arnesh kumar",))
check(ok, "_check_group matches a substring against the title list")
ok, _ = E._check_group(["ramesh v state"], ("arnesh kumar", "d.k. basu"))
check(not ok, "_check_group is False when no group member matches")

res = {"for_display": [_CAND("A v B")], "unverified_for_display": [_CAND("A v B"), _CAND("C v D")]}
titles = E._displayed_titles(res)
check(titles == ["a v b", "c v d"],
      "_displayed_titles unions both panels and dedups by judgment identity")


# ---------------------------------------------------------------------------
# every offline fixture case, through the real pipeline with mocks
# ---------------------------------------------------------------------------
cases = E._offline_cases()
check({c["id"] for c in cases} == set(E._OFF),
      "_offline_cases covers exactly the _OFF fixture set")

for case in cases:
    r = E.run_case(case, offline=True, pin=True, gloss=True)
    check("error" not in r, f"[{case['id']}] run_case did not raise")
    check(r["n_fail"] == 0,
          f"[{case['id']}] all fixture checks pass "
          f"({[n for n, ok, _ in r.get('checks', []) if not ok]})")

# spot-check the three behaviours that matter most, by id
by_id = {c["id"]: E.run_case(c, offline=True, pin=True, gloss=True)
         for c in cases}

r = by_id["off-whitelisted-dk-basu"]
check(r["show_user"] is True and r["n_for_display"] >= 1,
      "whitelisted custodial-torture case: panel shown, D.K. Basu displayed")
check(any("suresh" in (t or "").lower() for t in r["procedural_flagged"]),
      "the 'bail application is allowed' IK order is flagged procedural")
check(all("suresh" not in d["title"].lower() for d in r["displayed"]),
      "and that procedural order never reaches for_display")

r = by_id["off-not-whitelisted-property"]
check(r["show_user"] is False and r["n_for_display"] == 0 and r["n_unverified"] == 2,
      "not-whitelisted case: for_display empty, full list under unverified panel")

r = by_id["off-whitelisted-but-weak"]
check(r["status"] == "ok" and r["n_for_display"] == 0 and r["n_unverified"] >= 1,
      "whitelisted-but-weak case: panels are never BOTH empty (regression guard)")

r = by_id["off-disabled"]
check(r["status"] == "disabled" and r["n_candidates"] == 0,
      "kill switch -> status 'disabled', no work")

r = by_id["off-no-decomposition"]
check(r["status"] == "no_decomposition",
      "decomposition failure -> status 'no_decomposition'")


# ---------------------------------------------------------------------------
# the LIVE case list is well-formed (no API calls -- just shape)
# ---------------------------------------------------------------------------
ids = [c["id"] for c in E.LIVE_CASES]
check(len(ids) == len(set(ids)), "LIVE_CASES ids are unique")
check(all(c.get("question") for c in E.LIVE_CASES), "every LIVE case has a question")
check(all(c.get("notes") for c in E.LIVE_CASES), "every LIVE case has a notes/ideal-shape line")
for c in E.LIVE_CASES:
    st = c.get("expect_status", ("ok",))
    st = st if isinstance(st, tuple) else (st,)
    check(set(st) <= {"ok", "no_candidates", "no_decomposition", "disabled"},
          f"[{c['id']}] expect_status uses only real get_related_judgments statuses")

# Every expect_topics string must be a real whitelist key -- otherwise the
# check silently fails on every live run (the 'production_24_hours' vs
# 'twenty_four_hour_production' typo this guard was added to catch).
from settled_doctrine_whitelist import _WHITELIST
_real_topics = set(_WHITELIST)
for c in E.LIVE_CASES:
    for t in c.get("expect_topics", []):
        check(t in _real_topics,
              f"[{c['id']}] expect_topics {t!r} is a real settled_doctrine_whitelist key")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
