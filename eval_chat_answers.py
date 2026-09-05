
"""
eval_chat_answers.py

Quality harness for the free-text chat feature (chat_assistant.answer_question).

WHY THIS EXISTS:
The only automated check on chat output so far is test_chat_grounding.py,
which checks GROUNDING CORRECTNESS (no ungrounded "Section N", no
ThinkingBlock crash). Nothing measures whether the ANSWER IS ANY GOOD --
right shape, right length, leads with the practical step, doesn't dump a
laundry list of marginally-relevant sections, doesn't conflate the IPC,
doesn't hedge after already answering. Every prompt change so far has
been judged by eyeballing one or two answers.

This runs a fixed set of representative questions through the real
pipeline and reports, per question:
  - the classifier state + (for routed questions) the redirect_domain
  - how many match blocks were fed to the generator, and which distinct
    "Section N" numbers the ANSWER ends up citing
  - word count
  - whether a "what you can do next"-style closer appears more than once
  - MUST_INCLUDE / MUST_NOT_INCLUDE substring checks (case-insensitive)
  - the full answer text, for human review

It is NOT a pass/fail gate. The substring checks are directional signals;
the real judgement is a human reading answers.txt. Later this can grow an
LLM-judge layer -- start with human review.

COST: real Anthropic + Voyage calls -- roughly 2-3 Claude calls and one
embedding per question. Use --only / --limit while iterating.

Run:
  python eval_chat_answers.py                 # all cases, write eval_out/
  python eval_chat_answers.py --only goat-theft-arrest
  python eval_chat_answers.py --limit 3
  python eval_chat_answers.py --label before  # tag this run's output dir
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from chat_assistant import answer_question


# ---------------------------------------------------------------------------
# The eval set. Each case:
#   id            -- stable slug
#   question      -- verbatim user input
#   expect_state  -- optional: the answer_question state we expect
#   expect_redirect -- optional: redirect_domain for routed questions
#   must_include  -- substrings that SHOULD appear (case-insensitive); each
#                    is really "at least one of these" if given a tuple
#   must_not      -- substrings that MUST NOT appear
#   notes         -- the ideal shape, for the human reading the report
# ---------------------------------------------------------------------------
CASES = [
    {
        "id": "goat-theft-arrest",
        "question": "police came to my house and arrested me directly saying that i stole a goat",
        "expect_state": "in_scope_answer",
        "must_include": [("303", "theft"), ("35", "notice", "Arnesh Kumar"),
                         ("47", "grounds of arrest", "Vihaan Kumar"),
                         ("24 hour", "Magistrate")],
        "must_not": ["Indian Penal Code", " IPC", "Section 274", "retrieved text",
                     "the text I have", "your arrest was illegal", "this arrest is illegal"],
        "notes": "Action-first. <=350 words. <=4 distinct sections cited. "
                 "Must mention the Section 303 low-value/first-offence bailable carve-out. "
                 "One 'what you can do next', at the end. No verdict.",
    },
    {
        "id": "what-is-318",
        "question": "what is section 318 of BNS",
        "expect_state": "in_scope_answer",
        "must_include": ["318", "cheat"],
        "must_not": ["Indian Penal Code", " IPC", "retrieved text"],
        "notes": "Explain-mode -- no 'right now' block needed. Should name subsections "
                 "(318(1)-(4)) precisely if the data distinguishes them.",
    },
    {
        "id": "cheating-direct-arrest",
        "question": "can the police arrest me directly for cheating without a warrant",
        "expect_state": "in_scope_answer",
        "must_include": ["318", ("cognizable", "without a warrant")],
        "must_not": ["Indian Penal Code", " IPC", "this is legal", "this is illegal"],
        "notes": "Should state the cognizability status (deterministic fact) clearly, "
                 "not bury it. No verdict on the person's own arrest.",
    },
    {
        "id": "attempt-murder-timing",
        "question": "when can police file charges of attempt to murder",
        "expect_state": "in_scope_answer",
        "must_include": ["109"],
        "must_not": ["Indian Penal Code", " IPC",
                     "could not cleanly extract", "couldn't be cleanly extracted",
                     "a real exception exists that this system"],
        "notes": "Both punishment conditions (general vs. 'if hurt caused') stated "
                 "cleanly. NO reflexive 'a lawyer should confirm the exact condition' "
                 "hedge after already stating both conditions.",
    },
    {
        "id": "dowry-wife-complaint",
        "question": "my wife has filed a dowry case against me and police are asking me to come",
        "expect_state": "in_scope_answer",
        "must_include": [["85", "cruelty"]],
        "must_not": ["your arrest was illegal"],
        "notes": "BOTH gaps this case exists to catch are now fixed (2026-09-04). "
                 "(1) CONFIRMED SERIOUS BUG CLASS: a living wife's ongoing complaint "
                 "was once matched to Section 80 (dowry DEATH) as if it were the "
                 "applicable law -- fixed by adding an order-sensitive pair of "
                 "_OFFENCE_KEYWORD_ANCHORS entries (chat_assistant.py): a genuine "
                 "death/suicide/burning word near 'dowry' anchors to 80, every other "
                 "'dowry' mention anchors to the actually-applicable 85 (cruelty by "
                 "husband/relatives). (2) KNOWN CLASSIFIER GAP: 'dowry case' used to "
                 "read as a 'dowry-specific act' (adjacent_uncovered) -- fixed by a "
                 "SCOPE_CLASSIFIER_PROMPT rule distinguishing an offence's civil/family "
                 "BACKSTORY from the actual event being asked about. expect_state is "
                 "now unconditionally in_scope_answer, and must_include requires 85 "
                 "actually be cited -- proof the RIGHT section leads, not just that "
                 "the WRONG one is absent. must_not no longer blanket-bans 'dowry "
                 "death'/'Section 80'/'seven years to life': once 85 correctly leads, "
                 "a properly hedged aside noting Section 80 would apply only if death "
                 "were involved is accurate, useful content, not a recurrence of the "
                 "original bug (which was 80 presented as the applicable law, not 80 "
                 "mentioned at all).",
    },
    {
        "id": "freeze-route",
        "question": "my bank account was frozen by the police and nobody told me why",
        "expect_state": "covered_elsewhere_in_tool",
        "expect_redirect": "freeze",
        "must_include": [],
        "must_not": [],
        "notes": "Should route to the freeze interview (redirect_domain='freeze'), "
                 "not answer with a RAG explanation.",
    },
    {
        "id": "cheque-route",
        "question": "I received a legal notice saying my cheque bounced, what happens now",
        "expect_state": "covered_elsewhere_in_tool",
        "expect_redirect": "cheque_bounce",
        "must_include": [],
        "must_not": [],
        "notes": "Should route to the cheque-bounce interview.",
    },
    {
        "id": "fir-copy-denied",
        "question": "police registered an FIR against me but the station refuses to give me a copy",
        "expect_state": "in_scope_answer",
        "must_include": [("FIR", "first information report"), ("copy", "website", "uploaded")],
        "must_not": ["Indian Penal Code", "this is illegal"],
        "notes": "Should explain the FIR-copy right and the police-website upload rule "
                 "(Youth Bar Association). No verdict.",
    },
    {
        "id": "night-arrest-woman",
        "question": "police came and arrested my sister at 10 at night from our home",
        "expect_state": "in_scope_answer",
        "must_include": [("night", "woman", "female"), ("43", "female officer", "sunset")],
        "must_not": ["Indian Penal Code", "your arrest was illegal"],
        "notes": "The BNSS 43(5) curated override should fire (arrest of a woman after "
                 "sunset). Should mention the female-officer / no-night-arrest rule.",
    },
    {
        "id": "unrelated-weather",
        "question": "what is the weather in delhi today",
        "expect_state": "unrelated",
        "must_include": [],
        "must_not": [],
        "notes": "Must classify as unrelated -- no retrieval, no answer attempt.",
    },
    {
        "id": "general-rights-if-arrested",
        "question": "what are my rights if the police arrest me",
        "expect_state": "in_scope_answer",
        "max_sections": 8,  # genuinely spans many distinct rights; the
                            # failure mode was 17 sections, not 7
        "must_include": [("grounds of arrest", "47"), ("lawyer", "advocate", "38"),
                         ("24 hour", "Magistrate", "58"), ("family", "relative", "48")],
        "must_not": ["Indian Penal Code", "retrieved text"],
        "notes": "The 'template arrest rights' case. Comprehensive but STRUCTURED -- "
                 "not a wall of text, not a laundry list of every procedural section.",
    },
    {
        "id": "default-bail-70-days",
        "question": "police have kept my brother for 70 days and still not filed a chargesheet",
        "expect_state": "in_scope_answer",
        "must_include": [("default bail", "187", "matter of right"), ("60", "90")],
        "must_not": ["Indian Penal Code"],
        "notes": "Explain the default-bail right and the 60/90-day distinction. May "
                 "explain the right without computing a date (chat has no facts engine).",
    },
    {
        "id": "arrest-no-reason",
        "question": "the police took me to the station without telling me what i had done",
        "expect_state": "in_scope_answer",
        "must_include": [("grounds of arrest", "47", "Vihaan Kumar", "Article 22")],
        "must_not": ["Indian Penal Code", "your arrest was definitely illegal"],
        "notes": "Arrest-situation. Should explain the written-grounds requirement and "
                 "that a court can be asked to examine an arrest made without it -- "
                 "WITHOUT delivering a hard verdict.",
    },
    {
        "id": "medical-not-done",
        "question": "my father was arrested yesterday and was never taken to a doctor",
        "expect_state": "in_scope_answer",
        "must_include": [("D.K. Basu", "medical", "48", "doctor")],
        "must_not": ["Indian Penal Code"],
        "notes": "Should surface the D.K. Basu medical-examination safeguard.",
    },
    {
        "id": "anticipatory-bail",
        "question": "i think the police are going to arrest me soon, what can i do",
        "expect_state": "in_scope_answer",
        "must_include": [("anticipatory bail", "482", "before arrest")],
        "must_not": ["Indian Penal Code"],
        "notes": "Should explain anticipatory bail (BNSS 482) as the pre-arrest remedy.",
    },
]


_CLOSER_PAT = re.compile(
    r"what (you|to) (can|could) do next|what you can do|"
    r"upload .{0,60}\bhere\b|you can upload|"  # "upload it here", "upload the arrest memo or FIR here"
    r"describe (my|your) situation|option above will|"
    r"a lawyer (can|could|should)",
    re.IGNORECASE,
)
# The specific phrase the prompt mandates once at the end AND that
# app.py's conflicting_matches branch used to also append -- so 2+
# occurrences is the DUPLICATE-CLOSER bug (confirmed live 2026-09-01).
_DUPLICATE_CLOSER_PAT = re.compile(r"what you can do next", re.IGNORECASE)
_SECTION_PAT = re.compile(r"\bSection\s+(\d+)", re.IGNORECASE)


def _norm_state(result):
    """answer_question returns many states; collapse the in_scope answer
    states into one label so expectations are simple to write."""
    s = result.get("state")
    if s in ("single_match", "conflicting_matches"):
        return "in_scope_answer"
    return s


def _check_group(text_lc, group):
    """A must_include entry is either a string (must appear) or a tuple
    (at least one must appear). Returns (ok, detail)."""
    if isinstance(group, str):
        return (group.lower() in text_lc, group)
    hit = [g for g in group if g.lower() in text_lc]
    return (bool(hit), f"any({list(group)}) -> {hit or 'NONE'}")


def run_case(case):
    t0 = time.time()
    try:
        result = answer_question(case["question"])
    except Exception as exc:  # noqa: BLE001
        return {"id": case["id"], "error": repr(exc), "elapsed": time.time() - t0}

    state = _norm_state(result)
    answer = result.get("response_text") or ""
    answer_lc = answer.lower()
    matches = result.get("matches") or []
    cited_sections = sorted(set(_SECTION_PAT.findall(answer)), key=lambda x: int(x))
    closer_hits = len(_CLOSER_PAT.findall(answer))
    duplicate_closer_hits = len(_DUPLICATE_CLOSER_PAT.findall(answer))
    word_count = len(answer.split())

    inc_results = [_check_group(answer_lc, g) for g in case.get("must_include", [])]
    exc_results = [(bad, bad.lower() not in answer_lc) for bad in case.get("must_not", [])]

    checks = []
    want_state = case.get("expect_state")
    if want_state:
        ok_states = want_state if isinstance(want_state, tuple) else (want_state,)
        checks.append(("state", state in ok_states,
                       f"{state} (want {' or '.join(ok_states)})"))
    if case.get("expect_redirect"):
        checks.append(("redirect_domain", result.get("redirect_domain") == case["expect_redirect"],
                       f"{result.get('redirect_domain')} (want {case['expect_redirect']})"))
    for ok, detail in inc_results:
        checks.append(("must_include", ok, detail))
    for bad, ok in exc_results:
        checks.append(("must_not", ok, f"{bad!r} {'absent' if ok else 'PRESENT'}"))
    if state == "in_scope_answer":
        checks.append(("has_closer", closer_hits >= 1, f"{closer_hits} next-step pointer(s)"))
        checks.append(("no_duplicate_closer", duplicate_closer_hits <= 1,
                       f"'what you can do next' appears {duplicate_closer_hits}x"))
        cap = case.get("max_sections", 5)
        checks.append(("section_count", len(cited_sections) <= cap,
                       f"{len(cited_sections)} distinct sections cited (cap {cap}): {cited_sections}"))
        checks.append(("length", word_count <= 400, f"{word_count} words"))

    return {
        "id": case["id"],
        "question": case["question"],
        "notes": case["notes"],
        "state": state,
        "redirect_domain": result.get("redirect_domain"),
        "match_blocks_fed": len(matches),
        "cited_sections": cited_sections,
        "closer_hits": closer_hits,
        "duplicate_closer_hits": duplicate_closer_hits,
        "word_count": word_count,
        "checks": checks,
        "n_fail": sum(1 for _, ok, _ in checks if not ok),
        "answer": answer,
        "elapsed": round(time.time() - t0, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="run only these case ids (repeatable)")
    ap.add_argument("--limit", type=int, help="run only the first N cases")
    ap.add_argument("--label", default=None, help="tag for the output dir (e.g. 'before', 'after')")
    ap.add_argument("--out-root", default="eval_out")
    args = ap.parse_args()

    cases = CASES
    if args.only:
        cases = [c for c in CASES if c["id"] in set(args.only)]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        sys.exit("no cases selected")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = f"{stamp}-{args.label}" if args.label else stamp
    out_dir = os.path.join(args.out_root, tag)
    os.makedirs(out_dir, exist_ok=True)

    results = []
    for c in cases:
        print(f"  running {c['id']} ...", flush=True)
        results.append(run_case(c))

    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)

    lines = [f"# Chat answer eval  ({tag})", ""]
    total_fail = 0
    for r in results:
        if "error" in r:
            lines += [f"## {r['id']}  -- ERROR", "```", r["error"], "```", ""]
            total_fail += 1
            continue
        total_fail += r["n_fail"]
        head = f"## {r['id']}   [{r['n_fail']} check failure(s)]"
        lines.append(head)
        lines.append(f"**Q:** {r['question']}")
        lines.append(f"**Ideal:** {r['notes']}")
        lines.append(f"state=`{r['state']}` redirect=`{r['redirect_domain']}` "
                     f"blocks_fed=`{r['match_blocks_fed']}` "
                     f"cited_sections=`{r['cited_sections']}` "
                     f"closers=`{r['closer_hits']}` words=`{r['word_count']}` "
                     f"({r['elapsed']}s)")
        lines.append("")
        for name, ok, detail in r["checks"]:
            lines.append(f"- [{'x' if ok else ' '}] {name}: {detail}")
        lines.append("")
        lines.append("**Answer:**")
        lines.append("")
        lines.append("> " + (r["answer"].replace("\n", "\n> ") if r["answer"] else "(empty)"))
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.insert(1, f"\n**{len(results)} cases, {total_fail} total check failures.**\n")
    report = "\n".join(lines)
    report_path = os.path.join(out_dir, "answers.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report)

    print(f"\n{len(results)} cases, {total_fail} total check failures.")
    print(f"report: {report_path}")
    for r in results:
        flag = "ERR" if "error" in r else f"{r['n_fail']:>2} fail"
        print(f"  {flag}  {r['id']}")


if __name__ == "__main__":
    main()
