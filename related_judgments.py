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
     message into its discrete legal issues + verbatim fact hooks. Every
     hook is checked back against the user's own words before it is used.
  2. build_anchors()        -- pure Python: per issue, resolve the BNS/
     BNSS section hooks to the IPC/CrPC numbers Indian Kanoon is indexed
     under (statute_concordance).
  3. search_candidates()    -- one IK search per issue query + one local
     corpus search per issue; pooled and deduped.
  4. rank_candidates()      -- Voyage rerank-2 the pool against the FULL
     user message + cross-issue bonus + court-tier weight; drop corpus
     cases and corpus-case IK hits.
  5. fetch_and_pin()        -- fetch the top few IK candidates, clean via
     ik_text_cleaner, then rerank REAL PARAGRAPHS against the situation:
     this re-orders the pool on actual content (search headlines alone
     don't discriminate) and pins the 1-3 on-point paragraphs, with the
     judgment's own paragraph number.
  6. settled_doctrine_whitelist.coverage_report() -- the gate: the panel
     is shown to the user ('show_user') ONLY when EVERY decomposed issue
     is a settled doctrine. Otherwise the review bundle is still written
     (for hand-curation) but nothing is shown.
  7. gloss_and_verify()     -- whitelisted path only: one bounded Sonnet
     sentence per candidate ("what this case dealt with"), then Python
     rejects any gloss with verdict / binding-ness language or a section
     number the pinned paragraph doesn't contain.
  8. (later) the app.py UI panel + an eval harness.

Phases 0-4 are built (steps 1-7). get_related_judgments() is the entry
point; its result is NEVER fed back into the grounded-answer pipeline.
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
_SONNET_MODEL = "claude-sonnet-5"

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
_W_CROSS_ISSUE = 0.10    # per extra issue this judgment also answered
_W_COURT_TIER = 0.03     # * court_tier_rank (0..3)
_W_PHRASE_QUERY = 0.08   # candidate was surfaced by a verbatim-phrase query
_W_RECENT = 0.03         # candidate is dated on/after the 1 Jul 2024 codes

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


def corpus_candidates(anchors, *, local_search_fn=None, local_search_many_fn=None):
    """The FREE half of search_candidates: one local-corpus semantic
    search per issue, pooled and deduped by case name. No Indian Kanoon,
    no cost. Split out so it can be run speculatively at answer time
    (prepare_related_judgments) while the paid IK half waits for a click.

    Each per-issue search is independent -> run them concurrently
    (local_search_many_fn) when available.
    """
    if local_search_many_fn is None and local_search_fn is None:
        try:
            from semantic_retrieval import semantic_search as local_search_fn
        except Exception:
            return []

    issues = [a.get("issue", "") for a in (anchors or [])]
    if local_search_many_fn is not None:
        results = local_search_many_fn(issues)  # {issue_text: [hits]}
    elif len(issues) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(issues))) as ex:
            got = list(ex.map(lambda q: _safe_call(local_search_fn, q), issues))
        results = dict(zip(issues, got))
    else:
        results = {q: _safe_call(local_search_fn, q) for q in issues}

    corpus_by_name = {}
    for i, issue_text in enumerate(issues):
        for rec in (results.get(issue_text) or []):
            if rec.get("type") != "judgment":
                continue
            name = rec.get("case_name") or rec.get("chunk_id")
            if not name:
                continue
            entry = corpus_by_name.get(name)
            if entry is None:
                entry = {"source": "corpus", "matched_issues": set(),
                         "queries": set(), "record": rec}
                corpus_by_name[name] = entry
            entry["matched_issues"].add(i)
            if rec.get("score", 0.0) > entry["record"].get("score", 0.0):
                entry["record"] = rec

    pooled = list(corpus_by_name.values())
    for e in pooled:
        e["matched_issues"] = sorted(e["matched_issues"])
        e["queries"] = []
    return pooled


def _safe_call(fn, arg):
    try:
        return fn(arg) or []
    except Exception as exc:
        logger.warning("_safe_call: %s failed: %s", getattr(fn, "__name__", fn), exc)
        return []


