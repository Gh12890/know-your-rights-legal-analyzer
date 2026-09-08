# Vibeathon Battle Plan — Step 1 to submission

*Devised 2026-09-06. This is the permanent copy — do not lose it.*

**ILTN × vibecode.law Vibeathon 2026 · Submit by 11 Sep 5:00 PM IST · target submission 10 Sep · ~4 working days**

Prizes: ₹75k + Trilegal internship (1st) · ₹50k (runner-up) · ₹25k (open track).
Judges include **Sateesh Nori** (LawDroid — career access-to-justice). Field: Vaadhan is the class of the field.

---

## The bet (positioning)

Vaadhan and the field build for the **advocate**. We build for **the person the case is happening to, and their family**. That lane is open and one judge has spent his career in it. We already have the hard half — an engine that won't state a legal conclusion from an LLM, checks every citation four ways, knows the IPC→BNS mapping. We wrap the smallest honest product around it.

**The reframe:** access to justice is not "answer a legal question." It is: *tell me what stage I'm at, what the other side can and cannot do to me right now, what my rights are at this specific moment, what my family should do in the next 24 hours — and hand me the paper to do it.* The tool answers the **situation = role × stage × factors**, not the words.

**Name:** **Recourse** (recommended). Alts: Grounds, Habeas, The Brief.
**Tagline:** *When the police come, you have more rights than you think — and the paper to use them.*

**Positioning paragraph (draft):**
> Over three-quarters of India's prison population are undertrials — people not convicted of anything. When the police come, most people (and their families) don't know that the arrest must come with written grounds, that a woman can't be arrested after sunset without a magistrate's sanction, or that a missed chargesheet deadline means bail as of right. Recourse takes a plain-language description of what's happening and tells you: what stage you're at, what the police can and cannot do, your rights right now, what to do in the next 24 hours — and generates the document to do it. Every section and every judgment it shows is checked four ways. It says "I don't know" before it invents anything.

---

## Scope discipline

**Complete ~100% of a deliberately narrow slice** (~25–30% of total product vision). A 100%-done 30%-scope submission beats a 70%-done 100%-scope one every time in a demo competition.

**Cut from the demo (keep in repo):** cheque-bounce + asset-freeze domains, the 4 entry modes, Project 1/2/4 scaffolding. Lead with **free-text only**. Document-upload = a ~20s live-demo coda + one writeup sentence, **not** in the video.

**NOT in these 4 days:** Lane B findings #5–#7, MCP server, accounts, multi-domain, Pankaj Bansal / Vijay Kumar Ghai re-chunk, any refactor.

---

## The 3 hero scenarios (frozen demo spine)

2 accused-side, 1 victim-side (proves role-awareness) · 3 stages · ~9 cases, zero overlap · 3 documents.

| ID | Frozen input string | Cases (no repeats) | Document |
|---|---|---|---|
| **DEFAULT-BAIL** | *"the police have kept my brother 70 days and still haven't filed any chargesheet"* | M. Ravindran · Bikramjit Singh · Rakesh Kumar Paul | default-bail application skeleton |
| **ARREST-WOMAN** | *"my sister was arrested last night, nobody told us why, and she's a nursing mother"* | Prabir Purkayastha / Pankaj Bansal (grounds) · s.43(5) BNSS (sunset) · D.K. Basu (inform family, medical) | representation to the Magistrate |
| **FIR-NOT-REGISTERED** | *"the police won't register my complaint about the goods stolen from my shop"* | Lalita Kumari · zero-FIR · s.175(3) BNSS magistrate route | complaint to Magistrate under s.175(3) |

**Corpus risk:** Lalita Kumari + a zero-FIR case probably aren't in the corpus — Step 3 top-up (hard cap 4 new cases). **Fallback if it slips past noon on Day 3:** swap hero 3 → **FALSE-FIR-AGAINST-ME** (quashing, s.528 BNSS / Bhajan Lal; Vijay Kumar Ghai + Usha Chakraborty — already in corpus). Keeps distinctness, loses the role flip. In that world document-upload becomes a legitimate co-headliner for that hero. **Decide by end of Day 3.**
**Further fallback:** 2 heroes fully finished (DEFAULT-BAIL + ARREST-WOMAN).

