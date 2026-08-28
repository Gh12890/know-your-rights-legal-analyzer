
"""
ik_text_cleaner.py

Converts Indian Kanoon's raw HTML `doc` field (from get_document()) into
plain text comparable to what the existing corpus pipeline expects
(judgment_qa.py, chunk_judgments.py were built against PyMuPDF-extracted
plain text from manually-sourced PDFs — NOT html).

ARCHITECTURE NOTE:
This is a separate concern from indiankanoon_client.py (API transport)
and separate from Step 3's QA gate (trustworthiness checking). This
file only answers: "given IK's HTML, what is the clean text?" It makes
no judgment about whether that text is a valid/trustworthy judgment.

WHY BEAUTIFULSOUP, NOT REGEX:
This project has already hit 2 real bugs from regex-based text
stripping (footer-stripping regex overlap, twice, different root
causes both times). HTML tag structure is exactly the kind of thing
regex handles unreliably (nested tags, attributes with special chars,
self-closing tags). A real parser avoids that whole bug class.

REAL STRUCTURE CONFIRMED (2026-08-28, against a real Bombay HC 2022
judgment fetched live — this replaced an earlier, WRONG assumption
that most content lived in <pre> tags; it does not):

    <h2 class="doc_title">...</h2>          -- title
    <h3 class="doc_author">...</h3>          -- author
    <h3 class="doc_bench">...</h3>           -- bench
    <pre id="pre_1">...</pre>                -- case header block
                                                 (parties, coram, dates)
    <p data-structure="Issue" id="p_N">...</p>       -- most paragraphs
    <p data-structure="Facts" id="p_N">...</p>
    <p data-structure="Precedent" id="p_N">...</p>
    <p data-structure="PetArg" id="p_N">...</p>       (petitioner argument)
    <p data-structure="RespArg" id="p_N">...</p>      (respondent argument)
    <p data-structure="Section" id="p_N">...</p>      (statute text/refs)
    <p data-structure="Conclusion" id="p_N">...</p>
    <p data-structure="CDiscource" id="p_N">...</p>   (court's discourse)
    <blockquote id="blockquote_N">...</blockquote>    -- quoted material
                                                          (often reproduced
                                                          statute text)
    <pre id="pre_N">...</pre>                -- CAN also appear mid-document
                                                 (confirmed: one showed up
                                                 as pre_2, mid-judgment,
                                                 containing regular
                                                 paragraph content -- not
                                                 just header material.
                                                 Don't assume all <pre>
                                                 after pre_1 are noise.)
    <span class="citetext" data-sentiment="Pos|Neg|PARTY|Neutral"
          data-docid="...">...</span>        -- nested inside <p>/<blockquote>,
                                                 marks citation sentiment.
                                                 This is IK's paid-tier
                                                 "Precedent Analyser"
                                                 feature, present even in
                                                 a basic /doc/ response.
    <a href="/doc/{tid}/" id="a_N">...</a>   -- inline citation links to
                                                 OTHER judgment tids --
                                                 potentially useful for
                                                 precedent-chain discovery
                                                 later, out of scope for
                                                 this function.

The data-structure categories are IK's own 8-category paragraph
classification (their pricing page calls this "Structural Analysis":
Facts, Issues, Argument by petitioner, Argument by respondent,
Precedent Analysis, Analysis of Law, Courts Discourse, Conclusion --
confirmed present in the free-tier response, not a stated add-on).
This is genuinely more useful than plain PyMuPDF-extracted text: it
lets a caller filter for e.g. only "Conclusion" + "Precedent"
paragraphs when building a short doctrine excerpt, rather than
dumping an entire judgment.

STILL UNVERIFIED (only 1 real document inspected so far -- do not
assume these hold across all courts/years without checking more):
- Whether data-structure values are always one of the 8 categories
  seen so far, or whether other courts/document types use others.
- Whether every document has an <h2>/<h3> metadata block in this
  exact form.
- Whether blockquote content should be treated as body text or kept
  separately flagged as "quoted material" (currently: treated as body
  text, in document order, since a reproduced statute section IS part
  of what the judgment says).
"""

import logging

from bs4 import BeautifulSoup

logger = logging.getLogger("ik_text_cleaner")


class IKTextCleaningError(Exception):
    """Raised when the HTML structure doesn't match what we expect
    closely enough to safely extract text. Fail loudly rather than
    silently returning garbage or a wrong subset of the document."""
    pass


def extract_metadata(html: str) -> dict:
    """
    Pull structured metadata out of the HTML header tags, separate
    from the body text. Returns whatever it can find; missing fields
    are set to None rather than raising, since metadata absence isn't
    necessarily fatal the way body-text absence would be.

    Returns:
        dict with keys: title, author, bench (each str or None)
    """
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h2", class_="doc_title")
    author_tag = soup.find("h3", class_="doc_author")
    bench_tag = soup.find("h3", class_="doc_bench")

    return {
        "title": title_tag.get_text(strip=True) if title_tag else None,
        "author": author_tag.get_text(strip=True).replace("Author:", "").strip()
                  if author_tag else None,
        "bench": bench_tag.get_text(strip=True).replace("Bench:", "").strip()
                 if bench_tag else None,
    }


# Container tags that hold body content, in the order we care about
# them appearing. Confirmed present in a real document: pre, p,
# blockquote. All three can carry real substantive judgment text —
# NONE of them should be assumed to be noise-only.
_BODY_CONTAINER_TAGS = ("pre", "p", "blockquote")


