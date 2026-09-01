
"""
test_chat_domain_handoff.py

Regression suite for the chat-to-domain-flow handoff, 2026-09-01.

BACKGROUND: the "I just want to ask something in my own words" chat
feature used to dead-end on bank-freeze/cheque-bounce questions with a
generic "go upload a document" message -- even though a BETTER, no-
document-needed option (the dedicated free-text interview flows in
freeze_interview_flow.py / cheque_bounce_interview_flow.py, which give
a real Compliant/Non-Compliant verdict, not just an explanation) was
already sitting in the same mode-selector menu. This suite covers the
one-click handoff that now carries the user's already-typed question
straight into the right flow instead.

REAL BUG CAUGHT WHILE BUILDING THIS (kept here as the regression it
is): calling the handoff logic directly from the normal script body
raises StreamlitAPIException ("st.session_state.mode cannot be
modified after the widget with key 'mode' is instantiated"), since the
mode radio (key="mode") has already rendered earlier in the same
script pass. Must be an on_click callback. A SECOND bug caught the
same way: the callback originally re-appended the chat reply into
chat_history, which run_chat_flow() had already appended on the same
pass that rendered the button -- producing a duplicate identical
assistant turn every time the button was clicked.

COST NOTE: unlike this project's other test_*.py suites, the AppTest
cases below make REAL LLM calls (classify_scope, and process_turn's
own extraction) -- there is no way to test the actual handoff wiring
without exercising the real chat pipeline. Kept deliberately small (2
end-to-end cases) to bound cost. The classify_scope unit checks below
also cost real API calls, one per question.

Run with: python test_chat_domain_handoff.py
"""

import sys

from chat_assistant import classify_scope, answer_question
from streamlit.testing.v1 import AppTest

APP_PATH = r"C:\Users\reeti\OneDrive\Documents\My Project\app.py"

FAILURES = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        FAILURES.append(description)


# ---- classify_scope: redirect_domain is populated correctly ----

category, reasoning, redirect_domain = classify_scope(
    "my bank account got frozen by the police and nobody told me why"
)
check(category == "covered_elsewhere_in_tool", "freeze question classified as covered_elsewhere_in_tool")
check(redirect_domain == "freeze", "freeze question's redirect_domain is 'freeze'")

category, reasoning, redirect_domain = classify_scope(
    "I got a legal notice saying my cheque bounced, what happens now"
)
check(category == "covered_elsewhere_in_tool", "cheque-bounce question classified as covered_elsewhere_in_tool")
check(redirect_domain == "cheque_bounce", "cheque-bounce question's redirect_domain is 'cheque_bounce'")

category, reasoning, redirect_domain = classify_scope(
    "police came to my house and arrested me directly saying that i stole a goat"
)
check(category == "in_scope", "an in-scope arrest question is still classified as in_scope")
check(redirect_domain is None, "redirect_domain is None for an in_scope question, never guessed")

# ---- answer_question: redirect_domain propagates into the returned dict ----

result = answer_question("my bank account got frozen by the police and nobody told me why")
check(result["state"] == "covered_elsewhere_in_tool", "answer_question returns covered_elsewhere_in_tool for a freeze question")
check(result.get("redirect_domain") == "freeze", "answer_question propagates redirect_domain='freeze'")


# ---- End-to-end AppTest: the actual button click switches mode and seeds the flow ----

def run_handoff_case(question, history_key):
    at = AppTest.from_file(APP_PATH)
    at.session_state["mode"] = "I just want to ask something in my own words"
    at.run(timeout=90)
    at.chat_input[0].set_value(question).run(timeout=90)
    if at.exception:
        return None, [str(e) for e in at.exception]

    if len(at.button) != 1:
        return None, [f"expected exactly 1 handoff button, found {len(at.button)}"]

    at.button[0].click().run(timeout=90)
    if at.exception:
        return None, [str(e) for e in at.exception]

    return {
        "mode": at.session_state["mode"],
        "domain_history": at.session_state[history_key],
        "chat_history": at.session_state["chat_history"],
    }, []


result, errors = run_handoff_case(
    "my bank account got frozen by the police and nobody told me why",
    "freeze_chat_history",
)
check(not errors, f"freeze handoff runs with no exceptions ({errors})")
if result:
    check("bank account was frozen" in result["mode"], "freeze handoff switches mode to the freeze flow")
    check(len(result["domain_history"]) == 2, "freeze flow history has exactly 2 turns (seeded question + real follow-up)")
    check(
        result["domain_history"][0]["content"] == "my bank account got frozen by the police and nobody told me why",
        "freeze flow's first turn is the user's original, verbatim question",
    )
    check(len(result["chat_history"]) == 2, "chat_history has exactly 2 turns, NOT duplicated by the handoff callback")

result, errors = run_handoff_case(
    "I got a legal notice saying my cheque bounced, what happens now",
    "cheque_chat_history",
)
check(not errors, f"cheque-bounce handoff runs with no exceptions ({errors})")
if result:
    check("bounced cheque situation" in result["mode"], "cheque-bounce handoff switches mode to the cheque-bounce flow")
    check(len(result["domain_history"]) == 2, "cheque flow history has exactly 2 turns (seeded question + real follow-up)")
    check(
        result["domain_history"][0]["content"] == "I got a legal notice saying my cheque bounced, what happens now",
        "cheque flow's first turn is the user's original, verbatim question",
    )
    check(len(result["chat_history"]) == 2, "chat_history has exactly 2 turns, NOT duplicated by the handoff callback")


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
    sys.exit(0)
