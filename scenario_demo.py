"""
scenario_demo.py  (Vibeathon Step 2, 2026-09-06)

Run the routing + assembly layer over the frozen hero inputs (and anything you
type) and print the tailored answer.

    python scenario_demo.py                 # the 3 frozen heroes
    python scenario_demo.py --statute       # also print the quoted statute text
    python scenario_demo.py --variants      # heroes + input variations (anti-generic proof)
    python scenario_demo.py "my own free text here"

STEP 2 EXIT TEST: the 3 heroes below must produce visibly DIFFERENT structured
answers -- different scenario, different rights, different cases, different
document. `--variants` is the check that different inputs into the SAME scenario
also diverge.
"""

import argparse
import sys

from scenario_answer import build_scenario_answer, render_text

# The frozen hero input strings (VIBEATHON_PLAN.md - do not edit without
# re-freezing there).
HEROES = [
    ("DEFAULT-BAIL",
     "the police have kept my brother 70 days and still haven't filed any chargesheet"),
    ("ARREST-WOMAN",
     "my sister was arrested last night, nobody told us why, and she's a nursing mother"),
    ("FIR-NOT-REGISTERED",
     "the police won't register my complaint about the goods stolen from my shop"),
]

# Variations - same scenario, different facts -> must give a different answer.
VARIANTS = [
    ("ARREST-WOMAN / daytime, no night factor",
     "my sister was arrested this afternoon and they haven't told us the grounds"),
    ("ARREST-WOMAN / custodial violence red flag",
     "my wife was picked up last night, she says she was slapped in the lockup and no lady constable was there"),
    ("DEFAULT-BAIL / serious offence -> 90 days",
     "my brother has been in custody 65 days for an attempt to murder case and there's no chargesheet"),
    ("SUMMONS-PRE-ARREST / not arrested yet",
     "the police keep calling me to the station over a cheating complaint, I'm not named in the FIR, should I be worried about arrest"),
    ("OUT-OF-SCOPE / not our domain",
     "how do I get my late father's will declared invalid"),
]


def _run(label, text, *, show_statute):
    print("=" * 78)
    print(f"INPUT [{label}]:")
    print(f'  "{text}"')
    print("-" * 78)
    answer = build_scenario_answer(text)
    print(render_text(answer, show_statute=show_statute))
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("freetext", nargs="*", help="run one custom input instead of the heroes")
    ap.add_argument("--statute", action="store_true", help="print quoted statute text under each right")
    ap.add_argument("--variants", action="store_true", help="also run the input variations")
    args = ap.parse_args()

    if args.freetext:
        _run("custom", " ".join(args.freetext), show_statute=args.statute)
        return

    for label, text in HEROES:
        _run(label, text, show_statute=args.statute)

    if args.variants:
        print("\n" + "#" * 78)
        print("# VARIANTS - same scenario, different facts, different answer")
        print("#" * 78 + "\n")
        for label, text in VARIANTS:
            _run(label, text, show_statute=args.statute)


if __name__ == "__main__":
    sys.exit(main())
