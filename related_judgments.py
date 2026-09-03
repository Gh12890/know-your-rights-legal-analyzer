"""
related_judgments.py

Lane B of the chat feature: AFTER the deterministic grounded answer is
produced, find real court judgments whose SITUATION resembles what the
user described, so the user can read them.

ARCHITECTURE NOTE -- READ BEFORE EXTENDING (this is the whole point):
This module runs entirely to the SIDE of the grounded-answer path. Its
output is NEVER passed to generate_grounded_response(), never merged into
retrieved_text, never changes a state or a verdict. If anything here
fails -- the classifier, Indian Kanoon, the reranker, the network -- the
grounded answer the user already has is exactly what it would have been
anyway. The design doc for this lane:
    https://claude.ai/code/artifact/f04966df-f0f2-4799-a38f-04b687beee6e

The pipeline (this file builds it phase by phase):
  1. decompose_situation()  -- LLM EXTRACTION ONLY: break the user's
     message into its discrete legal issues + verbatim fact hooks. This
     is the same category of work as analyze_document()'s field
     extraction or interview_flow's offence identification -- it decides
     NO section and NO verdict, and every hook it emits is checked back
     against the user's own words (_hook_phrase_in_text) before it is
     trusted.
  2. build_anchors()        -- pure Python: per issue, resolve the BNS/
     BNSS section hooks to the IPC/CrPC numbers Indian Kanoon is actually
     indexed under (statute_concordance), and carry the verbatim hook
     phrase.
  3. (later phases) multi-query search -> rerank against the full
     message -> whitelist gate -> fetch + pin paragraphs -> one bounded
     gloss -> verbatim-substring verification -> render.

PHASE 0 (this commit) implements steps 1 and 2 only, plus the CLI is not
wired yet. Nothing here calls Indian Kanoon or costs IK credits.
"""

import json
import logging
import os
import re
from datetime import date, datetime, timezone

logger = logging.getLogger("related_judgments")

# Same model string as every other Haiku call site in this project
# (main.py, interview_flow.py, chat_assistant.classify_scope, ...).
_HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Resolve the Anthropic client the same way chat_assistant.py does: reuse
# main's client when importable (real app + most tests), else None. Tests
# patch this symbol directly (`patch("related_judgments.client")`).
try:
    from main import client
except Exception:  # ImportError, or main failing to import in a bare test env
    client = None


# How many issues we act on. A person's message usually has 2-4 real
# distinct grievances; past that the searches fan out into noise. The
# decomposition prompt is told the same number.
MAX_ISSUES = 4


# ---------------------------------------------------------------------------
# SITUATION_DECOMPOSITION_PROMPT
#
# Extraction only. The model is NOT asked which law applies or whether
# anything was done wrongly -- only to name, in the user's own terms, the
# separate things the user is complaining about, each with a short phrase
# lifted VERBATIM from their message. build_anchors + the rest of the
# pipeline decide what to do with those; _hook_phrase_in_text throws away
# any issue whose hook the user did not actually say.
# ---------------------------------------------------------------------------
SITUATION_DECOMPOSITION_PROMPT = """You are helping a legal-information tool find relevant Indian court judgments for someone describing a criminal-law situation (arrest, FIR, police procedure, bail).

Break their message into its SEPARATE legal issues -- the distinct things that have happened or that they are worried about. Do NOT decide which law applies, whether anything was done unlawfully, or what the outcome should be. Only identify and name the issues.

Return ONLY a JSON object, no other text:
{{
  "primary_grievance": "one short sentence naming the single most important thing they want help with",
  "procedural_stage": "where things stand now, in a few words (e.g. 'arrested, pre-chargesheet, ~2 months' or 'FIR registered, no arrest yet' or 'unknown')",
  "issues": [
    {{
      "issue": "a short neutral description of one distinct legal issue (e.g. 'arrest of a person not named in the FIR', 'grounds of arrest not communicated', 'chargesheet not filed within the time limit', 'alleged assault in custody')",
      "hook_phrase": "3 to 8 words copied VERBATIM from the user's message that show this issue -- must be an exact substring of their text",
      "section_hooks": ["any BNS or BNSS section, or well-known safeguard, that this issue is about -- e.g. 'BNSS 35', 'BNSS 187', 'Article 22(1)', 'D.K. Basu'. Empty list if none is obvious."]
    }}
  ]
}}

Rules:
- At most {max_issues} issues. If there are more, keep the {max_issues} most important.
- Order issues by importance, most important first.
- "hook_phrase" MUST be an exact run of words from the user's message. Do not paraphrase it. If you cannot find an exact phrase for an issue, do not include that issue.
- If the message describes only one thing, return one issue.
- "section_hooks" is your best guess at the relevant provision names for searching -- it is not a legal opinion and an empty list is fine.

User's message:
{user_message}"""


