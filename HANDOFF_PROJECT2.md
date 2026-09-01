# Know Your Rights (KYR) -- Handoff: Project 1 Complete, Starting Project 2

## What this project is

A deterministic legal-compliance-checking tool for Indian criminal
procedure (BNS/BNSS), built by a non-CS-background developer
transitioning into legal tech. Four-project roadmap:

1. **Project 1 (COMPLETE, this handoff)** -- Know Your Rights core engine.
2. **Project 2 (STARTING NOW)** -- Legal-Currency Verification Agent.
3. **Project 3** -- Bounded-Action/Compliance-Drafting Layer.
4. **Project 4 (Capstone)** -- Know Your Rights MCP Server.

## THE ONE NON-NEGOTIABLE ARCHITECTURAL PRINCIPLE

Deterministic Python decides every legal verdict. The LLM only
extracts facts from text/conversation and phrases already-decided
results in plain language. The LLM NEVER decides a verdict or a
citation applies.

Two sub-principles proven necessary in practice this session:

- Never silently convert an inferred fact into a confidently-cited
  legal conclusion the person never actually stated. Example: a
  person whose bank account is frozen typically does not know which
  BNSS section (106 vs 107) was invoked. The fix
  (check_freeze_authorization_inferred in main.py) reads only
  observable facts and caps its own confidence -- Compliant only on
  strong positive signal, "May be Non-Compliant" (never a hard
  "Non-Compliant") on absence of signal, "Cannot Determine" when
  genuinely unclear.
- Never trust a legal claim, even a confident one, without verifying
  it against a real fetched primary source first. This session caught
  TWO real self-introduced errors: a fabricated "security cheque,
  contingent liability" holding wrongly attributed to Kaveri Plastics
  v Mahdoom Bawa Bahrudeen Noorul (the actual judgment contains ZERO
  occurrences of "security", "matured", or "contingent" anywhere in
  40,710 characters), and a "friendly loan doesn't defeat the
  presumption" claim wrongly attributed to Bir Singh v Mukesh Kumar
  (the phrase appears only in the facts recitation, never as a Court
  holding). Both caught by re-reading real primary text before
  shipping -- directly load-bearing for Project 2's own purpose.

## Current state: three domains, each with three entry points

Every domain has document-upload, a button-based guided interview, and
a free-text conversational interview, all three funneling into the
SAME deterministic compliance functions.

### Domain 1: Arrest (BNS/BNSS arrest procedure)

- 8 checks in run_arrest_compliance_checks (main.py): Arnesh Kumar
  notice, cognizable-arrest basis, written grounds (Vihaan Kumar),
  D.K. Basu memo/witness/family/medical, night-arrest-of-woman,
  female-officer-involvement, 24-hour-production, default-bail.
- Free-text flow: interview_flow.py. Identifies offence via semantic
  search, MANDATORY confirmation gate, and for HIGH-SEVERITY offences
  (dowry death, murder, attempt to murder) a stricter fact-based gate
  (HIGH_SEVERITY_CONFIRMATION_GATE) -- built after a CONFIRMED
  SERIOUS BUG where "my wife has filed a dowry case" (a LIVING wife's
  ongoing complaint) was matched to Section 80 (dowry DEATH,
  mandatory minimum 7 years to life) on vocabulary overlap alone.
  Single most important lesson for Project 2: semantic similarity is
  not legal correctness.
- Tiered questions (5 critical, 5 optional) after confirmed real user
  frustration with longer interviews.
- Regression suite: test_interview_flow.py (20 checks).

### Domain 2: Bank-Account Freezing (BNS/BNSS 106/107)

- 4 checks in run_freeze_compliance_checks: check_freeze_section_and_scope,
  check_freeze_magistrate_intimation, check_freeze_107_court_order
  (only when section_invoked is DIRECTLY known), check_freeze_holder_intimation
  (post-freeze notification -- BNSS does not require advance notice).
- Sourced/verified: State of Maharashtra v Tapas D. Neogy (1999) 7
  SCC 685 [SC, foundational], Neelkanth Pharma Logistics v Union of
  India (Delhi HC, 2025) [proportionality strand], Malabar Gold and
  Diamond Limited v Union of India (Delhi HC, 2026) [S.106/107
  textual strand].
- Free-text flow: freeze_interview_flow.py. NO offence/section ID
  step -- per explicit user confirmation the person typically doesn't
  know which section applies. Asks about observable facts, feeds
  check_freeze_authorization_inferred (main.py), which never claims
  certainty about which section was invoked.
- CONFIRMED REAL BUG fixed: check_freeze_section_and_scope treated the
  string "unclear" as a real amount, producing "Rs. unclear" in a
  live conversation. Fixed.