def search_candidates(anchors, *, ik_search_many_fn=None, local_search_fn=None,
                      local_search_many_fn=None, corpus_pool=None,
                      per_query_cap=_PER_QUERY_CAP, fromdate="01-01-2015"):
    """Indian Kanoon searches for every issue query (run CONCURRENTLY via
    ik_search_many_fn) + the local-corpus half, pooled.

    ik_search_many_fn: callable([query])->{query: result|None} like
        indiankanoon_client.search_many (defaults to the real PAID one).
    corpus_pool: if given, the already-computed corpus half (from
        corpus_candidates / prepare_related_judgments) -- skips re-running
        it. Otherwise corpus_candidates() runs here.

    Returns the pooled candidate list (see corpus_candidates for the
    corpus dict shape; IK entries carry 'raw' instead of 'record').
    Deduped: IK by tid. A query / search that fails maps to no hits, never
    raises.
    """
    from ik_query_builder import build_issue_queries

    if ik_search_many_fn is None:
        try:
            from indiankanoon_client import search_many as ik_search_many_fn
        except Exception:
            ik_search_many_fn = None

    # one flat, deduped batch of queries -> ONE parallel call
    query_to_issues = {}
    for i, anchor in enumerate(anchors or []):
        for q in build_issue_queries(anchor, fromdate=fromdate or None):
            query_to_issues.setdefault(q, set()).add(i)

    ik_by_tid = {}
    if ik_search_many_fn is not None and query_to_issues:
        try:
            results = ik_search_many_fn(list(query_to_issues))
        except Exception as exc:
            logger.warning("search_candidates: IK batch search failed: %s", exc)
            results = {}
        for query, issue_idxs in query_to_issues.items():
            raw = results.get(query)
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
                entry["matched_issues"].update(issue_idxs)
                entry["queries"].add(query)

    if corpus_pool is None:
        corpus_pool = corpus_candidates(
            anchors, local_search_fn=local_search_fn,
            local_search_many_fn=local_search_many_fn,
        )

    pooled = list(ik_by_tid.values()) + list(corpus_pool)
    for e in pooled:
        if isinstance(e["matched_issues"], set):
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
            # If the grounded answer NAMES this case ("the Supreme Court in
            # D.K. Basu said..."), showing it is MORE useful, not less --
            # the answer only mentions it, the panel gives the actual
            # paragraph + a link to read. Flag it so the panel can say
            # "the judgment cited above".
            short = re.split(r"\s+v\.?\s+| vs\.? ", name, maxsplit=1)[0].strip().lower()
            cand["triage"] = {
                "tid": None,
                "title": name or None,
                "citation": (rec.get("citation") or "").strip(),
                "url": rec.get("source_url"),
                "court": rec.get("court"),
                "court_tier": "supreme_court",  # corpus is SC/foundational + a few HC
                "publish_date": None,
                "is_corpus_case": True,
                "cited_in_answer": bool(short and len(short) > 3 and short in answer_lc),
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
        # A candidate that a "quoted verbatim phrase" query surfaced is far
        # more likely to be genuinely on point than one that only matched a
        # bag of section numbers and keywords.
        from_phrase = any('"' in q for q in cand.get("queries", []))
        recent = cand["triage"].get("post_three_code_commencement") is True
        nudges = (
            _W_CROSS_ISSUE * cross
            + _W_COURT_TIER * tier
            + (_W_PHRASE_QUERY if from_phrase else 0.0)
            + (_W_RECENT if recent else 0.0)
        )
        cand["rerank_score"] = rerank_score
        cand["rerank_used"] = rerank_used
        cand["_nudges"] = nudges   # fetch_and_pin re-uses these on top of content_score
        cand["score"] = rerank_score + nudges

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


# ---------------------------------------------------------------------------
# Phase 2 -- fetch + paragraph pinning.
#
# Ranking on Indian Kanoon's one-line search headlines does not
# discriminate (a Phase-1b trial put Kasab and Navjot Sandhu in the same
# score band as the genuinely on-point cases). So: fetch the top few IK
# candidates, clean them with ik_text_cleaner, and rerank the REAL
# PARAGRAPHS against the user's full situation. A candidate's content
# score is its best paragraph's score; the same pass pins the 1-3 on-point
# paragraphs with the judgment's own paragraph number.
# ---------------------------------------------------------------------------

_FETCH_N = 6              # top IK candidates to fetch in full (Rs 0.20 each)
_MAX_PINNED_PARAS = 3
_MAX_PARAS_PER_DOC = 50   # cap the rerank payload
_KEEP_FINAL = 8
_W_UNFETCHED = 0.4       # score multiplier for an IK candidate we didn't fetch

# IK's own data-structure paragraph categories worth a small nudge when
# choosing which paragraph to pin -- the court's reasoning and holding,
# not the facts recital or the parties' arguments.
_STRUCTURE_BONUS = {
    "Conclusion": 0.06, "Precedent": 0.05, "CDiscource": 0.045,
    "Analysis": 0.04, "Issue": 0.02,
}

_PARA_NUM_RE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s")


def _para_number(text):
    """The judgment's own leading paragraph number ('14. ...' -> 14), or
    None. Lets the panel cite 'para 14', not 'somewhere in the judgment'."""
    m = _PARA_NUM_RE.match(text or "")
    return int(m.group(1)) if m else None


def _corpus_para_pool(case_name):
    """Every embedded chunk of a corpus case, as a paragraph pool -- free
    (already local), and better than the single retrieved chunk for
    choosing what to pin."""
    try:
        from semantic_retrieval import _load_corpus_embeddings
        corpus = _load_corpus_embeddings()
    except Exception:
        return []
    if not corpus:
        return []
    pool = []
    for r in corpus["records"]:
        if r.get("type") != "judgment" or r.get("case_name") != case_name:
            continue
        text = (r.get("text") or "").strip()
        if len(text) < 40:
            continue
        pool.append({"text": text, "structure": None,
                     "para_number": _para_number(text) or r.get("paragraph_number")})
    return pool[:_MAX_PARAS_PER_DOC]


def _paras_from_html(html, clean_fn):
    """Clean one IK judgment's HTML into a paragraph pool. Returns None if
    the HTML is empty or ik_text_cleaner rejects it -- the caller demotes
    rather than drops the candidate. (The fetch itself is now done in
    bulk by fetch_and_pin via indiankanoon_client.get_documents.)"""
    if not isinstance(html, str) or not html.strip() or clean_fn is None:
        return None
    try:
        cleaned = clean_fn(html)
    except Exception:
        logger.warning("_paras_from_html: ik_text_cleaner rejected a document")
        return None
    pool = []
    for p in cleaned.get("paragraphs", []):
        text = (p.get("text") or "").strip()
        if len(text) < 40:
            continue
        pool.append({"text": text, "structure": p.get("structure"),
                     "para_number": _para_number(text)})
    return pool


_PIN_STOPWORDS = frozenset("""
a an the this that these those and or but of to in on at by for with as is are
was were be been being he she it they them his her their my our your i we me us
you not no nor so then than there here have has had do does did about after over
under from into out up down will would can could court judgment judgement case
cases police arrest arrested arresting section sections held would shall this
petitioner respondent appellant accused learned counsel para paragraph
""".split())


def _content_words(text):
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower())
            if w not in _PIN_STOPWORDS}


