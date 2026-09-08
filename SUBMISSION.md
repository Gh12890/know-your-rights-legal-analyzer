# Recourse — ILTN Vibeathon 2026 submission

**Live:** https://recourse.co.in  ·  **Backup:** https://recourse.up.railway.app
**Repo:** this repository  ·  **Tagline:** *An arrest. An FIR. A night in custody. You have more rights than you know — and the law to back them.*

---

## The problem

More than three-quarters of India's prison population are **undertrials** — people not convicted of anything. When the police arrive, the decisions that matter are made in the first 24 hours, and the people in the room usually do not know that:

- an arrest must come with the **grounds of arrest**, communicated in a way the person can actually respond to;
- a woman ordinarily **cannot be arrested between sunset and sunrise**;
- for an offence up to 7 years, the police are expected to serve a **notice to appear**, not arrest straight away;
- once the **60- or 90-day chargesheet deadline** passes, bail stops being discretionary and becomes a right.

These rights exist on paper and are lost in practice, because no lawyer is in the room and the family has never heard of them.

## Who it is for

**The person the case is happening to, and their family — at the moment it is happening.** Not law firms. Every other legal-AI tool in this space builds for the advocate. This one is built for the person in the lock-up's family, standing outside a police station at 11 pm.

## What it does

You type what is happening, in plain words. Recourse:

1. **Checks scope first** — if this is not about an arrest, an FIR, police procedure or bail under the BNS/BNSS, it says so plainly and points you to a lawyer, rather than guessing an answer.
2. **Retrieves the law that actually applies** — the matching sections of the BNS and BNSS and the real Supreme Court / High Court judgments, from a fixed hand-checked library, never the model's own knowledge. When you name an accusation in plain words ("they said I stole a goat"), it anchors the exact offence — Section 303, its punishment, the carve-outs — instead of hoping a similarity score ranks it first.
3. **Answers in the shape a frightened person needs** — a short **what to do right now**, then the exact law, then **what is still unclear** (the facts that change the answer), then one next step.
4. **Checks the actual papers** — where an arrest has happened, you can upload the arrest memo, FIR or remand order and Recourse checks each safeguard against what the document says, with fixed rules, not the AI.

## The honesty rule

**The language model is never allowed to state a verdict on your case.** It classifies scope and phrases the retrieved law in plain words — nothing more. The sections, the judgments, the punishment tiers and the compliance verdicts all come from a hand-checked library and fixed Python rules.

Before you see it, the plain-language answer is **screened for anything the library does not support** — a section number that was never retrieved, a wrong cognisable/bailable claim, a judgment stretched past what it holds. Where a section has been **renumbered** from the old codes, or a judgment's standing is **uncertain**, Recourse says so on the page. Every section and judgment the answer rests on is shown, in full, under "Read the source." When a question is outside its scope, it says so plainly rather than guessing.

## One line on rigour

22 automated test files that pass on `git clone`, two live evaluation harnesses with recorded baselines, a 39-judgment corpus where every excerpt was verified verbatim against the primary judgment at ingest, and an IPC→BNS/CrPC→BNSS concordance so old case law is mapped to the new codes. The discipline is the product.

## How it was built

The engine — scope classification, checked retrieval over the BNS/BNSS and a verified judgment corpus, the offence-keyword anchors, the IPC→BNS mapping, the ungrounded-statement screens, the "model never states a verdict" architecture — was built over several months with Claude Code. For this Vibeathon I built the access-to-justice product on top of it: the single-question interface, the plain-language framing for a non-lawyer in a crisis, and the one-click check of the actual arrest papers. The hard, unglamorous half was already done properly — and that is the point.

## Roadmap

- More offence coverage and more of the arrest/FIR/bail situations, verified the same way.
- Regional-language output — the citizens least served by existing tools are the ones least served by English-only findings.
- A warm handoff to a real lawyer / the nearest District Legal Services Authority.
- The engine behind an API (an MCP server) so other tools can build on the verification layer.

## Disclaimer

Recourse gives legal information, **not legal advice**. It cannot see anything beyond what you type. For a real case, the next step is always a qualified advocate; the District Legal Services Authority provides that help free.
