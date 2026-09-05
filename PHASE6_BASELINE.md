# Lane B (related judgments) — Phase 6 eval baseline

> **Update 2026-09-05 (commit 1f67374):** Fix 1 (`doctrine_anchors.py` — a
> curated whitelist-topic → canonical-corpus-case map, injected and
> guaranteed a spot at the head of the trusted panel) and Fix 2 (the
> decomposer now ticks a fixed doctrine-tag checklist instead of relying
> on free-prose keyword matching, at temperature 0) are shipped. This
> addresses findings **#1** (LOC landmark unreachable), **#2** (canonical
> case under the display floor), and **#3** (whitelist phrasing gap) — the
> four live cases the baseline left failing now pass, verified live *even
> with Indian Kanoon returning 403s*, because the anchors come from the
> local corpus. Findings #4–#7 and research fixes 3–8 remain open.

---


First full run of `eval_related_judgments.py` against the live pipeline,
2026-09-05. 14 cases, several batches (the harness loads the 38 MB corpus
embeddings, so batches of ~4 keep peak memory down). Indian Kanoon +
Voyage + Anthropic calls; roughly a few tens of rupees of IK credit plus
~40 Sonnet gloss calls total.

**How to reproduce:** `python eval_related_judgments.py` (all 14) or
`--only <id>` per case. Reports land in `eval_related_out/<stamp>/`
(gitignored). The per-case `notes` field in `eval_related_judgments.py`
carries the detailed finding for each failing case.

## Headline

The **safety machinery works**. Every invariant held on every run:

- no bail/interlocutory (`procedural_disposal`) candidate ever reached the
  trusted panel
- when the pipeline found anything, the two panels were never both empty
  (the 2026-09-05 regression stays fixed)
- no displayed gloss carried verdict / "binding" / "settled law" language
- the not-whitelisted cases (property dispute, partnership cheating,
  boundary dispute, bank freeze, night-arrest-no-lady-constable) all
  correctly hid the trusted panel and routed everything to the
  "unverified, you judge it" panel
- gibberish correctly stopped at `no_decomposition`

The **retrieval and ranking quality is the weak point**, and it is
**unstable between runs** (LLM decomposition + Voyage rerank + Sonnet
gloss all vary).

## Findings, most to least serious

### 1. A whitelisted corpus landmark is unreachable by its own doctrine's plain query — CONSISTENT

`loc-igi-airport`: **Viraj Chetan Shah v Union of India** (the LOC case,
in the corpus, whitelisted topic `loc_validity_challenge`) **never
surfaced as a candidate** on any baseline run. The LOC chunks are
framework-heavy ("OM/LOC-framework validity", "Clause 8(j)") and carry no
airport / immigration / detention vocabulary, so "detained at the airport
because of a look out circular" retrieves Prabir / Vihaan / Arnesh Kumar
instead, all glossed "not closely on point". Fix is corpus-side: add a
plain-language chunk (or re-chunk) so the LOC landmark matches how a
person actually describes an LOC detention.

### 2. Canonical corpus judgments score just under the trusted-panel floor — INTERMITTENT

`dk-basu-medical` (D.K. Basu) and `itact-66a-whatsapp` (Shreya Singhal):
the single most important citation for the question surfaces as a
candidate but its `content_score` lands right around the
`_DISPLAY_CONTENT_FLOOR` (0.40–0.42), so on some runs it shows in the
trusted panel and on others it is hidden — and because `for_display` then
has *other* (weaker, HC-recite) content in it, `unverified_for_display`
stays suppressed and the landmark is shown **nowhere**. Candidates:
raise/curve the floor for a verified corpus case, or always admit a
corpus case whose gloss is on point, or fall back to unverified when the
best corpus case is excluded.

### 3. `twenty_four_hour_production` whitelist entry has a phrasing gap — INTERMITTENT

`not-produced-in-24h`: when `decompose_situation` phrases the issue as
"failure to produce ... within mandatory time limit" (no literal "24
hours"), it does not match the `twenty_four_hour_production` patterns, so
`show_user` comes back False and the whole trusted panel is suppressed
for a settled-law question. Add patterns for "produce/produced before
(a) magistrate within [a] mandatory/statutory time limit".

### 4. `default_bail` is a whitelisted topic with no corpus judgment

`default-bail-75-days`: every candidate came from live IK and none was on
point. Corpus-seeding target — Bikramjit Singh Bansal / Rakesh Kumar Paul
/ M. Ravindran.

### 5. Live dedup misses

`default-bail-75-days` (one IK case ×3) and `loc-igi-airport` /
`opposed-bail-three-months` (one IK case ×2) showed the same judgment
multiple times in the ranked list. `_judgment_identity` / `_merge_ranked`
dedups by tid-or-title; the duplicates likely carry different tids for
the same case, or the final IK list is assembled past the dedup point.

### 6. The finality filter does not catch *reasoned* bail orders

`opposed-bail-three-months` pulled real HC bail orders to ranks #1 and #3
("bail granted with conditions") and `classify_document_finality` flagged
neither — because a modern HC bail order has a real Analysis section, so
it fails the (no-reasoning-structure AND disposal-phrase) conjunction.
Harmless where the question is not whitelisted (unverified panel only),
but a risk for a whitelisted question that happens to pull one. Revisit
the heuristic for reasoned bail grants.

### 7. Latency and IK flakiness

Case times ranged 11 s – 150 s; the slow ones coincided with Indian
Kanoon `/search` read-timeouts (20 s each, degrades gracefully). The
~20 s target from the Phase-5 speedup is not being met under real IK
load.

## Corpus retrieval misses (lower stakes — these land in the unverified panel a human reads)

- `arnesh-no-notice`: Arnesh Kumar v State of Bihar (in corpus) did not
  surface; Satender Kumar Antil carried the doctrine instead (on-point
  gloss).
- `partnership-cheating`: Vijay Kumar Ghai / Satishchandra (in corpus,
  the right "civil dispute is not cheating" authorities) did not surface.
- `grounds-of-arrest-not-given`: Pankaj Bansal (in corpus) did not
  surface; Vihaan Kumar + Prabir Purkayastha did (enough).

The common thread with finding #1: **the judgment corpus is retrieved by
semantic similarity to the user's plain words, and several landmarks
don't match their own doctrine's plain-language description well.** This
is the biggest single lever for Lane B answer quality.

## What passed cleanly every run

`fir-copy-refused`, `grounds-of-arrest-not-given`, `arnesh-no-notice`,
`property-dispute-fir`, `boundary-dispute-arrest`, `bank-account-frozen`,
`night-arrest-woman-no-lady-constable`, `opposed-bail-three-months`,
`gibberish-no-situation`, `partnership-cheating`.
