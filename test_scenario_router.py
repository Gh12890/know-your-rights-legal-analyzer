"""
test_scenario_router.py

Vibeathon Step 2 -- scenario_router + scenario_spec + scenario_answer.
No Anthropic calls: scenario_router.client is forced to None so route_situation
falls to the deterministic keyword router. The real LOCAL corpus embeddings are
used to validate every case_name in the catalogue.

Run: python test_scenario_router.py
"""

import logging
import sys

logging.getLogger("scenario_answer").setLevel(logging.CRITICAL)
logging.getLogger("scenario_router").setLevel(logging.CRITICAL)

import scenario_router
scenario_router.client = None  # force the keyword router everywhere

from scenario_router import route_situation, SCENARIO_IDS, resolve_target, _RESOLVE_TARGET
from scenario_spec import SCENARIOS, all_case_names, get_scenario, ALWAYS
from scenario_answer import build_scenario_answer

FAILURES = []


def check(cond, desc):
    print(f"[{'PASS' if cond else 'FAIL'}] {desc}")
    if not cond:
        FAILURES.append(desc)


# ---------------------------------------------------------------------------
# catalogue integrity
# ---------------------------------------------------------------------------
_BUILT = {"DEFAULT_BAIL", "ARREST_GENERAL", "ARREST_WOMAN", "FIR_NOT_REGISTERED",
          "SUMMONS_PRE_ARREST", "CHEQUE_BOUNCE_NOTICE"}
check(set(SCENARIOS) == _BUILT, f"{len(_BUILT)} scenarios built (got {sorted(SCENARIOS)})")
check(_BUILT <= set(SCENARIO_IDS), "every built scenario id is a routing target")
check("OUT_OF_SCOPE" in SCENARIO_IDS, "OUT_OF_SCOPE is in the enum")

for tid, target in _RESOLVE_TARGET.items():
    check(target in _BUILT or target == "OUT_OF_SCOPE",
          f"resolve target {tid} -> {target} is built or OUT_OF_SCOPE")

# every case in the catalogue must be a real corpus case_name, UNLESS the
# right that carries it is explicitly marked in_corpus=False
from semantic_retrieval import _load_corpus_embeddings
_corpus = {r["case_name"] for r in _load_corpus_embeddings()["records"]
           if r.get("type") == "judgment"}

_allowed_absent = set()
for s in SCENARIOS.values():
    for r in s.rights:
        if r.case and r.in_corpus is False:
            _allowed_absent.add(r.case)

_missing = [c for c in all_case_names() if c not in _corpus and c not in _allowed_absent]
check(not _missing, f"every catalogue case is in the corpus or flagged in_corpus=False "
                    f"(unexpected missing: {_missing})")
check("Lalita Kumari v Government of Uttar Pradesh" in _corpus,
      "Lalita Kumari is now seeded in the corpus (Step 3 batch 4)")
check("Deepa v S. Vijayalakshmi" in _corpus,
      "Deepa v S. Vijayalakshmi is now seeded in the corpus (Step 3 batch 4)")
check(not _allowed_absent,
      f"no catalogue case is still flagged in_corpus=False (remaining: {sorted(_allowed_absent)})")

# every scenario has at least one ALWAYS right (so an answer is never empty)
for sid, s in SCENARIOS.items():
    has_always = any((r.triggers is ALWAYS or not r.triggers) for r in s.rights)
    check(has_always or not s.rights, f"{sid} has an always-on right")

# Arnesh Kumar is confined to the two arrest-notice scenarios only (the
# anti-generic rule) -- NOT in default-bail, FIR, cheque or as a repeat
# landmark everywhere.
_arnesh = {sid for sid, s in SCENARIOS.items()
          if any("arnesh kumar" in c.lower() for c in s.cases)}
check(_arnesh <= {"SUMMONS_PRE_ARREST", "ARREST_GENERAL"},
      f"Arnesh Kumar confined to the arrest-notice scenarios (found in {sorted(_arnesh)})")
