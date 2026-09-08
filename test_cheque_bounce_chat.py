"""
test_cheque_bounce_chat.py

Regression suite for the inline Section 138 (cheque-bounce) answer path
added 2026-09-08.

BACKGROUND: after the live site was swapped to the chat-only recourse_app
(which has no document-upload handoff), a cheque-bounce question hit the
scope classifier's "covered_elsewhere_in_tool" redirect and dead-ended
with a "take it to a lawyer / DLSA" panel that pointed nowhere -- even
though the shared corpus already holds the Section 138 case law
(Rangappa, Bir Singh, Prakash Chimanlal Sheth, Damodar S. Prabhu, Kaveri
Plastics). Fix: answer_question(question, inline_domains={"cheque_bounce"})
answers it inline from that corpus + cheque_bounce_doctrine_map anchors.

The arrest path must be completely untouched: find_relevant_sections's
new domain= parameter defaults to None (identical behaviour), and the
cheque cases stay in OUT_OF_CHAT_DOMAIN_CASE_NAMES for every non-cheque
call.

Most checks here are offline (doctrine map + retrieval filter). The two
end-to-end answer_question checks make real LLM calls -- kept minimal.

Run with: python test_cheque_bounce_chat.py
"""

import sys

FAILURES = []


def check(condition, description):
    print(f"[{'PASS' if condition else 'FAIL'}] {description}")
    if not condition:
        FAILURES.append(description)


# ---- offline: the doctrine map ----

from cheque_bounce_doctrine_map import get_cheque_bounce_override

CHEQUE_Q = (
    "I gave a friend a signed blank cheque as security for a hand loan of 80,000. "
    "He filled in 6,00,000 on it later and it bounced; now I have a summons from a "
    "magistrate's court three hours away for a cheque-bouncing case."
)

anchors = get_cheque_bounce_override(CHEQUE_Q)
anchor_cases = {a["case_name"] for a in anchors}
check(anchors, "cheque doctrine map returns anchors for a Section 138 question")
check("Rangappa v Sri Mohan" in anchor_cases,
      "Rangappa (s.139 presumption) is anchored")
check("Bir Singh v Mukesh Kumar" in anchor_cases,
      "Bir Singh (signed blank cheque) is anchored for a 'blank cheque' question")
check("Prakash Chimanlal Sheth v Jagruti Keyur Rajpopat" in anchor_cases,
      "Prakash Chimanlal Sheth (jurisdiction) is anchored for a 'court three hours away' question")
check("Damodar S. Prabhu v Sayed Babalal H" in anchor_cases,
      "Damodar S. Prabhu (compounding) is anchored")
check(all(a.get("text") and a.get("citation") for a in anchors),
      "every anchor resolved to real verbatim paragraph text + a citation")
check(all(a.get("source") == "curated_judgment_override" for a in anchors),
      "anchors are tagged as curated overrides")

# get_cheque_bounce_override is only ever called AFTER the scope
# classifier has said redirect_domain == "cheque_bounce", so its two
# baseline doctrines (Rangappa s.139, Damodar compounding) are
# deliberately _ALWAYS-on for that path. The KEYED doctrines must still
# be selective -- an arrest fact pattern must not pull in the blank-
# cheque or jurisdiction anchors even if this function were somehow
# reached.
arrest_q = ("police arrested my father at night in a boundary dispute and did not tell "
            "us which police station he was taken to")
_arrest_anchor_cases = {a["case_name"] for a in get_cheque_bounce_override(arrest_q)}
check("Bir Singh v Mukesh Kumar" not in _arrest_anchor_cases,
      "the blank-cheque anchor does NOT fire on an arrest fact pattern")
check("Prakash Chimanlal Sheth v Jagruti Keyur Rajpopat" not in _arrest_anchor_cases,
      "the jurisdiction anchor does NOT fire on an arrest fact pattern")

# a bare 'he gave me a cheque' mention with no dishonour is still fine to
# anchor nothing catastrophic -- the map only runs on the cheque path, so
# this is a light guard, not load-bearing
check(isinstance(get_cheque_bounce_override("what is theft under BNS"), list),
      "doctrine map never raises on an unrelated question")


# ---- offline: the retrieval-filter carve-out ----

from semantic_retrieval import OUT_OF_CHAT_DOMAIN_CASE_NAMES, CHEQUE_BOUNCE_CASE_NAMES

check(CHEQUE_BOUNCE_CASE_NAMES <= OUT_OF_CHAT_DOMAIN_CASE_NAMES,
      "every cheque case is still in the default OUT_OF_CHAT_DOMAIN exclusion set")
check("Malabar Gold and Diamond Limited v Union of India" not in CHEQUE_BOUNCE_CASE_NAMES,
      "the freeze cases are NOT in the cheque carve-out set")


# ---- end-to-end: answer_question ----

from chat_assistant import answer_question

# 1. inline enabled -> real grounded answer
r = answer_question(CHEQUE_Q, inline_domains={"cheque_bounce"})
check(r.get("state") == "single_match",
      f"cheque question with inline_domains -> single_match (got {r.get('state')!r})")
check(bool(r.get("response_text")), "inline cheque answer has response text")
check(r.get("situation_detected") is False,
      "cheque answer never sets situation_detected (no arrest-doc upload prompt)")
reply = (r.get("response_text") or "").lower()
check(
    "negotiable instruments" in reply
    or "138" in reply or "139" in reply
    or ("presumption" in reply and "cheque" in reply),
    "the answer actually discusses cheque-dishonour law (NI Act / s.138-139 / the presumption)",
)
named = {a["case_name"] for a in r.get("matches", []) if a.get("case_name")}
check("Rangappa v Sri Mohan" in named, "Rangappa reaches the answer's matches")

# 2. inline NOT enabled (old app.py behaviour) -> unchanged redirect
r2 = answer_question("I got a legal notice saying my cheque bounced, what happens now")
check(r2.get("state") == "covered_elsewhere_in_tool",
      "without inline_domains, a cheque question still redirects (app.py path unchanged)")
check(r2.get("redirect_domain") == "cheque_bounce", "redirect_domain still propagates")

# 3. freeze is never answered inline, even with the cheque flag set
r3 = answer_question("my bank account was frozen by the police and nobody told me why",
                     inline_domains={"cheque_bounce"})
check(r3.get("state") == "covered_elsewhere_in_tool" and r3.get("redirect_domain") == "freeze",
      "a freeze question still redirects even when cheque inlining is on")


print("\n" + "=" * 70)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
sys.exit(0)