def fetch_and_pin(ranked, user_message, *, pin_query=None, fetch_many_fn=None,
                  clean_fn=None, rerank_fn=None, fetch_n=_FETCH_N, keep=_KEEP_FINAL):
    """Fetch the top `fetch_n` IK candidates (CONCURRENTLY, one batch call)
    + every corpus candidate, and PIN their 1-3 on-point paragraphs (with
    the judgment's own paragraph number).

    Each candidate gains 'pinned', 'content_score', 'fetch_failed', and a
    re-based 'score' (content is authoritative once a paragraph is pinned;
    fetched-but-nothing / unfetched IK candidates fall back to a demoted
    headline score -- THIS re-orders the list).

    Speed: the paragraph pool of each judgment is PRE-FILTERED to those
    that share a content word with the situation (or carry a reasoning
    structure tag) BEFORE the reranker sees them -- ~500 paragraphs down
    to ~60, faster and less noise.

    pin_query: the concise text to rank paragraphs against (default the
        raw message; callers pass primary_grievance + issue list).
    """
    if not ranked:
        return []
    q = pin_query or user_message
    q_words = _content_words(q)

    if fetch_many_fn is None:
        try:
            from indiankanoon_client import get_documents as fetch_many_fn
        except Exception:
            fetch_many_fn = None
    if clean_fn is None:
        try:
            from ik_text_cleaner import clean_document as clean_fn
        except Exception:
            clean_fn = None
    if rerank_fn is None:
        try:
            from semantic_retrieval import rerank as rerank_fn
        except Exception:
            rerank_fn = None

    # which IK candidates to open, in current rank order
    to_fetch = []   # [(cand_idx, tid_str)]
    ik_seen = 0
    for idx, cand in enumerate(ranked):
        if cand["source"] == "indiankanoon" and ik_seen < fetch_n:
            ik_seen += 1
            tid = cand["triage"].get("tid")
            if tid is not None:
                to_fetch.append((idx, str(tid)))

    docs = {}
    if fetch_many_fn and to_fetch:
        try:
            docs = fetch_many_fn([tid for _, tid in to_fetch]) or {}
        except Exception as exc:
            logger.warning("fetch_and_pin: batch fetch failed: %s", exc)

    pools = {}  # candidate index -> [paragraph dicts]
    for idx, cand in enumerate(ranked):
        if cand["source"] == "corpus":
            pools[idx] = _corpus_para_pool(cand["triage"].get("title") or "")
    for idx, tid in to_fetch:
        raw = docs.get(tid)
        html = raw.get("doc") if isinstance(raw, dict) else None
        pool = _paras_from_html(html, clean_fn)
        if pool is None:
            ranked[idx]["fetch_failed"] = True
        else:
            pools[idx] = pool

    ik_fetched_idxs = {idx for idx, _ in to_fetch}

    # PRE-FILTER: only paragraphs worth reranking (share vocabulary with
    # the situation, or a reasoning-structure tag). Caps the rerank
    # payload hard and removes boilerplate before scoring.
    flat = []
    for cidx, pool in pools.items():
        worth = [p for p in pool
                 if (_content_words(p["text"]) & q_words)
                 or (p.get("structure") in _STRUCTURE_BONUS)]
        worth = (worth or pool[:8])[:_MAX_PARAS_PER_DOC]
        for p in worth:
            flat.append((cidx, p))

    para_scores = {}
    if rerank_fn and flat:
        result = rerank_fn(q, [p["text"] for _, p in flat], top_k=None)
        for r in (result or []):
            para_scores[id(flat[r["index"]][1])] = r["score"]

    paras_by_cand = {}
    for cidx, p in flat:
        paras_by_cand.setdefault(cidx, []).append(p)

    for idx, cand in enumerate(ranked):
        pool = paras_by_cand.get(idx) or []
        scored = []
        for p in pool:
            s = para_scores.get(id(p), 0.0)
            overlap = len(_content_words(p["text"]) & q_words)
            pick = (s
                    + _STRUCTURE_BONUS.get(p.get("structure") or "", 0.0)
                    + 0.04 * min(overlap, 5))
            scored.append((pick, s, overlap, p))

        # Relevance gate: a pinned paragraph must share vocabulary with
        # the situation -- keeps procedural boilerplate and reranker
        # misfires ("As a honest Judge... is he right in hearing this
        # matter") out. Prefer >=2 shared content words; fall back to >=1,
        # then to the top-2 by rerank only if nothing overlaps at all.
        strong = [t for t in scored if t[2] >= 2]
        weak = [t for t in scored if t[2] >= 1]
        pool_scored = strong or weak or sorted(scored, key=lambda t: t[1], reverse=True)[:2]
        pool_scored.sort(key=lambda t: t[0], reverse=True)

        nudges = cand.get("_nudges", 0.0)
        if pool_scored:
            cand["content_score"] = round(pool_scored[0][1], 4)
            cand["pinned"] = [
                {"para_number": p.get("para_number"), "structure": p.get("structure"),
                 "text": p["text"][:1200], "score": round(s, 4)}
                for _, s, _o, p in pool_scored[:_MAX_PINNED_PARAS]
            ]
            # Content is authoritative: re-base the score on it.
            cand["score"] = pool_scored[0][1] + nudges
        else:
            cand["content_score"] = None
            cand["pinned"] = []
            head = cand.get("rerank_score", 0.0)
            if idx in ik_fetched_idxs or cand.get("fetch_failed"):
                # we looked and found nothing on point -> strong demote
                cand["score"] = 0.5 * head + nudges
            elif cand["source"] == "indiankanoon":
                # beyond fetch_n, never opened -> mild demote
                cand["score"] = 0.7 * head + nudges

    ranked.sort(key=lambda c: c["score"], reverse=True)
    return _dedupe_batch(ranked)[:keep]


