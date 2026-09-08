"""
eval_recourse_battery.py

Re-run the full set of test scenarios raised across the build, against BOTH
layers as they stand now:

  A) the Recourse scenario layer  (scenario_answer.build_scenario_answer)
     -- what recourse.co.in actually serves.
  B) the FIR/arrest free-text chat (chat_assistant.answer_question)
     -- the older, wider module (offence keyword anchors, scope classifier).

For each scenario it prints: which situation/state it routed to, the
sections and cases surfaced, and a quick check of the "not generic" property
(do different questions produce different answers).

Run:  python eval_recourse_battery.py
      python eval_recourse_battery.py --chat        # also run layer B
"""

import argparse
import sys

# ---- the battery -------------------------------------------------------------
# each: (id, question, layer, expectation-note)
#   layer: "scenario" | "chat" | "both"
ARREST_SCENARIOS = [
    ("default-bail-70d",
     "the police have kept my brother 70 days and still haven't filed any chargesheet",
     "scenario", "DEFAULT_BAIL, 60-day line (ordinary offence)"),
    ("default-bail-serious",
     "my brother has been in custody 65 days for an attempt to murder case and there's no chargesheet",
     "scenario", "DEFAULT_BAIL, 90-day line + Rakesh Kumar Paul"),
    ("arrest-woman-night",
     "my sister was arrested last night around 9 pm, nobody told us why, and she's a nursing mother",
     "scenario", "ARREST_WOMAN, s.43 night + nursing-mother rights"),
    ("arrest-woman-day",
     "my sister was arrested this afternoon and they haven't told us the grounds",
     "scenario", "ARREST_WOMAN, NO night right, sunset negation"),
    ("fir-not-registered",
     "the police won't register my complaint about the goods stolen from my shop",
     "scenario", "FIR_NOT_REGISTERED, Lalita Kumari + s.175(3)"),
    ("arrest-general-goat",
     "Police came to my house and arrested me saying i stole a goat",
     "scenario", "ARREST_GENERAL (male, theft) -- NOT 'A woman has been arrested'"),
    ("arrest-general-beaten",
     "police beat my brother in the lockup after arresting him",
     "scenario", "ARREST_GENERAL, custodial-violence right + D.K. Basu"),
    ("arrest-general-24h",
     "my father was arrested 3 days ago and still not produced before any magistrate",
     "scenario", "ARREST_GENERAL, 24-hour production"),
    ("summons-pre-arrest",
     "the police keep calling me to the station over a cheating complaint, I'm not named in the FIR",
     "scenario", "SUMMONS_PRE_ARREST, Arnesh Kumar + Satender Kumar Antil"),
    ("cheque-bounce",
     "a cheque I received bounced and I want to know what to do next",
     "scenario", "CHEQUE_BOUNCE_NOTICE"),
]

OFFENCE_VARIETY = [
    ("will-civil",
     "how do I get my late father's will declared invalid",
     "both", "pure civil -> OUT_OF_SCOPE (scenario) / adjacent_uncovered (chat)"),
    ("land-dispute-arrest",
     "there is a land dispute between our family and the neighbours and after a scuffle "
     "the police arrested my son the same evening",
     "both", "mixed: an arrest happened -> should give arrest rights, not just 'civil'"),
    ("dowry-wife-complaint",
     "my wife has filed a dowry case against me and the police are asking me to come to the station",
     "both", "living wife's cruelty complaint -> BNS 85 (chat) / SUMMONS-ish (scenario)"),
    ("dowry-death",
     "my brother's wife died and her family are saying it is a dowry death and the police have taken him",
     "both", "dowry DEATH -> BNS 80 (chat). scenario: an arrest happened -> arrest rights"),
    ("forgery",
     "someone forged my signature on a property document and used it to transfer my land",
     "both", "forgery -> BNS 336 (chat) / FIR-not-registered-ish or OOS (scenario)"),
    ("cruelty-victim",
     "my husband and his family beat me and keep demanding dowry, I want to file a complaint",
     "both", "cruelty by husband/relatives -> BNS 85 (chat)"),
    ("false-fir-property",
     "an FIR has been registered against me over a property dispute about ancestral land "
     "and the police are now threatening to arrest me",
     "both", "property-dispute-as-crime + threatened arrest"),
    ("partnership-cheating",
     "i ran a small trading partnership with my cousin, he moved money out of the firm account, "
     "and now he has filed a cheating case against me",
     "both", "civil/commercial dispute dressed as cheating"),
    ("weather",
     "what is the weather like in Delhi today",
     "both", "not legal -> OUT_OF_SCOPE / unrelated"),
]