# default-bail / FIR / cheque must NOT carry Arnesh Kumar
for _sid in ("DEFAULT_BAIL", "FIR_NOT_REGISTERED", "CHEQUE_BOUNCE_NOTICE"):
    check(not any("arnesh kumar" in c.lower() for c in SCENARIOS[_sid].cases),
          f"{_sid} does not carry Arnesh Kumar")

# a man arrested for theft must NOT get the "A woman has been arrested" answer
from scenario_answer import build_scenario_answer as _bsa
_goat = _bsa("Police came to my house and arrested me saying i stole a goat")
check(_goat["target_id"] == "ARREST_GENERAL",
      f"goat-theft (male) -> ARREST_GENERAL, not ARREST_WOMAN (got {_goat['target_id']})")
check(_goat["scenario_label"] != "A woman has been arrested",
      f"goat-theft heading is not the woman one (got {_goat['scenario_label']!r})")
check(len(_goat["rights"]) >= 3, f"goat-theft answer has rights ({len(_goat['rights'])})")


# ---------------------------------------------------------------------------
# routing -- the 3 frozen heroes + variants (keyword router)
# ---------------------------------------------------------------------------
HERO_ROUTES = [
    ("the police have kept my brother 70 days and still haven't filed any chargesheet",
     "DEFAULT_BAIL"),
    ("my sister was arrested last night, nobody told us why, and she's a nursing mother",
     "ARREST_WOMAN"),
    ("the police won't register my complaint about the goods stolen from my shop",
     "FIR_NOT_REGISTERED"),
]
for text, expected in HERO_ROUTES:
    got = route_situation(text)["scenario_id"]
    check(got == expected, f"route: {expected}  <- {text[:55]!r}  (got {got})")

check(route_situation("how do I get my father's will declared invalid")["scenario_id"]
      == "OUT_OF_SCOPE", "route: OUT_OF_SCOPE for a civil-succession question")
check(route_situation("")["scenario_id"] == "OUT_OF_SCOPE", "route: empty -> OUT_OF_SCOPE")


# ---------------------------------------------------------------------------
# assembly -- the 3 heroes give visibly DIFFERENT answers
# ---------------------------------------------------------------------------
answers = {label: build_scenario_answer(text) for label, text in [
    ("bail", HERO_ROUTES[0][0]),
    ("woman", HERO_ROUTES[1][0]),
    ("fir", HERO_ROUTES[2][0]),
]}

for k, a in answers.items():
    check(a["status"] == "answered", f"hero {k}: status answered")

# distinct scenarios
sids = {k: a["target_id"] for k, a in answers.items()}
check(len(set(sids.values())) == 3, f"3 heroes -> 3 distinct scenarios ({sids})")

# distinct paper types
papers = {a["paper_type"] for a in answers.values()}
check(len(papers) == 3, f"3 heroes -> 3 distinct documents ({papers})")

# distinct case sets, and NO shared case across the three answers
case_sets = {k: set(a["cited_cases"]) for k, a in answers.items()}
_all_pairs_disjoint = all(
    case_sets[a].isdisjoint(case_sets[b])
    for a in case_sets for b in case_sets if a < b
)
check(_all_pairs_disjoint, f"no case is cited in more than one hero answer ({case_sets})")

# the woman answer surfaces the NIGHT right (s.43) because "last night" is present
woman_sections = {r["section"] for r in answers["woman"]["rights"]}
check("43" in woman_sections, "woman/night: s.43 (night-arrest) right fires on 'last night'")
check("58" in woman_sections, "woman: s.58 (24h production) always-on right present")

# the woman answer surfaces the nursing-mother right
woman_text = " ".join(r["plain_text"].lower() for r in answers["woman"]["rights"])
check("nursing mother" in woman_text, "woman: nursing-mother right fires on 'nursing mother'")