def _extract_text_from_response(response):
    """Safely pull text out of an Anthropic response regardless of block
    order or the presence of a leading ThinkingBlock. Same helper the
    rest of this project copies into each module (chat_assistant.py,
    freeze_interview_flow.py, main.py) -- kept local so this module has
    no import dependency on them."""
    text_block = next(
        (b for b in getattr(response, "content", []) if hasattr(b, "text")), None
    )
    if text_block is None:
        raise ValueError("No text block in response.content")
    return text_block.text


_WORD_RE = re.compile(r"[a-z0-9]+")
# Words too common to count toward a hook-phrase match -- if a "verbatim"
# hook only overlaps the user's text on these, it isn't really grounded.
_HOOK_STOPWORDS = frozenset("""
a an the this that these those and or but if of to in on at by for with as
is are was were be been being he she it they them his her their my our your
i we me us you not no nor so then than there here have has had do does did
about after over under from into out up down was were will would can could
police station court case day days month months year years time
""".split())


def _normalise(text):
    return _WORD_RE.findall((text or "").lower())


def _hook_phrase_in_text(hook_phrase, user_message):
    """True when `hook_phrase` is genuinely drawn from `user_message`.

    Deterministic, deliberately generous about punctuation/spacing but
    strict about content: a substring match after normalisation, OR every
    non-stopword token of the hook present in the user's text. An issue
    whose hook fails this check is dropped -- the model was told to copy
    verbatim, and we do not act on an issue the user did not raise.
    """
    if not hook_phrase or not user_message:
        return False

    hay = " ".join(_normalise(user_message))
    needle = " ".join(_normalise(hook_phrase))
    if not needle:
        return False
    if needle in hay:
        return True

    hay_set = set(hay.split())
    content_tokens = [t for t in needle.split() if t not in _HOOK_STOPWORDS]
    if not content_tokens:
        return False
    return all(t in hay_set for t in content_tokens)