def _dedupe_batch(ranked):
    """Collapse near-identical rows from a BATCH judgment -- one order
    disposing of many connected petitions produces one IK document per
    petition (same court, same date, same reasoning, same pinned
    paragraph). Keep the highest-scored, drop the rest. Key: court +
    publish date + first ~120 chars of the top pinned paragraph."""
    seen, out = set(), []
    for c in ranked:
        t = c["triage"]
        top_para = (c.get("pinned") or [{}])[0].get("text", "")
        key = (t.get("court"), t.get("publish_date"),
               re.sub(r"\s+", " ", top_para[:120]).strip().lower())
        if all(key):
            if key in seen:
                logger.info("_dedupe_batch: dropped batch duplicate %r", t.get("title"))
                continue
            seen.add(key)
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# Phase 4 -- the one bounded generative step, and its verification gate.
#
# For each displayed judgment, one Sonnet call writes ONE sentence: what
# the case dealt with and what the court observed. Then Python checks the
# output: no verdict / currency / binding-ness language, and no section
# number the pinned paragraph does not itself contain. A gloss that fails
# is dropped -- the paragraph still shows, just without the sentence.
#
# This is the SAME discipline as generate_grounded_response: the model
# phrases, Python verifies. The gloss never advises and never says the
# case applies to the user.
# ---------------------------------------------------------------------------

JUDGMENT_GLOSS_PROMPT = """A person described this situation to a legal-information tool:
"{situation}"

Below is a paragraph (or two) from a real Indian court judgment that a search suggested might be related. Write ONE sentence for the person that says, in plain words:
- what factual situation that judgment was dealing with, and
- what the court observed or held about it.

Rules -- breaking any of these makes the sentence unusable:
- ONE sentence only, at most ~35 words.
- Describe the judgment. Do NOT say it is "binding", "settled law", "good law", or "the position". Do NOT say it applies to this person, or use "you"/"your"/"in your case".
- Do NOT give a verdict about this person's situation ("your arrest was illegal", "you are entitled to bail").
- Do NOT mention a section number or a holding that is not in the paragraph text below.
- If the paragraph is not actually about a situation like the person's, say only: "This one may not be closely on point."

Judgment paragraph(s):
{paragraphs}

The one sentence:"""


# Lowercased substrings that must not appear in a gloss.
_GLOSS_FORBIDDEN = (
    "your arrest", "your case", "your situation", "in your case", "applies to you",
    "you are entitled", "you were entitled", "you should", "you can seek", "you may seek",
    "binding", "settled law", "good law", "the settled position", "must be followed",
    "your bank", "your account", "your bail", "illegal in your", "unlawful in your",
)
_GLOSS_SECTION_RE = re.compile(r"\bSection\s+(\d{1,3})", re.IGNORECASE)


def _verify_gloss(gloss, pinned_text):
    """Return the gloss if it passes, else None. Rejects verdict /
    currency / binding-ness language and any Section N not present in the
    paragraph text the gloss was written from."""
    if not gloss or not gloss.strip():
        return None
    g = gloss.strip()
    low = g.lower()
    if any(bad in low for bad in _GLOSS_FORBIDDEN):
        logger.info("_verify_gloss: rejected for forbidden phrase: %r", g)
        return None
    para_sections = set(_GLOSS_SECTION_RE.findall(pinned_text or ""))
    for sec in _GLOSS_SECTION_RE.findall(g):
        if sec not in para_sections:
            logger.info("_verify_gloss: rejected -- Section %s not in the paragraph", sec)
            return None
    # one sentence, not a paragraph
    if g.count(". ") > 1 and len(g.split()) > 45:
        logger.info("_verify_gloss: rejected -- more than one sentence")
        return None
    return g


_GLOSS_MAX_WORKERS = 5