---

## The 6 anti-generic mechanics

| # | Mechanic | What it does |
|---|---|---|
| 1 | **Scenario routing, not topic matching** | ~14 mutually distinct scenario IDs, each with its **own** 2–4 case set. Arnesh Kumar lives **only** in the summons/pre-arrest scenario — never in default-bail, FIR-not-registered, or custodial-violence. |
| 2 | **Sub-issue → (right, case, paragraph) pinning** | "They beat him" → D.K. Basu custodial-torture para. "No lady constable" → s.43(5) BNSS. "They took his insulin" → medical-exam right. Same scenario, different inputs, different cases. |
| 3 | **Suppression rule** | A case surfaced once for issue A is not reused for issue B in the same answer — fall to the next distinct authority. One line in Lane B ranking. |
| 4 | **Precision through negation** | "Your situation does **not** raise X" — "this is a bailable offence, so the discretionary bail law doesn't apply to you; bail is yours as of right." |
| 5 | **Corpus on the fact axis, not the fame axis** | Add cases chosen for factual texture (senior citizen wrongly held, daily-wager who can't furnish surety, zero-FIR, NRI 498A) — only what the hero scenarios need. |
| 6 | **The generated document is the proof** | `draft_layer` pulls the arrest time / dates / offence from the user's story into the paper. A chatbot cannot do this. |

Architecturally this is **one new layer** (`scenario_router.py` + `SCENARIO_SPEC`) on top of everything already built. Deterministic verdict path, `draft_layer`, `statute_concordance`, citation-currency checks, Lane B — all reused.

---

## STEP 1 — Lock & frame · *6 Sep PM · ~2 hrs*
**Exit: a one-page spec, a name, frozen scope, a `submission` branch.**

- **Name it.** Decide, don't reopen. (Recommendation: Recourse.)
- **Confirm the 3 heroes.** Write the exact demo input string for each — frozen from here.
- **Positioning paragraph** (above).
- **Branch:** `git checkout -b submission`. Only submission-scoped commits from here.
- **Teammate's job:** author the scenario content for the 3 heroes; review every rights line and every case pin for legal correctness; be the opener in the live demo.

---

## STEP 2 — The routing layer · *7 Sep*
**Exit: 3 hero inputs → visibly distinct structured answers in the CLI.**

- `scenario_router.py` — bounded Haiku call (temp 0) → `{role, stage, offence_hint, factors[], scenario_id, confidence}` against a **fixed enum** of ~14 scenario IDs; low confidence → `OUT-OF-SCOPE`. Reuse the `decompose_situation` pattern.
- `SCENARIO_SPEC` data file — 3 heroes + 2 reserves (`SUMMONS-PRE-ARREST`, `CHEQUE-BOUNCE-NOTICE`). Per scenario:
  - stage explainer (plain language, LLM fills slots, verified)
  - `rights[]` — each `{plain_text, section, pinned_case + para_hint, sub_issue_triggers[]}`
  - can / cannot list
  - next-24h actions
  - `paper_type`
  - red flags ("see a lawyer immediately if…")
- Response assembler — SCENARIO_SPEC + the user's decomposed sub-issues → a tailored, ordered rights checklist (only the rights they raised) + negation lines. Wire to existing Lane A verdict + Lane B panel + `draft_layer`.

---

## STEP 3 — Anti-generic + corpus top-up · *8 Sep* ✅ DONE (commit 923ee3e)
**Exit: 3 different inputs per hero → different cases & rights each time. Every hero case anchor resolves clean.** — met.

- Mechanics 2 (sub-issue pinning via triggers), 3 (suppression), 4 (negation) — built in `scenario_answer.py` (Step 2).
- Mechanic 1 (scenario-scoped cases): the scenario layer serves cases ONLY from each scenario's own pool — Arnesh Kumar appears in exactly one scenario. Lane B panel scoping is a Step 4 integration detail.
- Mechanic 5 (corpus, fact axis): batch 4 seeded **2** cases (under the cap of 4), both fetched live + verbatim-verified + finality-checked:
  - **Lalita Kumari v Government of Uttar Pradesh** (2014) 2 SCC 1 — para 111 holding → FIR_NOT_REGISTERED anchor (was not in corpus).
  - **Deepa v S. Vijayalakshmi** (Madras HC DB, 2025) — Section 43(5) BNSS directory-not-mandatory → ARREST_WOMAN night-arrest pin (had no case).
- Mechanic 6 (document pulls the user's facts) — Step 4.
- **HERO 3 DECISION: keep `FIR_NOT_REGISTERED`.** Lalita Kumari now seeded; the s.175(3) route + victim-side role stand. No swap to FALSE-FIR-AGAINST-ME.
- Open (teammate, post-submission ok): a nursing-mother / woman-dignity specific authority (currently leans on D.K. Basu); a territorial-jurisdiction / zero-FIR authority (currently grounded in Lalita Kumari 111(i)/(iv)).

---

## STEP 4 — Product surface · *9 Sep* ✅ CODE DONE (commit f50f679) — deploy is a manual step for the user
**Exit: a public URL that loads cold and runs all 3 heroes end to end, document download included.** — code side met; the Railway click-through + custom domain is on the user (see `RECOURSE_DEPLOY.md`).

- **One flow:** built as a NEW app `recourse_app.py` (old `app.py` untouched in the repo). One text area + 3 example chips → one result page: stage explainer · trigger-gated rights (each with statute text, the 4-way badge, "how this citation was checked", "in the court's words" excerpt + source link) · negations · police can/cannot · next-24h · red flags · the draft document + PDF download · a "how Recourse works / model never states the conclusion" panel. Serif identity via `.streamlit/config.toml`.
- **Verification badge** — `scenario_verification.py`. `✓ exists · ✓ still good law · ✓ quoted verbatim · ✓ on point`. Honest: only shows GREEN on "still good law" from a curated entry; amber "check currency" otherwise, never a false green.
- **Document** — `scenario_draft.py`, deterministic, no LLM, one template per `paper_type`; lifts days-in-custody / arrest-time / offence from the message, each hedged. Branded PDF.
- **Cold-start** — `@st.cache_resource` `_warm()` at the top of `recourse_app.py` loads the 38 MB embeddings at boot.
- `OUT_OF_SCOPE` → honest refusal card, no document. Verified.
- **Deploy config committed:** `railway.json` + `Procfile` (start cmd), `.python-version`/`runtime.txt` (3.13), `requirements.txt` re-frozen UTF-8 (was UTF-16 + missing bs4/lxml), `.slugignore`/`.railwayignore`, `.gitattributes` (LF for deploy files).
- **`RECOURSE_DEPLOY.md`** — Railway steps + wallet caps + the **custom-domain steps to remove "railway" from the URL** (register `recourse.law`/`.in`, add CNAME on Day 4). Only `ANTHROPIC_API_KEY` + `VOYAGE_API_KEY` needed (no IK key — recourse_app does no live fetch).

**USER TO DO for Step 4:** (1) register a domain (recourse.law / recourse.in); (2) Railway → deploy from repo branch `submission`, add the 2 env keys, set health check; (3) set Anthropic spend cap; (4) add custom domain + CNAME (Day 4); (5) optional UptimeRobot ping + Streamlit Cloud backup URL.

---

## STEP 5 — Writeup + about page · *10 Sep AM*

- **Submission writeup:** problem (undertrials, first 24 hours) → user (accused & family, not firms) → mechanism (stage × role × factors) → the honesty rule → **one** rigor line ("21 automated test files, an eval harness, and a rule that the model never states a legal conclusion") → roadmap.
- **"About" panel** in the app: who it's for · "not legal advice" · "orientation + a starting-point document, then see a lawyer".
- Error states, empty state, mobile check.

---

## STEP 6 — Video + submit · *10 Sep PM*

- **2–3 min video.** Wow in the first 30 seconds. Script = the live-demo script below, compressed. Free-text heroes + the generated document only. Upload **not shown**.
- Full QA on the deployed URL from a clean / incognito browser.
- **Submit on vibecode.law. Don't touch it again.**
- Write the 5-min live-demo script + rehearse once with the teammate (for the last week of September).

## BUFFER — *11 Sep* — breakage only. No new features. **Do not touch it at 4:59 PM.**

---

## Reveal the repo — YES, but curated

Judges from Trilegal / HSF / CAM applied-AI teams **will open the repo**. The code is the single biggest differentiator (21+ test files, two eval harnesses with baselines, deterministic verdict path, "model never states a legal conclusion" architecture).

**FIRST — non-negotiable:** confirm no secrets in git.
```
git log --all --full-history -- .env
git log -p --all | grep -iE "api_key|secret|voyage|sk-ant"
```
Any key ever committed → **rotate it immediately** and publish from a fresh repo with clean history.

**Make a clean public `recourse` repo:** `app.py` (one-flow UI) + the engine (Lane A, Lane B + hybrid search, `draft_layer`, `statute_concordance`, currency, `scenario_router`, `SCENARIO_SPEC`) + `tests/` (all of them — a `pytest` that passes on `git clone` is the flex) + `eval/` (reframed as "how we measure retrieval quality", not "list of open weaknesses"). De-emphasise the domains not demoed and Project 1/2/4 scaffolding.

**Honest-provenance line** (README + writeup):
> The reasoning engine — verified retrieval, no hallucinated citations, IPC↔BNS concordance — I built over the past few months with Claude Code. For this Vibeathon I built the access-to-justice product on top of it: the scenario router, the 14 situation types, the plain-language rights layer, the document generation, and the interface. I didn't start on Tuesday — and that's the point. The hard, unglamorous half was already done properly.

---

## Submission checklist

- [ ] Public URL loads cold in <~15s, runs all 3 heroes
- [ ] Each hero → distinct rights checklist, distinct cases, distinct document
- [ ] Four-way verification badge on every citation
- [ ] Out-of-scope input → honest refusal, visibly
- [ ] IPC→BNS currency point appears once ("old s.420 → new s.318(4); case law still applies")
- [ ] 2–3 min video, wow in 30s, uploaded
- [ ] Writeup: problem / user / mechanism / honesty / one rigor line / roadmap
- [ ] "About / not legal advice" panel
- [ ] Repo link; README names the reused engine + the new routing layer
- [ ] No secrets in git history (checked; keys rotated if needed)
- [ ] Submitted by end of **10 Sep**

---

## Live-demo script — 5 min (shortlist round, last week of Sept)

| Time | Beat |
|---|---|
| 0:00 | **Hook (teammate).** The undertrial number. The 2024 grounds-of-arrest-in-writing ruling. "Their families have never heard of it." |
| 0:30 | **Live input 1 — ARREST-WOMAN.** Walk the rights checklist; point at 3 cases; say *why* each applies to *this* fact. Show the badge. Download the representation, read the line naming the 9:40 PM arrest. |
| 2:15 | **Live input 2 — DEFAULT-BAIL.** "70 days, no chargesheet." Totally different answer, cases, document. "Same tool — it knew this is a different *situation*, not a different question." |
| 3:15 | **The honesty moment.** Out-of-scope input → "I can't help with this." "It says that before it invents a case. That's the entire design." |
| 3:45 | **Rigor + currency.** Model never states the conclusion — that's a checked table. Every quote matched to the judgment. IPC→BNS built in. |
| 4:00 | **(coda) Document upload.** One prepared FIR citing old IPC sections → maps to BNS + flags a procedural gap → "works on the notice, the chargesheet, the remand order too." Show *your* sample; don't invite them to upload. |
| 4:15 | **Roadmap.** More scenarios · regional languages · warm handoff to a real lawyer · the engine behind an API. |
| 4:45 | **Close.** "The others build for the advocate. We build for the person the case is happening to." |

---

## Honest odds

- **Shortlist for the live demo: likely**, if narrow-and-finish is executed.
- **Podium (runner-up / open track): plausible.** A2J angle + verification + a working demo is a strong, distinctive combination.
- **Outright win (₹75k + Trilegal): possible but contested.** Path to first = own the access-to-justice lane so cleanly the judges see you as the best in a category Vaadhan isn't in — not "Vaadhan but smaller."
