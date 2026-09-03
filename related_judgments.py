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
import re

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