def gloss_and_verify(candidates, user_message, *, gloss_fn=None):
    """Attach a verified one-sentence 'what this case dealt with' gloss to
    each candidate that has pinned paragraphs. `cand['gloss']` is the
    sentence, or None if the model was unavailable / the sentence failed
    verification. Never raises.

    The gloss calls (one Sonnet call each) are INDEPENDENT -> run them
    concurrently. gloss_fn: callable(situation, paragraphs_text)->str,
    injected for tests. Defaults to a real Sonnet call.
    """
    if gloss_fn is None:
        gloss_fn = _default_gloss_fn

    jobs = []  # (cand, paras_text)
    for cand in candidates or []:
        cand.setdefault("gloss", None)
        pinned = cand.get("pinned") or []
        if pinned:
            jobs.append((cand, "\n\n".join(p["text"] for p in pinned[:2])))

    def _one(job):
        cand, paras_text = job
        try:
            raw = gloss_fn(user_message, paras_text)
        except Exception as exc:
            logger.warning("gloss_and_verify: gloss call failed: %s", exc)
            return
        cand["gloss"] = _verify_gloss(raw, paras_text)

    if len(jobs) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(_GLOSS_MAX_WORKERS, len(jobs))) as ex:
            list(ex.map(_one, jobs))
    else:
        for job in jobs:
            _one(job)
    return candidates


def _default_gloss_fn(situation, paragraphs_text):
    if client is None:
        return None
    resp = client.messages.create(
        model=_SONNET_MODEL,
        max_tokens=160,
        messages=[{"role": "user", "content": JUDGMENT_GLOSS_PROMPT.format(
            situation=situation[:1200], paragraphs=paragraphs_text[:2500],
        )}],
    )
    return _extract_text_from_response(resp).strip()


def _slugify(text, maxlen=60):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:maxlen].rstrip("-")) or "query"


def write_review_bundle(user_message, profile, anchors, ranked, *,
                        grounded_answer_text=None, degraded=False,
                        whitelist_report=None,
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
                "headline_rerank_score": round(r.get("rerank_score", 0.0), 4),
                "content_score": (round(r["content_score"], 4)
                                  if r.get("content_score") is not None else None),
                "fetch_failed": r.get("fetch_failed", False),
                "rerank_used": r["rerank_used"],
                "matched_issue_indices": r["matched_issues"],
                "queries": r.get("queries", []),
                "triage": r["triage"],
                "gloss": r.get("gloss"),
                "pinned_paragraphs": r.get("pinned", []),
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
    if whitelist_report is not None:
        bundle["whitelist"] = whitelist_report
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, ensure_ascii=False)
    logger.info("wrote related-judgments review bundle: %s", path)
    return path


_KILL_SWITCH_ENV = "KYR_DISABLE_LIVE_JUDGMENTS"

# What the user-facing panel actually shows (the review bundle keeps
# everything). A candidate is display-worthy only if its content is
# genuinely on point.
_DISPLAY_CONTENT_FLOOR = 0.40
_MAX_DISPLAY = 5
_OFF_POINT_RE = re.compile(r"not (be )?(closely |really )?on point", re.I)


def _display_worthy(cand):
    """True if this candidate should appear in the user-facing panel."""
    gloss = cand.get("gloss")
    if gloss and _OFF_POINT_RE.search(gloss):
        return False
    if cand.get("fetch_failed"):
        return False
    # A case the grounded answer named always shows -- the user wants to
    # read the judgment it cited.
    if cand.get("triage", {}).get("cited_in_answer"):
        return True
    cs = cand.get("content_score")
    # Corpus cases are verified, but a weak content score means the match
    # is a stray paragraph, not the point of the case -- hold them to a
    # slightly higher bar than live IK hits.
    floor = _DISPLAY_CONTENT_FLOOR + (0.02 if cand["source"] == "corpus" else 0.0)
    return cs is not None and cs >= floor


def prepare_related_judgments(user_message, *, decompose_fn=None,
                              local_search_fn=None, local_search_many_fn=None,
                              rerank_fn=None, grounded_answer_text=None, today=None):
    """The FREE, no-Indian-Kanoon half of the pipeline: decompose the
    situation, build the anchors, search the local 22-case corpus, and
    rank those corpus candidates. Costs one Haiku call + Voyage (free
    tier) and ~3-4s.

    Meant to be run speculatively the moment the grounded answer is
    produced (in a background thread -- this touches no Streamlit state),
    so that when the user clicks "Show related judgments" only the paid
    Indian Kanoon + gloss work remains.

    Returns {'profile', 'anchors', 'corpus_ranked', 'today'} or None. Pass
    the whole dict back as get_related_judgments(prepared=...).
    """
    decompose = decompose_fn or decompose_situation
    try:
        profile = decompose(user_message)
    except Exception as exc:
        logger.warning("prepare_related_judgments: decompose failed: %s", exc)
        return None
    if not profile:
        return None

    profile.setdefault("_question", user_message)
    anchors = build_anchors(profile)
    corpus_pool = corpus_candidates(
        anchors, local_search_fn=local_search_fn,
        local_search_many_fn=local_search_many_fn,
    )
    corpus_ranked = rank_candidates(
        list(corpus_pool), user_message, rerank_fn=rerank_fn,
        grounded_answer_text=grounded_answer_text, today=today,
        keep=_KEEP_FINAL,
    )
    # judgments the user kept in a draft for the same / a similar question
    # -- pre-pinned, no IK call. Merged ahead of the corpus ones.
    seed = approved_candidates(profile)
    if seed:
        seen = {(c["source"], c["triage"].get("tid") or c["triage"].get("title")) for c in corpus_ranked}
        corpus_ranked = [c for c in seed
                         if (c["source"], c["triage"].get("tid") or c["triage"].get("title")) not in seen
                         ] + corpus_ranked
    return {"profile": profile, "anchors": anchors,
            "corpus_ranked": corpus_ranked, "today": today}