def decompose_situation(user_message):
    """Break a free-text situation into its discrete legal issues.

    Returns a dict:
        {
          "primary_grievance": str,
          "procedural_stage": str,
          "issues": [ {"issue": str, "hook_phrase": str,
                       "section_hooks": [str, ...]}, ... ]   # 1..MAX_ISSUES
        }
    or None if the model is unavailable, the response can't be parsed, or
    no issue survives the hook-phrase check. None is an honest "could not
    decompose" -- callers fall back to whole-message retrieval, never
    treat it as an error.

    LLM EXTRACTION ONLY. No legal judgement is made here; see the module
    and prompt docstrings.
    """
    if client is None:
        return None
    if not user_message or not user_message.strip():
        return None

    try:
        response = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=900,
            messages=[{
                "role": "user",
                "content": SITUATION_DECOMPOSITION_PROMPT.format(
                    user_message=user_message, max_issues=MAX_ISSUES
                ),
            }],
        )
        raw = _extract_text_from_response(response).strip()
    except Exception:
        logger.exception("decompose_situation: model call failed")
        return None

    # Strip a ```json ... ``` fence if the model adds one despite the
    # "ONLY a JSON object" instruction (same defensive step classify_scope
    # takes).
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("decompose_situation: could not parse model JSON: %r", raw[:300])
        return None

    if not isinstance(parsed, dict):
        return None

    raw_issues = parsed.get("issues")
    if not isinstance(raw_issues, list):
        return None

    issues = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        issue_text = (item.get("issue") or "").strip()
        hook = (item.get("hook_phrase") or "").strip()
        hooks = item.get("section_hooks")
        if not isinstance(hooks, list):
            hooks = []
        hooks = [str(h).strip() for h in hooks if str(h).strip()]

        if not issue_text or not hook:
            continue
        if not _hook_phrase_in_text(hook, user_message):
            logger.info("decompose_situation: dropped issue with unverified hook %r", hook)
            continue

        issues.append({"issue": issue_text, "hook_phrase": hook, "section_hooks": hooks})
        if len(issues) >= MAX_ISSUES:
            break

    if not issues:
        return None

    return {
        "primary_grievance": (parsed.get("primary_grievance") or "").strip(),
        "procedural_stage": (parsed.get("procedural_stage") or "unknown").strip() or "unknown",
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Anchor building -- pure Python, no LLM, no network.
# ---------------------------------------------------------------------------

# "BNSS 35", "BNS 318(4)", "Section 187 BNSS", "s.35 BNSS" -> (act, number)
_SECTION_HOOK_RE = re.compile(
    r"\b(?P<act1>BNSS|BNS)\b[^\d]{0,12}(?P<num1>\d{1,3}[A-Z]{0,2})"
    r"|\b(?:section|sec\.?|s\.?)\s*(?P<num2>\d{1,3}[A-Z]{0,2})[^\w]{0,4}\b(?P<act2>BNSS|BNS)\b",
    re.IGNORECASE,
)


def _parse_section_hook(hook):
    """'BNSS 35' -> ('BNSS', '35'); 'BNS 318(4)' -> ('BNS', '318');
    'Article 22(1)' / 'D.K. Basu' -> None (not a BNS/BNSS section)."""
    m = _SECTION_HOOK_RE.search(hook or "")
    if not m:
        return None
    if m.group("act1"):
        return m.group("act1").upper(), m.group("num1")
    return m.group("act2").upper(), m.group("num2")


def build_anchors(profile):
    """Turn a decompose_situation() profile into per-issue search anchors.

    For each issue returns:
        {
          "issue": str,
          "hook_phrase": str,
          "new_sections": ["BNSS 35", ...],      # the BNS/BNSS hooks, cleaned
          "old_sections": ["CrPC 41", "IPC 420", ...],  # concordance equivalents
          "doctrine_hooks": ["Article 22(1)", "D.K. Basu", ...],  # non-section hooks, kept verbatim
        }

    The old-section resolution is the point: Indian Kanoon's corpus is
    overwhelmingly indexed under IPC/CrPC numbers (BNS/BNSS are ~2 years
    old), so a section-anchored search needs the pre-2024 number. This is
    the "Option A" ik_query_builder.py's header describes as unblocked.

    Pure lookup via statute_concordance -- a concordance hit is a pointer
    to search on, never asserted as an identity (see that module's
    docstring). Returns [] for a falsy/Shapeless profile.
    """
    from statute_concordance import to_old

    if not profile or not isinstance(profile, dict):
        return []

    anchors = []
    for issue in profile.get("issues", []):
        new_sections, old_sections, doctrine_hooks = [], [], []
        seen_old = set()

        for hook in issue.get("section_hooks", []):
            parsed = _parse_section_hook(hook)
            if parsed is None:
                if hook not in doctrine_hooks:
                    doctrine_hooks.append(hook)
                continue

            act, num = parsed
            label = f"{act} {num}"
            if label not in new_sections:
                new_sections.append(label)

            try:
                equivalents = to_old(act, num)
            except ValueError:
                equivalents = None
            for e in equivalents or []:
                old_label = f"{e['act']} {e['section']}"
                if old_label not in seen_old:
                    seen_old.add(old_label)
                    old_sections.append(old_label)

        anchors.append({
            "issue": issue.get("issue", ""),
            "hook_phrase": issue.get("hook_phrase", ""),
            "new_sections": new_sections,
            "old_sections": old_sections,
            "doctrine_hooks": doctrine_hooks,
        })

    return anchors


_ANSWER_SECTION_RE = re.compile(r"\bSection\s+(\d{1,3})", re.IGNORECASE)


def extract_answer_sections(answer_text):
    """The base BNS/BNSS section numbers the grounded answer actually
    cited (e.g. {'303', '35', '187'} from 'Section 303(2)' etc.). One of
    the deterministic anchor sources for the search phase -- these are the
    provisions the VERIFIED pipeline already decided were relevant, so
    they carry more weight than a guessed hook. Base number only, matching
    how retrieved_text is labelled elsewhere in the project."""
    return {m.group(1) for m in _ANSWER_SECTION_RE.finditer(answer_text or "")}


# "Section 35 of the BNSS", "Section 187 BNSS", "Section 303(2) of the BNS"
_ANSWER_ACT_SECTION_RE = re.compile(
    r"Section\s+(\d{1,3}[A-Z]{0,2})(?:\s*\([^)]*\))?\s+(?:of\s+(?:the\s+)?)?\b(BNSS|BNS)\b",
    re.IGNORECASE,
)


def _answer_act_sections(answer_text):
    """[(act, num)] pairs the grounded answer explicitly tied to an act
    ('Section 35 of the BNSS' -> ('BNSS','35')). Deduped, order kept.
    Only act-qualified references -- a bare 'Section 35' is ambiguous
    (BNS private defence vs BNSS arrest) and is deliberately ignored
    here."""
    out, seen = [], set()
    for m in _ANSWER_ACT_SECTION_RE.finditer(answer_text or ""):
        pair = (m.group(2).upper(), m.group(1))
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out


def answer_old_sections(answer_text):
    """The grounded answer's act-qualified sections, resolved to their
    IPC/CrPC equivalents ('Section 35 of the BNSS' -> ['CrPC 41', ...]).
    A clean, verified section signal -- used by later phases for ranking
    and verification. NOT folded into the search queries: an answer
    section can't be tied to a specific issue, and spraying every issue
    query with every answer section is what produced constitutional-law
    noise in the first Phase-1b trial."""
    from statute_concordance import to_old

    out, seen = [], set()
    for act, num in _answer_act_sections(answer_text):
        try:
            eq = to_old(act, num)
        except ValueError:
            eq = None
        for e in (eq or []):
            ol = f"{e['act']} {e['section']}"
            if ol not in seen:
                seen.add(ol)
                out.append(ol)
    return out


# ---------------------------------------------------------------------------
# Phase 1b -- the search phase. Real Indian Kanoon calls happen here (cost
# real IK credits); the CLI writes a review bundle for a human to eyeball
# before any of this is wired into the app. Fetch / paragraph-pinning /
# the one-sentence gloss / the whitelist gate are LATER phases.
# ---------------------------------------------------------------------------

# How many IK search hits to keep per query, and how many ranked
# candidates the bundle keeps. Deliberately modest -- the reranker is what
# finds the good ones, not breadth.
_PER_QUERY_CAP = 12
_KEEP_RANKED = 12

# Scoring weights for rank_candidates. rerank score (0..~1) dominates;
# the rest are gentle nudges, not overrides.
_W_CROSS_ISSUE = 0.12   # per extra issue this judgment also answered
_W_COURT_TIER = 0.04    # * court_tier_rank (0..3)

# How many already-in-corpus cases the ranked list may carry. Lane B is
# mainly for NEW judgments; a couple of relevant verified cases the
# grounded answer missed are a bonus, a list full of them is noise.
_MAX_CORPUS_IN_RESULT = 3


def _corpus_case_names():
    """Distinct case_name of every judgment embedded in the local corpus
    (the 22 hand-verified cases). Used to DROP an IK hit that is really
    one of those -- the clean corpus copy is preferable to a live fetch."""
    try:
        from semantic_retrieval import _load_corpus_embeddings
        corpus = _load_corpus_embeddings()
    except Exception:
        return []
    if not corpus:
        return []
    names = {r.get("case_name") for r in corpus["records"]
             if r.get("type") == "judgment" and r.get("case_name")}
    return sorted(names)


def search_candidates(anchors, *, ik_search_fn=None, local_search_fn=None,
                      per_query_cap=_PER_QUERY_CAP):
    """Run one Indian Kanoon search per issue query + one local-corpus
    semantic search per issue, and pool the hits.

    ik_search_fn: callable(query:str)->dict like indiankanoon_client.search
        (defaults to the real, PAID client).
    local_search_fn: callable(query:str)->list like
        semantic_retrieval.semantic_search (defaults to the real one; free).

    Returns a list of candidate dicts, each:
        {
          "source": "indiankanoon" | "corpus",
          "matched_issues": [int, ...],   # which anchor indices surfaced it
          "queries": [str, ...],          # the IK queries that surfaced it
          "raw": {...},                   # the raw IK doc  (source=indiankanoon)
          "record": {...},                # the corpus chunk (source=corpus)
        }
    Deduped: IK by tid, corpus by chunk_id. matched_issues/queries are
    unioned across anchors. IK or local failures are logged and skipped --
    a partial pool is fine, an empty pool is honest.
    """
    from ik_query_builder import build_issue_queries

    if ik_search_fn is None:
        try:
            from indiankanoon_client import search as ik_search_fn
        except Exception:
            ik_search_fn = None
    if local_search_fn is None:
        try:
            from semantic_retrieval import semantic_search as local_search_fn
        except Exception:
            local_search_fn = None

    ik_by_tid = {}
    corpus_by_chunk = {}

    for i, anchor in enumerate(anchors or []):
        # --- Indian Kanoon ---
        if ik_search_fn is not None:
            for query in build_issue_queries(anchor):
                try:
                    raw = ik_search_fn(query)
                except Exception:
                    logger.exception("search_candidates: IK search failed for %r", query)
                    continue
                docs = raw.get("docs", []) if isinstance(raw, dict) else []
                for doc in docs[:per_query_cap]:
                    tid = doc.get("tid")
                    if tid is None:
                        continue
                    entry = ik_by_tid.get(tid)
                    if entry is None:
                        entry = {"source": "indiankanoon", "matched_issues": set(),
                                 "queries": set(), "raw": doc}
                        ik_by_tid[tid] = entry
                    entry["matched_issues"].add(i)
                    entry["queries"].add(query)

        # --- local corpus: OTHER verified cases relevant to this issue.
        #     Deduped by CASE NAME (not chunk) -- showing six paragraphs of
        #     Vihaan Kumar as six "related judgments" is noise; one row per
        #     case, keeping the best-scoring paragraph, is the useful form.
        if local_search_fn is not None:
            try:
                local_hits = local_search_fn(anchor.get("issue", "")) or []
            except Exception:
                logger.exception("search_candidates: local search failed")
                local_hits = []
            for rec in local_hits:
                if rec.get("type") != "judgment":
                    continue
                name = rec.get("case_name") or rec.get("chunk_id")
                if not name:
                    continue
                entry = corpus_by_chunk.get(name)
                if entry is None:
                    entry = {"source": "corpus", "matched_issues": set(),
                             "queries": set(), "record": rec}
                    corpus_by_chunk[name] = entry
                entry["matched_issues"].add(i)
                if rec.get("score", 0.0) > entry["record"].get("score", 0.0):
                    entry["record"] = rec

    pooled = list(ik_by_tid.values()) + list(corpus_by_chunk.values())
    for e in pooled:
        e["matched_issues"] = sorted(e["matched_issues"])
        e["queries"] = sorted(e["queries"])
    return pooled


def _candidate_document(cand):
    """The text handed to the reranker for one candidate -- title/name
    plus the best available snippet. Kept short; the reranker reads it
    against the user's full message."""
    from ik_triage import strip_html, snippet_of

    if cand["source"] == "corpus":
        rec = cand["record"]
        name = rec.get("case_name") or "BNS/BNSS judgment"
        return f"{name}. {(rec.get('text') or '')[:700]}"
    doc = cand["raw"]
    title = strip_html(doc.get("title") or "")
    return f"{title}. {snippet_of(doc)[:700]}"


def rank_candidates(candidates, user_message, *, rerank_fn=None,
                    corpus_case_names=None, grounded_answer_text=None,
                    keep=_KEEP_RANKED, today=None):
    """Triage the pool, drop IK hits that are really corpus cases and
    corpus cases the grounded answer already cited, then rank by:
    reranker relevance to the FULL user message (dominant) + a
    cross-issue-agreement bonus + a gentle court-tier weight.

    rerank_fn: callable(query, [docs], top_k)->list|None like
        semantic_retrieval.rerank (defaults to the real one). None
        (unavailable) -> ranking degrades to the deterministic nudges
        alone, flagged via 'rerank_used' on each item.

    Returns the top `keep` candidates, best first, with at most
    _MAX_CORPUS_IN_RESULT already-in-corpus cases among them. Each item
    is enriched with 'triage', 'score', 'rerank_score', 'rerank_used'.
    """
    from ik_triage import triage_hit, court_tier_rank

    today = today or date.today()
    if corpus_case_names is None:
        corpus_case_names = _corpus_case_names()
    if rerank_fn is None:
        try:
            from semantic_retrieval import rerank as rerank_fn
        except Exception:
            rerank_fn = None

    answer_lc = (grounded_answer_text or "").lower()

    kept = []
    for cand in candidates or []:
        if cand["source"] == "indiankanoon":
            tr = triage_hit(cand["raw"], corpus_case_names=corpus_case_names, today=today)
            if tr["is_corpus_case"]:
                logger.info("rank_candidates: dropped IK hit that is a corpus case: %r", tr["title"])
                continue
            cand["triage"] = tr
        else:
            rec = cand["record"]
            name = rec.get("case_name") or ""
            # A corpus case the grounded answer ALREADY names is not a
            # "related" judgment -- the user has it.
            short = re.split(r"\s+v\.?\s+| vs\.? ", name, maxsplit=1)[0].strip().lower()
            if short and len(short) > 3 and short in answer_lc:
                logger.info("rank_candidates: dropped corpus case already in the answer: %r", name)
                continue
            cand["triage"] = {
                "tid": None,
                "title": name or None,
                "url": rec.get("source_url"),
                "court": rec.get("court"),
                "court_tier": "supreme_court",  # corpus is SC/foundational + a few HC
                "publish_date": None,
                "is_corpus_case": True,
                "post_three_code_commencement": None,
                "adverse_markers": [],
                "snippet": (rec.get("text") or "")[:600],
            }
        kept.append(cand)

    if not kept:
        return []

    docs = [_candidate_document(c) for c in kept]
    ranked = rerank_fn(user_message, docs, top_k=None) if rerank_fn else None
    rerank_used = ranked is not None
    score_by_index = {r["index"]: r["score"] for r in (ranked or [])}

    for idx, cand in enumerate(kept):
        rerank_score = score_by_index.get(idx, 0.0)
        cross = max(0, len(cand["matched_issues"]) - 1)
        tier = court_tier_rank(cand["triage"]["court_tier"])
        cand["rerank_score"] = rerank_score
        cand["rerank_used"] = rerank_used
        cand["score"] = rerank_score + _W_CROSS_ISSUE * cross + _W_COURT_TIER * tier

    kept.sort(key=lambda c: c["score"], reverse=True)

    # Cap the number of already-in-corpus cases so the list stays mostly
    # new judgments.
    out, corpus_seen = [], 0
    for cand in kept:
        if cand["source"] == "corpus":
            if corpus_seen >= _MAX_CORPUS_IN_RESULT:
                continue
            corpus_seen += 1
        out.append(cand)
        if len(out) >= keep:
            break
    return out


def _slugify(text, maxlen=60):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:maxlen].rstrip("-")) or "query"