- Regression suite: test_freeze_compliance.py (15 checks). NOTE: tests
  compliance functions directly, NOT freeze_interview_flow.py's own
  state machine -- that has no dedicated suite yet (deferred).

### Domain 3: Cheque Bounce (Section 138 NI Act)

- 4 checks in run_compliance_checks: check_30_day_window,
  check_amount_match (corrected), check_15_day_payment_window,
  check_jurisdiction (new).
- check_enforceable_debt RETIRED entirely (was legally backwards --
  treated enforceability as a flat pass/fail fact). Replaced with
  explain_debt_presumption_status (informational only, never a
  verdict, same pattern as compute_bail_pathway_info).
- Sourced/verified 5 Supreme Court judgments, each READ IN FULL:
  1. Rangappa v Sri Mohan, (2010) 11 SCC 441 -- S.139 presumption
     mandatory, covers debt existence, preponderance-of-probabilities
     rebuttal. Paras 14, 34.
  2. Bir Singh v Mukesh Kumar, (2019) 4 SCC 197 -- blank cheque still
     attracts the presumption. Para 40. (An initial draft also
     attributed a "friendly loan" holding here -- CONFIRMED WRONG,
     removed.)
  3. Damodar S. Prabhu v Sayed Babalal H, (2010) 5 SCC 663 --
     graduated compounding-cost scheme (~10/15/20%). Para 15. Feeds
     compute_settlement_cost_incentive (informational).
  4. Kaveri Plastics v Mahdoom Bawa Bahrudeen Noorul (SC, 2025) --
     notice must specifically/severably state the correct cheque
     amount; co-mention of interest is not fatal, an actual amount
     MISMATCH is. Para 14 (quotes Suman Sethi v Ajay K. Churiwal,
     (2000) 2 SCC 380 verbatim -- Suman Sethi's own judgment never
     separately fetched). (An initial draft attributed a SEPARATE
     "security cheque, contingent liability" holding to this same
     case -- CONFIRMED WRONG on full re-read, zero occurrences of the
     relevant terms in the real text. Retracted, no function built on
     the false holding.)
  5. Prakash Chimanlal Sheth v Jagruti Keyur Rajpopat, 2025 INSC 897
     -- complaint must be filed where the cheque was presented for
     collection (S.142(2), Dashrath Rupsingh Rathod). Paras 7-8.
- Free-text flow: cheque_bounce_interview_flow.py. No offence/section
  ID needed at all -- every conversation is a Section 138 matter.
  8 questions. FLAGGED: case_stage defaults to "pre_trial" (not asked
  in this flow) -- a real, bounded gap if the user is mid-appeal.
- Regression suite: test_cheque_bounce_compliance.py (19 checks,
  includes explicit regression tests for both self-corrections above).

## Infrastructure built this session, reusable for Project 2

- indiankanoon_client.py -- authenticated Indian Kanoon API wrapper
  (/search/, /doc/, /docmeta/). Real key in .env, real cost per call.
- ik_text_cleaner.py -- parses IK's HTML format (different shape from
  PDF-extracted text) into the standard corpus record shape.
- chunk_judgments.py, embed_corpus.py -- unchanged, now proven to work
  on IK-sourced documents too. embed_corpus.py confirmed incremental/
  append-only, safe to re-run.
- judgment_qa.py -- CONFIRMED to produce FALSE POSITIVES on IK-HTML
  documents (caption/closing patterns calibrated for the PDF path).
  Two documents this session were flagged as "unrecognised" but direct
  inspection confirmed both are genuine, complete real text. Worth
  extending this tool's patterns if more IK-sourced judgments are added.