# ---------------------------------------------------------------------------
# The user-approved store. When a live judgment is kept in a draft the user
# prepared (they read it, edited around it, sent it on), it is recorded
# here so the SAME / a similar question retrieves it instantly next time --
# no Indian Kanoon call, paragraphs already pinned.
#
# This is NOT the verified corpus. It never feeds the grounded answer
# (Lane A). It only pre-seeds Lane B, still shown with the unverified
# framing. Gitignored, like the review bundles.
# ---------------------------------------------------------------------------

_APPROVED_STORE = "related_judgments_approved.json"
_APPROVED_MATCH_FLOOR = 0.55   # content-word overlap between a stored issue and a new one


def _issue_overlap(a, b):
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _load_approved(path=_APPROVED_STORE):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def record_approved(question, issues, ranked_or_result, *, path=_APPROVED_STORE):
    """Append the judgments a user kept in a prepared draft to the store.
    Accepts a get_related_judgments() result OR a raw ranked list. Deduped
    by tid (IK) / title (corpus). Only entries with a pinned paragraph are
    stored. Never raises."""
    cands = ((ranked_or_result or {}).get("for_display")
             if isinstance(ranked_or_result, dict) else ranked_or_result) or []
    issue_texts = [str(i.get("issue") if isinstance(i, dict) else i) for i in (issues or [])]

    store = _load_approved(path)
    have = {(e.get("tid"), (e.get("case_name") or "").lower()) for e in store}
    added = 0
    for c in cands:
        pinned = c.get("pinned") or []
        if not pinned:
            continue
        t = c.get("triage", {})
        key = (t.get("tid"), (t.get("title") or "").lower())
        if key in have:
            continue
        have.add(key)
        store.append({
            "tid": t.get("tid"),
            "case_name": t.get("title") or "Judgment",
            "citation": t.get("citation") or "",
            "court": t.get("court") or "",
            "url": t.get("url") or "",
            "publish_date": t.get("publish_date"),
            "source": c.get("source", "indiankanoon"),
            "pinned": [{"para_number": p.get("para_number"), "structure": p.get("structure"),
                        "text": (p.get("text") or "")[:1200]} for p in pinned[:_MAX_PINNED_PARAS]],
            "gloss": c.get("gloss"),
            "issues": issue_texts,
            "approved_for_question": (question or "")[:400],
            "approved_utc": datetime.now(timezone.utc).isoformat(),
        })
        added += 1

    if added:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(store, fh, indent=2, ensure_ascii=False)
        except OSError:
            logger.warning("record_approved: could not write %s", path)
    return added


def approved_candidates(profile, *, path=_APPROVED_STORE):
    """Stored judgments whose approved-for issues overlap this question's
    issues (or the exact same question). Returned pre-pinned, as candidate
    dicts with source='approved' -- no Indian Kanoon call. [] if none."""
    store = _load_approved(path)
    if not store or not profile:
        return []
    new_issues = [i.get("issue", "") for i in profile.get("issues", [])]
    q = (profile.get("_question") or "").strip().lower()  # optional, set by callers

    out = []
    for e in store:
        exact = q and (e.get("approved_for_question") or "").strip().lower() == q
        overlap = exact or any(
            _issue_overlap(si, ni) >= _APPROVED_MATCH_FLOOR
            for si in e.get("issues", []) for ni in new_issues
        )
        if not overlap:
            continue
        out.append({
            "source": "approved",
            "matched_issues": list(range(len(new_issues))),
            "queries": [],
            "pinned": [dict(p) for p in e.get("pinned", [])],
            "gloss": e.get("gloss"),
            "content_score": 0.6,   # it was good enough to keep in a filing
            "rerank_score": 0.6,
            "rerank_used": True,
            "_nudges": 0.0,
            "score": 0.6,
            "triage": {
                "tid": e.get("tid"), "title": e.get("case_name"),
                "citation": e.get("citation"), "court": e.get("court"),
                "court_tier": "high_court", "url": e.get("url"),
                "publish_date": e.get("publish_date"), "is_corpus_case": False,
                "cited_in_answer": False, "adverse_markers": [],
                "previously_approved": True,
            },
        })
    return out


_PREP_EXECUTOR = None


def submit_prepare(user_message, grounded_answer_text=None):
    """Kick off prepare_related_judgments() on a small background pool and
    return the Future. The app calls this the moment a grounded answer is
    shown; by the time the user clicks "Show related judgments" the free
    half (decompose + corpus search + rank) is already done, so the click
    only pays for the Indian Kanoon + gloss work.

    prepare_related_judgments touches no Streamlit state, so running it in
    a plain worker thread is safe."""
    global _PREP_EXECUTOR
    if _PREP_EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor
        _PREP_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rj-prep")
    return _PREP_EXECUTOR.submit(
        prepare_related_judgments, user_message,
        grounded_answer_text=grounded_answer_text,
    )


