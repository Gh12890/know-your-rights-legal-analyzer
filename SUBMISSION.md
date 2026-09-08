# Recourse — ILTN Vibeathon 2026 submission

**Live:** https://recourse.co.in  ·  **Backup:** https://recourse.up.railway.app
**Repo:** this repository  ·  **Tagline:** *An arrest. An FIR. A night in custody. You have more rights than you know — and the paper to use them.*

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

1. **Works out the situation** — not "answer this legal question" but *who you are × what stage you are at × what specific things have happened* (a woman, arrested, after sunset, no grounds given, a nursing mother — that is four different facts, and each pulls a different right and a different case).
2. **Returns only the rights those facts raise** — each with its section of the BNS/BNSS, one real judgment, and what the police can and cannot do at this stage.
3. **States what your situation does *not* raise** — ruling things out is the strongest signal that the specific facts were understood.
4. **Generates a first-draft document** — a representation to the Magistrate, a default-bail application, a Section 175(3) complaint — with the arrest time and dates lifted from your own account, ready to hand to a lawyer or a Legal Services Authority.

## The honesty rule

**The language model is never allowed to state the legal conclusion.** It has three jobs: classify which situation your message describes, and phrase explanations in plain words. The rights, the section numbers, the cases, the verdicts and the document all come from a hand-checked library and fixed Python rules.

Every citation is checked four ways and the result is shown on the page:
**✓ it exists** in the checked library · **✓ still good law** · **✓ quoted verbatim** from the judgment · **✓ mapped to your right by a person, not a similarity score.**
Where a check cannot be satisfied, Recourse shows an amber "read it yourself" — never a false green tick. When a situation is outside its scope, it says so plainly rather than guessing.

## One line on rigour

22 automated test files that pass on `git clone`, two live evaluation harnesses with recorded baselines, a 39-judgment corpus where every excerpt was verified verbatim against the primary judgment at ingest, and an IPC→BNS/CrPC→BNSS concordance so old case law is mapped to the new codes. The discipline is the product.

## How it was built

The verification engine — checked retrieval, the IPC→BNS mapping, the "model never states the conclusion" architecture — was built over several months with Claude Code. For this Vibeathon I built the access-to-justice product on top of it: the situation router, the situation catalogue, the plain-language rights layer, the document generator, and the interface. The hard, unglamorous half was already done properly — and that is the point.

## Roadmap

- More situations (custodial violence, Look-Out Circulars, false-FIR quashing — the router already recognises them; the content layer follows).
- Regional-language output — the citizens least served by existing tools are the ones least served by English-only findings.
- A warm handoff to a real lawyer / the nearest District Legal Services Authority.
- The engine behind an API (an MCP server) so other tools can build on the verification layer.

## Disclaimer

Recourse gives legal information and a starting-point document, **not legal advice**. It cannot see anything beyond what you type. For a real case, the next step is always a qualified advocate; the District Legal Services Authority provides that help free.