def write_review_bundle(user_message, profile, anchors, ranked, *,
                        grounded_answer_text=None, degraded=False,
                        out_dir="related_judgments_review"):
    """Write the pooled/ranked candidates + how they were found to
    <out_dir>/<slug>.json, for a human to read and curate genuinely-good
    judgments into the corpus by hand. Mirrors
    citation_currency_checker.write_review_bundle. Overwrites a previous
    bundle for the same slug. Returns the path."""
    os.makedirs(out_dir, exist_ok=True)
    slug = _slugify(user_message)
    path = os.path.join(out_dir, f"{slug}.json")

    bundle = {
        "user_message": user_message,
        "grounded_answer_excerpt": (grounded_answer_text or "")[:1500] or None,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "anchors": anchors,
        "degraded": degraded,
        "counts": {
            "candidates_ranked": len(ranked),
            "from_indiankanoon": sum(1 for r in ranked if r["source"] == "indiankanoon"),
            "from_corpus": sum(1 for r in ranked if r["source"] == "corpus"),
        },
        "candidates": [
            {
                "source": r["source"],
                "score": round(r["score"], 4),
                "rerank_score": round(r["rerank_score"], 4),
                "rerank_used": r["rerank_used"],
                "matched_issue_indices": r["matched_issues"],
                "queries": r.get("queries", []),
                "triage": r["triage"],
            }
            for r in ranked
        ],
        "disclaimer": (
            "UNVERIFIED. Every candidate here was retrieved automatically. "
            "No field is a determination that a judgment is on point, "
            "still good law, or not under appeal. adverse_markers is a "
            "keyword flag for a human, never a verdict."
        ),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, ensure_ascii=False)
    logger.info("wrote related-judgments review bundle: %s", path)
    return path


