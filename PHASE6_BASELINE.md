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
>
> **Update 2026-09-06 (Fix 4):** finding **#4** closed. Added three
> default-bail Supreme Court landmarks to the corpus — **M. Ravindran v
> Intelligence Officer, DRI** (2021) 2 SCC 485, **Bikramjit Singh v State
> of Punjab** (2020) 10 SCC 616, **Rakesh Kumar Paul v State of Assam**
> (2017) 15 SCC 67 (9 curated `curated_excerpt` chunks, all
> component-verified verbatim, embedded). `DOCTRINE_ANCHOR_CASES["default_bail"]`
> now anchors Ravindran → Bikramjit (Rakesh Kumar Paul is embedded and
> retrievable but not a guaranteed-display anchor). Live eval of
> `default-bail-75-days`: `show_user=True`, both anchors lead the ranked
> list (scores 1.02 / 0.96) and display, glosses on point, every invariant
> held. `test_doctrine_anchors` / `test_related_judgments` /
> `test_eval_related_judgments` updated (the "whitelisted but nothing
> clears the floor" regression guard now suppresses anchor injection,
> since no whitelist topic is anchor-less any more). Findings #5-#7 and
> research fixes 3-8 remain open.
>
> **Update 2026-09-06 (Fix: hybrid corpus search):** Lane B's corpus
> candidate pool is now retrieved **two ways** - `semantic_search`
> (meaning) plus `semantic_retrieval.lexical_search` (Okapi BM25, pure
> Python, no new dependency) - rank-fused via RRF in
> `semantic_retrieval.hybrid_search`, wired into
> `related_judgments.corpus_candidates`. Recall only: `fetch_and_pin`'s
> Voyage rerank is still the authoritative ranker for what displays.
> Live re-run of the four affected cases (0 check failures): **finding
> #2 improved** - a "Section 66A" question now ranks Shreya Singhal
> `0.664` at the head of the ranked list (baseline ~0.44, under the
> floor, hidden ~half the runs); **`loc-igi-airport`** - Viraj Chetan
> Shah now enters the pool as a genuine corpus candidate (`0.51`,
> displayed) rather than never surfacing. Lexical false-friends (NALSA
> on "partner"/"medical") never reached `for_display` - the downstream
> rerank + floor filtered them, as designed. Also a free resilience
> win: if Voyage is down, `hybrid_search` returns the lexical results
> alone instead of an empty panel. **Finding #1 is only partly helped**
> - Viraj Chetan Shah's chunks genuinely lack "airport"/"immigration"
> vocabulary, so pure layman phrasing still needs the corpus-side
> plain-language chunk (Fix 5). `test_hybrid_search.py` added. Lane A's
> `find_relevant_sections` (the verified answer path) is deliberately
> **not** switched to hybrid - that needs its own `eval_chat_answers`
> run and ships separately.

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

> **Partly addressed (2026-09-06):** hybrid corpus search + the Fix 1
> doctrine anchor now get Viraj Chetan Shah into the pool and onto the
> panel for `loc-igi-airport`. But the *retrieval* weakness this finding
> names is real and unfixed — BM25 can't match "airport"/"immigration"
> against a chunk that doesn't contain those words. The corpus-side
> plain-language chunk (Fix 5) is still the right fix for the
> retrieval-only path.

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

> **Improved (2026-09-06):** Fix 1's doctrine anchor already guarantees
> both these landmarks display. On top of that, hybrid corpus search
> lifts a "Section 66A" question's Shreya Singhal to `0.664` at the head
> of the ranked list (well clear of the floor) because the chunk
> contains the literal string "Section 66A". D.K. Basu likewise benefits
> when the query names it. The floor-tuning ideas above are no longer
> urgent.

### 3. `twenty_four_hour_production` whitelist entry has a phrasing gap — INTERMITTENT

`not-produced-in-24h`: when `decompose_situation` phrases the issue as
"failure to produce ... within mandatory time limit" (no literal "24
hours"), it does not match the `twenty_four_hour_production` patterns, so
`show_user` comes back False and the whole trusted panel is suppressed
for a settled-law question. Add patterns for "produce/produced before
(a) magistrate within [a] mandatory/statutory time limit".

### 4. `default_bail` is a whitelisted topic with no corpus judgment — CLOSED (Fix 4, 2026-09-06)

`default-bail-75-days`: every candidate came from live IK and none was on
point. **Fixed** by seeding the corpus with M. Ravindran v Intelligence
Officer DRI, Bikramjit Singh v State of Punjab, and Rakesh Kumar Paul v
State of Assam (9 chunks), and anchoring `default_bail` to Ravindran →
Bikramjit. Re-run 2026-09-06: both anchors lead the panel and display.

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