# ---------------------------------------------------------------------------
# anti-generic: same scenario, different facts -> different answer
# ---------------------------------------------------------------------------
day = build_scenario_answer("my sister was arrested this afternoon and they haven't told us the grounds")
night = answers["woman"]
day_sections = {r["section"] for r in day["rights"]}
night_sections = {r["section"] for r in night["rights"]}
check("43" not in day_sections, "woman/daytime: s.43 night right does NOT fire")
check(any("sunset" in n["line"].lower() for n in day["negations"]),
      "woman/daytime: negation line states the sunset rule does not apply")
check(night_sections != day_sections,
      "woman: night vs day answers surface different rights")


# default-bail: serious vs ordinary offence -> 90-day right toggles
serious = build_scenario_answer(
    "my brother has been in custody 65 days for an attempt to murder case and there's no chargesheet")
ordinary = answers["bail"]
serious_has_rkp = any("rakesh kumar paul" in r["case"].lower() for r in serious["rights"])
ordinary_has_rkp = any("rakesh kumar paul" in r["case"].lower() for r in ordinary["rights"])
check(serious_has_rkp and not ordinary_has_rkp,
      "default-bail: Rakesh Kumar Paul (90-day) fires for a serious offence, not an ordinary one")
check(any("60 days, not 90" in n["line"] for n in ordinary["negations"]),
      "default-bail/ordinary: negation states the limit is 60 not 90")


# ---------------------------------------------------------------------------
# suppression: a case is never pinned twice in one answer
# ---------------------------------------------------------------------------
for k, a in answers.items():
    pinned = [r["case"] for r in a["rights"] if r["case"]]
    check(len(pinned) == len(set(pinned)), f"hero {k}: no case pinned twice ({pinned})")


# ---------------------------------------------------------------------------
# Step 4: verification badge + document
# ---------------------------------------------------------------------------
from scenario_verification import verification_badge
from scenario_draft import build_document, document_pdf

b = verification_badge("Lalita Kumari v Government of Uttar Pradesh",
                       chunk_method="curated_excerpt")
check(b["all_ok"] and len(b["checks"]) == 4,
      f"badge: Lalita Kumari 4/4 ({b['summary']})")
check(all(k in {c["key"] for c in b["checks"]}
          for k in ("exists", "good_law", "verbatim", "on_point")),
      "badge: all four check keys present")
b2 = verification_badge("Some Unknown Case v Nobody", chunk_method="fixed_size_fallback")
check(not b2["checks"][1]["ok"] and not b2["checks"][2]["ok"],
      "badge: an unknown case fails good-law and verbatim, honestly")

# every cited right in every hero answer carries a badge
for k, a in answers.items():
    for r in a["rights"]:
        if r["case"]:
            check(bool(r.get("badge")), f"{k}: cited right has a badge ({r['case'][:30]})")

# document for each hero
import tempfile as _tf
for k, a in answers.items():
    doc = build_document(a, HERO_ROUTES[["bail", "woman", "fir"].index(k)][0])
    check(doc["available"] and len(doc["text"]) > 400, f"{k}: document builds ({doc['target']})")
    check("not legal advice" in doc["text"].lower(), f"{k}: document carries the disclaimer")
    p = _tf.mkstemp(suffix=".pdf")[1]
    try:
        document_pdf(doc, p)
        import os as _os
        check(_os.path.getsize(p) > 1500, f"{k}: PDF renders")
    except Exception as e:  # noqa
        check(False, f"{k}: PDF render raised {e!r}")

# the woman document names the night fact it lifted from the message
wdoc = build_document(answers["woman"], "my sister was arrested last night around 9 pm, nobody told us why")
check("9:00 pm" in wdoc["text"] or "sunset" in wdoc["text"].lower(),
      "woman document: lifts the arrest-time / night fact from the message")

# out-of-scope -> no document
oos = build_scenario_answer("how do I get my father's will declared invalid")
check(build_document(oos, "x")["available"] is False,
      "out-of-scope: no document offered")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