def extract_body_paragraphs(html: str) -> list:
    """
    Extract the judgment body as an ORDERED list of paragraph-level
    dicts, walking the real document structure (pre/p/blockquote, in
    document order) rather than only looking at one tag type.

    This is the corrected version of the earlier (wrong) approach,
    which only looked at <pre> tags and silently dropped ~95% of a
    real 70,780-char document because most content actually lives in
    <p data-structure="..."> and <blockquote> tags.

    Each returned dict has:
        tag (str)              -- "pre", "p", or "blockquote"
        structure (str|None)   -- IK's data-structure category, e.g.
                                   "Issue", "Facts", "Precedent",
                                   "PetArg", "RespArg", "Section",
                                   "Conclusion", "CDiscource". None for
                                   <pre>/<blockquote> which don't carry
                                   this attribute.
        text (str)             -- cleaned text of this element
        has_citation (bool)    -- True if a <span class="citetext">
                                   appears inside this element
        citation_sentiments (list[str]) -- distinct data-sentiment
                                   values found inside this element
                                   (e.g. ["Pos"], ["Neg", "PARTY"]),
                                   empty list if none

    IMPORTANT: this walks the soup in document order using
    find_all(_BODY_CONTAINER_TAGS), which returns top-level matches in
    the order they appear in the HTML — it does NOT recurse into
    nested matches twice, since blockquote/p/pre don't nest inside
    each other in the real document inspected. If a future document
    DOES nest these tags, this would double-count content — flagged
    here so it's not a silent risk if it ever comes up.

    Args:
        html: the raw string from get_document()'s 'doc' field.

    Returns:
        List of paragraph dicts, in document order. Empty paragraphs
        (whitespace-only after stripping) are excluded.

    Raises:
        IKTextCleaningError if none of pre/p/blockquote tags are found
        at all — this means the HTML structure doesn't match the
        pattern this function was built against, and guessing a
        fallback risks silently returning wrong/incomplete text again.
    """
    soup = BeautifulSoup(html, "html.parser")
    elements = soup.find_all(_BODY_CONTAINER_TAGS)

    if not elements:
        raise IKTextCleaningError(
            "No pre/p/blockquote tags found in document HTML. This "
            "document's structure doesn't match the pattern this "
            "function was built against (1 real document, Bombay HC "
            "2022, confirmed 2026-08-28). Do not guess a fallback — "
            "inspect this document's raw HTML manually."
        )

    paragraphs = []
    for el in elements:
        text = el.get_text().strip()
        if not text:
            continue

        citetext_spans = el.find_all("span", class_="citetext")
        sentiments = []
        for span in citetext_spans:
            sentiment = span.get("data-sentiment")
            if sentiment and sentiment not in sentiments:
                sentiments.append(sentiment)

        paragraphs.append({
            "tag": el.name,
            "structure": el.get("data-structure"),
            "text": text,
            "has_citation": len(citetext_spans) > 0,
            "citation_sentiments": sentiments,
        })

    if not paragraphs:
        raise IKTextCleaningError(
            f"Found {len(elements)} pre/p/blockquote element(s) but "
            f"all were empty after stripping. Inspect manually."
        )

    logger.info(
        "Extracted %d non-empty paragraph(s) from document HTML "
        "(%d total pre/p/blockquote tags found)",
        len(paragraphs), len(elements)
    )

    return paragraphs


def extract_body_text(html: str) -> str:
    """
    Convenience wrapper around extract_body_paragraphs() for callers
    that just want plain joined text and don't need per-paragraph
    structure metadata (e.g. a quick length/sanity check).

    Most real use in Step 3's QA gate should probably use
    extract_body_paragraphs() directly instead, since the structural
    metadata (data-structure category, citation sentiment) is genuine
    signal worth keeping, not discarding.

    Returns:
        Plain text string, paragraphs joined with double newlines, in
        document order.

    Raises:
        IKTextCleaningError — propagated from extract_body_paragraphs().
    """
    paragraphs = extract_body_paragraphs(html)
    return "\n\n".join(p["text"] for p in paragraphs)


def clean_document(html: str) -> dict:
    """
    Main entry point. Combines metadata extraction and body text
    extraction into one call.

    Args:
        html: the raw string from get_document()'s 'doc' field.

    Returns:
        dict with keys:
            title (str or None)
            author (str or None)
            bench (str or None)
            body_text (str) — plain text, paragraphs separated by
                double newlines (for callers that just want text)
            paragraphs (list[dict]) — full structured paragraph list
                from extract_body_paragraphs(), including
                data-structure category and citation sentiment per
                paragraph. Step 3's QA gate should use THIS, not just
                body_text, since the structure/sentiment signal is
                genuinely useful (e.g. flag documents with zero
                "Conclusion"-tagged paragraphs as suspicious).
            paragraph_count (int) — len(paragraphs). A judgment with
                only 1-2 real paragraphs is suspicious for what should
                be a multi-page document and should be flagged by
                Step 3's QA gate, not silently trusted.

    Raises:
        IKTextCleaningError — propagated from extract_body_paragraphs().
        Callers (Step 3's QA gate) should catch this and reject the
        document rather than let the exception crash a batch process.
    """
    metadata = extract_metadata(html)
    paragraphs = extract_body_paragraphs(html)
    body_text = "\n\n".join(p["text"] for p in paragraphs)

    return {
        **metadata,
        "body_text": body_text,
        "paragraphs": paragraphs,
        "paragraph_count": len(paragraphs),
    }
    