def _scenario_row(q):
    from scenario_answer import build_scenario_answer
    a = build_scenario_answer(q)
    if a["status"] != "answered":
        return {
            "route": f"OUT_OF_SCOPE ({a.get('routed_id')})",
            "conf": a.get("confidence", 0.0),
            "sections": [], "cases": [], "label": "(honest refusal)",
            "nrights": 0,
        }
    return {
        "route": f'{a["routed_id"]} -> {a["target_id"]}',
        "conf": a.get("confidence", 0.0),
        "label": a["scenario_label"],
        "sections": sorted({f'{r["act"]} {r["section"]}'.strip()
                            for r in a["rights"] if r.get("section")}),
        "cases": a["cited_cases"],
        "nrights": len(a["rights"]),
        "negations": [n["line"][:60] for n in a.get("negations", [])],
    }


def _chat_row(q):
    from chat_assistant import answer_question
    r = answer_question(q)
    state = r.get("state")
    out = {"state": state, "sections": [], "cases": []}
    if state == "covered_elsewhere_in_tool":
        out["state"] = f"covered_elsewhere ({r.get('redirect_domain')})"
    matches = r.get("matches") or []
    out["sections"] = sorted({f'{m.get("act","")} {m.get("section_number","")}'.strip()
                              for m in matches if m.get("section_number")})
    txt = (r.get("response_text") or "")[:220].replace("\n", " ")
    out["preview"] = txt
    out["reasoning"] = r.get("reasoning", "")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat", action="store_true", help="also run the free-text chat layer (slower, Sonnet)")
    args = ap.parse_args()

    print("=" * 90)
    print("A) RECOURSE SCENARIO LAYER  (what recourse.co.in serves)")
    print("=" * 90)
    seen_answers = {}
    for cid, q, layer, note in ARREST_SCENARIOS + [s for s in OFFENCE_VARIETY]:
        row = _scenario_row(q)
        key = (row["route"], tuple(row["sections"]), tuple(row["cases"]))
        dup = seen_answers.get(key)
        seen_answers.setdefault(key, cid)
        print(f"\n[{cid}]  {q[:78]}")
        print(f"   expect: {note}")
        print(f"   route : {row['route']}   conf={row['conf']:.0%}   ({row.get('label','')})")
        print(f"   rights: {row['nrights']}   sections: {row['sections']}")
        print(f"   cases : {row['cases']}")
        if row.get("negations"):
            print(f"   negations: {row['negations']}")
        if dup and dup != cid:
            print(f"   [!] SAME answer shape as [{dup}] -- possible generic collision")

    if args.chat:
        print("\n\n" + "=" * 90)
        print("B) FIR/ARREST FREE-TEXT CHAT LAYER  (chat_assistant.answer_question)")
        print("=" * 90)
        for cid, q, layer, note in OFFENCE_VARIETY + ARREST_SCENARIOS:
            row = _chat_row(q)
            print(f"\n[{cid}]  {q[:78]}")
            print(f"   expect: {note}")
            print(f"   state : {row['state']}")
            if row.get("reasoning"):
                print(f"   reason: {row['reasoning'][:120]}")
            if row["sections"]:
                print(f"   sections fed to answer: {row['sections']}")
            if row.get("preview"):
                print(f"   answer: {row['preview']}…")

    print("\n\ndone.")


if __name__ == "__main__":
    sys.exit(main())