def get_related_judgments(user_message, grounded_answer_text=None, *,
                          write_bundle=True, pin=True, gloss=True, prepared=None,
                          ik_search_many_fn=None, local_search_fn=None,
                          local_search_many_fn=None, rerank_fn=None,
                          decompose_fn=None, fetch_many_fn=None, clean_fn=None,
                          gloss_fn=None, today=None):
    """Lane B entry point: decompose -> anchor -> search -> rank -> fetch
    top few + pin paragraphs -> settled-doctrine whitelist gate -> (if
    covered) one bounded gloss per candidate + verification.

    prepared: the dict from prepare_related_judgments() -- if given,
        decomposition + anchors + the corpus search/rank are reused
        instead of recomputed, so the call starts straight at the paid
        Indian Kanoon searches.

    Returns a dict with 'status' always set:
      'disabled'          -- KYR_DISABLE_LIVE_JUDGMENTS is set
      'no_decomposition'  -- the situation could not be broken into issues
      'no_candidates'     -- searches ran but nothing survived ranking
      'ok'                -- 'candidates' holds the ranked list
    plus:
      'candidates'   -- ranked list, each with 'pinned' paragraphs and
                        (when show_user) a verified 'gloss'
      'show_user'    -- True only when EVERY issue is a whitelisted
                        settled doctrine. When False the panel must NOT
                        be shown to the user; the review bundle is still
                        written for hand-curation.
      'whitelist'    -- coverage_report(): which topic each issue mapped
                        to, and which issue (if any) kept show_user False
      'bundle_path', 'profile', 'anchors', 'degraded'

    pin=False stops after ranking (no IK-doc credits). gloss=False skips
    the Sonnet call even when whitelisted.

    NEVER raises for an operational failure. This function's result is
    NEVER fed back into the grounded-answer pipeline.
    """
    from settled_doctrine_whitelist import coverage_report

    empty = {"status": None, "candidates": [], "for_display": [], "bundle_path": None,
             "profile": None, "anchors": [], "degraded": False,
             "show_user": False, "whitelist": None}

    if os.getenv(_KILL_SWITCH_ENV):
        return {**empty, "status": "disabled"}

    if prepared and prepared.get("profile"):
        profile = prepared["profile"]
        anchors = prepared["anchors"]
        # prepared["corpus_ranked"] is corpus + user-approved, already ranked
        pre_ranked = list(prepared.get("corpus_ranked") or [])
        if today is None:
            today = prepared.get("today")
        ik_pool = search_candidates(anchors, ik_search_many_fn=ik_search_many_fn, corpus_pool=[])
        ik_ranked = rank_candidates(
            ik_pool, user_message, rerank_fn=rerank_fn,
            grounded_answer_text=grounded_answer_text, today=today,
        )
        ranked = _merge_ranked(ik_ranked, pre_ranked)
    else:
        decompose = decompose_fn or decompose_situation
        profile = decompose(user_message)
        if not profile:
            return {**empty, "status": "no_decomposition"}
        profile.setdefault("_question", user_message)
        anchors = build_anchors(profile)
        corpus_pool = corpus_candidates(
            anchors, local_search_fn=local_search_fn,
            local_search_many_fn=local_search_many_fn,
        )
        pooled = search_candidates(
            anchors, ik_search_many_fn=ik_search_many_fn,
            local_search_fn=local_search_fn,
            local_search_many_fn=local_search_many_fn, corpus_pool=corpus_pool,
        )
        ranked = rank_candidates(
            pooled, user_message, rerank_fn=rerank_fn,
            grounded_answer_text=grounded_answer_text, today=today,
        )
        # user-approved judgments are pre-built (they carry their own
        # triage/score) -- merge them AFTER rank_candidates, which expects
        # a 'record'/'raw' on every input.
        ranked = _merge_ranked(ranked, approved_candidates(profile))

    if pin and ranked:
        pin_query = " ".join(
            [profile.get("primary_grievance", "")]
            + [iss["issue"] for iss in profile.get("issues", [])]
        ).strip() or user_message
        try:
            ranked = fetch_and_pin(
                ranked, user_message, pin_query=pin_query,
                fetch_many_fn=fetch_many_fn, clean_fn=clean_fn, rerank_fn=rerank_fn,
            )
        except Exception:
            logger.exception("get_related_judgments: fetch_and_pin failed; using headline ranking")

    # --- the whitelist gate: only settled doctrine reaches the user ---
    wl = coverage_report(profile.get("issues", []))
    show_user = wl["covered"]

    # --- the one bounded generative step, whitelisted path only.
    #     Gloss ONLY the candidates that could plausibly be shown -- a
    #     content score above the floor (+ 1 buffer). No point spending a
    #     Sonnet call on a judgment that won't clear _display_worthy.
    if show_user and gloss and ranked:
        glossable = [c for c in ranked
                     if c["source"] == "corpus"
                     or (c.get("content_score") is not None
                         and c["content_score"] >= _DISPLAY_CONTENT_FLOOR)]
        glossable = glossable[:_MAX_DISPLAY + 1]
        try:
            gloss_and_verify(glossable, user_message, gloss_fn=gloss_fn)
        except Exception:
            logger.exception("get_related_judgments: gloss_and_verify failed")

    degraded = bool(ranked) and not ranked[0].get("rerank_used", False)

    bundle_path = None
    if write_bundle:
        try:
            bundle_path = write_review_bundle(
                user_message, profile, anchors, ranked,
                grounded_answer_text=grounded_answer_text, degraded=degraded,
                whitelist_report=wl,
            )
        except Exception:
            logger.exception("get_related_judgments: could not write review bundle")

    for_display = [c for c in ranked if _display_worthy(c)][:_MAX_DISPLAY] if show_user else []

    return {
        "status": "ok" if ranked else "no_candidates",
        "candidates": ranked,          # full ranked list -> the review bundle
        "for_display": for_display,    # the subset the user-facing panel shows
        "bundle_path": bundle_path,
        "profile": profile,
        "anchors": anchors,
        "degraded": degraded,
        "show_user": show_user,
        "whitelist": wl,
    }