_KILL_SWITCH_ENV = "KYR_DISABLE_LIVE_JUDGMENTS"


def get_related_judgments(user_message, grounded_answer_text=None, *,
                          write_bundle=True, ik_search_fn=None,
                          local_search_fn=None, rerank_fn=None,
                          decompose_fn=None, today=None):
    """Lane B entry point (Phase 1b form: stops after ranking + the review
    bundle -- fetch / paragraph-pinning / gloss / whitelist gate are
    later phases).

    Returns a dict with 'status' always set:
      'disabled'          -- KYR_DISABLE_LIVE_JUDGMENTS is set
      'no_decomposition'  -- the situation could not be broken into issues
      'no_candidates'     -- searches ran but nothing survived ranking
      'ok'                -- 'candidates' holds the ranked list
    plus 'candidates' (possibly []), 'bundle_path' (or None), 'profile',
    'anchors', 'degraded' (True if the reranker was unavailable).

    NEVER raises for an operational failure -- every path returns a dict
    the caller can render or ignore. This function's result is NEVER fed
    back into the grounded-answer pipeline.
    """
    empty = {"status": None, "candidates": [], "bundle_path": None,
             "profile": None, "anchors": [], "degraded": False}

    if os.getenv(_KILL_SWITCH_ENV):
        return {**empty, "status": "disabled"}

    decompose = decompose_fn or decompose_situation
    profile = decompose(user_message)
    if not profile:
        return {**empty, "status": "no_decomposition"}

    anchors = build_anchors(profile)

    pooled = search_candidates(
        anchors, ik_search_fn=ik_search_fn, local_search_fn=local_search_fn
    )
    ranked = rank_candidates(
        pooled, user_message, rerank_fn=rerank_fn,
        grounded_answer_text=grounded_answer_text, today=today
    )
    degraded = bool(ranked) and not ranked[0].get("rerank_used", False)

    bundle_path = None
    if write_bundle:
        try:
            bundle_path = write_review_bundle(
                user_message, profile, anchors, ranked,
                grounded_answer_text=grounded_answer_text, degraded=degraded,
            )
        except Exception:
            logger.exception("get_related_judgments: could not write review bundle")

    return {
        "status": "ok" if ranked else "no_candidates",
        "candidates": ranked,
        "bundle_path": bundle_path,
        "profile": profile,
        "anchors": anchors,
        "degraded": degraded,
    }