- Corpus now at 1,595 total embedded chunks (was 1,409 before this
  session's Indian Kanoon sourcing work).

## Explicitly tracked open items -- do not lose these

1. Common intention / joint liability (BNS Section 3(5)) is entirely
   unaddressed by the arrest module. Concrete trigger scenario logged:
   a passenger in a car during a suspected theft, driver flees,
   passenger arrested and charged with theft -- no doctrine covers
   "mere presence vs. actual participation." Needs sourcing.
2. Security/maturity doctrine for cheque bounce is NOT resolved -- the
   false Kaveri Plastics attribution was retracted, not replaced. A
   real case may exist but has not been located/verified. (2026-09-01:
   the false attribution was still lingering in two corpus/builder
   notes fields; now fully scrubbed -- see item 7.)
3. The Pawan Kumar Rai / Sajir / Saifullah citation chain, referenced
   inside Neelkanth Pharma Logistics' own text, was never independently
   sourced/verified.
4. No dedicated regression suite exists yet for freeze_interview_flow.py
   or cheque_bounce_interview_flow.py's own state-machine/extraction
   logic (the underlying compliance functions ARE covered).
5. A formal "stress-test log" is EXPLICITLY DEFERRED per direct user
   instruction: "remind me to complete it after project 2 and project
   3 are completed. Currently we are out of time." Do NOT raise this
   again until the user confirms Projects 2 and 3 are done.
6. citation_currency_checker.py (Project 2 Step 3) built and run against
   all 14 doctrine_keys 2026-09-01. Case-law-treatment dimension now
   verified for ALL 14 (youth_bar closed by adding doctrine-phrase
   queries: ik_query_builder.CASE_METADATA entries now support an
   'extra_search_queries' list; build_doctrine_queries pools them).
   RESOLVED this session:
   - D.K. Basu citation conflict: the sourced corpus text (IK doc
     235756) is the SHORT 1 Aug 1997 monitoring order, (1997) 6 SCC 642,
     which QUOTES the 11 safeguards verbatim from the substantive 18 Dec
     1996 judgment, (1997) 1 SCC 416. corpus record + chunk header +
     build_judgment_corpus.py comment corrected: citation = (1997) 1 SCC
     416 (the standard reference), source_document_citation records the
     1997 order, source_type = "primary_reproduction". NO retrieval text
     changed (the requirement wording is verbatim-faithful and chunks
     cleanly; the 1996 judgment numbers them "(1)".."(11)" and would
     need a manual_override_text hack, so it was NOT re-sourced).
   - Kaveri Plastics fabricated holding: corpus notes AND
     build_cheque_bounce_judgment_corpus.py still asserted a
     "SECURITY/MATURITY HOLDING" feeding a check_debt_maturity_status
     function (never built). Text has ZERO occurrences of security/
     matured/contingent -- re-confirmed by grep, scrubbed from both
     files. Real citation 2025 INSC 1133 applied.
   - Citation upgrades applied to corpus + chunk headers + builders:
     Neelkanth = 2025 SCC OnLine Del 1055 (docket kept as
     source_document_citation; "OnLine" form inferred from a citing
     judgment's "2025 SCC Del 1055"); Malabar Gold = 2026 SCC OnLine
     Del 297 (confirmed against a citing judgment); Kaveri = 2025 INSC
     1133. retrieval.py surfaces chunks[0]["citation"], so these are
     now what the chat feature attributes.
   STILL OPEN:
   - Vihaan Kumar: a larger-bench reference is pending (as of mid-2025)
     on whether written grounds of arrest are required in EVERY case.
     Core holding "holds the field" meanwhile; the arrest module's
     written-grounds check still stands, but re-check when the larger
     Bench reports.
   - The corpus embeddings were NOT regenerated after these metadata
     edits. Not needed (no chunk TEXT changed, only header citation
     fields), but embed_corpus.py should be re-run before the next
     release regardless, for cleanliness.
7. Item 2 above (Kaveri Plastics security/maturity doctrine): the real
   Kaveri Plastics judgment is 2025 INSC 1133 (SC affirming Delhi HC),
   about NOTICE-AMOUNT MISMATCH, not security/maturity. Later HCs
   distinguish it on facts (demand less than vs. more than the cheque).
   The separate security-cheque/contingent-liability holding the
   retracted attribution claimed still has NO located source -- item 2
   remains genuinely open, but the false trail is now fully scrubbed
   from the corpus and builder (was still lingering in notes fields).

## What Project 2 actually is

Legal-Currency Verification Agent: checks whether a citation is still
good law before it's used/surfaced. A direct extension of the
discipline this session already required by hand -- Project 2's job is
making that verification systematic, not a one-time manual check.
Likely concretely means: given a citation already in the corpus, check
whether it's been overruled, distinguished, or superseded by later
legislation (e.g. BNS/BNSS superseding IPC/CrPC citations already in
the corpus -- Tapas D. Neogy was decided entirely under old Section
102 CrPC, and its continued relevance depends on courts treating it as
the doctrinal ancestor of BNSS 106/107, which Malabar Gold's reasoning
does -- but this should be an explicit, checked fact, not an assumption).

## Real, honest self-assessment carried into Project 2

This session's discipline caught two real fabricated legal claims
before they shipped, plus multiple real code bugs. The lesson for
Project 2, stated directly: verification only works if it's actually
performed, every time, against real primary sources -- confidence,
however articulate, is not a substitute for checking. Project 2 exists
to make this project's own demonstrated discipline systematic rather
than dependent on a human or an LLM remembering to do it by hand.