def _merge_ranked(*lists, keep=_KEEP_FINAL):
    """Union candidate lists, deduped by (source, tid-or-title), sorted by
    score desc, capped at `keep`. First occurrence of a key wins."""
    by_key = {}
    for lst in lists:
        for c in lst or []:
            t = c.get("triage", {})
            by_key.setdefault((c["source"], t.get("tid") or t.get("title")), c)
    return sorted(by_key.values(), key=lambda c: c.get("score", 0.0), reverse=True)[:keep]


def _para_num_or_none(v):
    if isinstance(v, int):
        return v
    return int(v) if isinstance(v, str) and v.isdigit() else None


def authorities_from_result(result, *, max_items=6):
    """A get_related_judgments() result -> a draft_layer `authorities`
    list. One entry per displayed candidate (its top pinned paragraph),
    quote verbatim. Corpus -> verified=True; live Indian Kanoon ->
    verified=False (walled off in the draft's 'NOT VERIFIED' block)."""
    out = []
    for c in (result or {}).get("for_display", []):
        pinned = c.get("pinned") or []
        if not pinned:
            continue
        t = c.get("triage", {})
        p = pinned[0]
        out.append({
            "case_name": t.get("title") or "Judgment",
            "citation": t.get("citation") or "",
            "court": t.get("court") or "",
            "para_number": p.get("para_number"),
            "quote": (p.get("text") or "").strip(),
            "url": t.get("url") or "",
            "verified": c.get("source") == "corpus",
        })
        if len(out) >= max_items:
            break
    return out


def authorities_from_matches(matches, *, max_items=4):
    """The chat's Lane-A retrieval matches -> `authorities`. Only judgment
    matches (they carry 'case_name'; statute matches do not). All verified
    (they are from the 22-case corpus)."""
    out = []
    for m in matches or []:
        if not m.get("case_name"):
            continue
        quote = (m.get("text") or "").strip()
        if len(quote) < 40:
            continue
        out.append({
            "case_name": m["case_name"],
            "citation": m.get("citation") or "",
            "court": "",
            "para_number": _para_num_or_none(m.get("paragraph_number")),
            "quote": quote[:900],
            "url": m.get("source_url") or "",
            "verified": True,
        })
        if len(out) >= max_items:
            break
    return out


def _print_result(result):
    print(f"\nstatus: {result['status']}   degraded(rerank down): {result['degraded']}")
    wl = result.get("whitelist") or {}
    print(f"show to user: {result.get('show_user')}   "
          f"(whitelist covered: {wl.get('covered')})")
    if wl.get("uncovered"):
        print(f"  NOT whitelisted -- panel hidden because of: {wl['uncovered']}")
    if result["profile"]:
        print(f"grievance: {result['profile'].get('primary_grievance')}")
        for i, iss in enumerate(result["profile"]["issues"]):
            topic = dict(wl.get("by_issue", [])).get(iss["issue"])
            print(f"  issue {i}: {iss['issue']}  <- {iss['hook_phrase']!r}  [{topic or 'NOT whitelisted'}]")
    disp_ids = {id(c) for c in result.get("for_display", [])}
    print(f"\n{len(result['candidates'])} ranked candidate(s)  "
          f"({len(disp_ids)} would show in the user panel, marked >>):")
    for r in result["candidates"]:
        t = r["triage"]
        mark = ">> " if id(r) in disp_ids else "   "
        tags = []
        if r["source"] == "corpus":
            tags.append("CORPUS (verified)")
        if r.get("fetch_failed"):
            tags.append("FETCH FAILED (headline only)")
        if t.get("adverse_markers"):
            tags.append("ADVERSE: " + ",".join(t["adverse_markers"]))
        if len(r["matched_issues"]) > 1:
            tags.append(f"{len(r['matched_issues'])} issues")
        tag = f"  [{' | '.join(tags)}]" if tags else ""
        print(f"{mark}{r['score']:.3f}  {t.get('court_tier', '?'):>13}  "
              f"{(t.get('title') or '')[:64]}{tag}")
        if t.get("url"):
            print(f"         {t['url']}")
        if r.get("gloss"):
            print(f"         gloss: {r['gloss']}")
        for p in r.get("pinned", [])[:2]:
            num = f"para {p['para_number']}" if p.get("para_number") else "para ?"
            struct = f" [{p['structure']}]" if p.get("structure") else ""
            print(f"         {num}{struct} ({p['score']}): {p['text'][:160].strip()}...")
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
                    help="the grounded answer text (used to drop already-cited corpus cases)")
    ap.add_argument("--no-bundle", action="store_true", help="don't write the review bundle")
    ap.add_argument("--no-fetch", action="store_true",
                    help="stop after headline ranking -- no full-document fetches / IK-doc credits")
    ap.add_argument("--no-gloss", action="store_true",
                    help="skip the one-sentence gloss even when whitelisted (no Sonnet call)")
    args = ap.parse_args()

    res = get_related_judgments(args.question, args.answer,
                                write_bundle=not args.no_bundle, pin=not args.no_fetch,
                                gloss=not args.no_gloss)
    _print_result(res)