def _print_result(result):
    print(f"\nstatus: {result['status']}   degraded(rerank down): {result['degraded']}")
    if result["profile"]:
        print(f"grievance: {result['profile'].get('primary_grievance')}")
        for i, iss in enumerate(result["profile"]["issues"]):
            print(f"  issue {i}: {iss['issue']}  <- {iss['hook_phrase']!r}")
    print(f"\n{len(result['candidates'])} ranked candidate(s):")
    for r in result["candidates"]:
        t = r["triage"]
        tags = []
        if r["source"] == "corpus":
            tags.append("CORPUS (verified)")
        if t.get("adverse_markers"):
            tags.append("ADVERSE: " + ",".join(t["adverse_markers"]))
        if len(r["matched_issues"]) > 1:
            tags.append(f"{len(r['matched_issues'])} issues")
        tag = f"  [{' | '.join(tags)}]" if tags else ""
        print(f"  {r['score']:.3f}  {t.get('court_tier', '?'):>13}  "
              f"{(t.get('title') or '')[:66]}{tag}")
        if t.get("url"):
            print(f"         {t['url']}")
    if result["bundle_path"]:
        print(f"\nbundle: {result['bundle_path']}")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    ap = argparse.ArgumentParser(
        description="Lane B search phase for a chat question. Makes REAL Indian "
                    "Kanoon calls -- costs IK credits. Writes a review bundle."
    )
    ap.add_argument("question", help="the user's free-text situation")
    ap.add_argument("--answer", default=None,
                    help="the grounded answer text (its cited sections become an extra anchor)")
    ap.add_argument("--no-bundle", action="store_true", help="don't write the review bundle")
    args = ap.parse_args()

    res = get_related_judgments(args.question, args.answer, write_bundle=not args.no_bundle)
    _print_result(res)
