
"""
Judgment-specific QA module — the counterpart to corpus_qa.py's
verify_section_coverage, which is statute-shaped only (numbered-section gap
and duplicate detection) and produces a FALSE PASS on judgment text.

Confirmed real case: running verify_section_coverage against Arnesh Kumar's
judgment text matched a single stray line beginning "1961. The maximum
sentence..." (a reference to the Dowry Prohibition Act, 1961, inside the
judgment's facts) as if it were a statute section header, and reported a
clean PASS on a range of "1961-1961". This is not a hypothetical risk --
it is exactly what a statute-shaped check does when pointed at case law.

Judgments have no numbered-section structure to verify. What CAN be checked,
and what genuinely matters for downstream trust, is different:
  1. Does the text open with a recognisable case caption (case name, date)?
  2. Does the text end with a recognisable judgment closing (a judge's
     signature block, typically with a place and date)?
  3. Is the text free of private-use-area / non-standard Unicode glyphs --
     confirmed real case: Youth Bar Association's corpus record opens with
     two stray icon-font glyphs (U+EDD9, U+EDDA), almost certainly captured
     from the source website's UI icons during a browser print-to-PDF.
  4. Is the text free of the specific footer contamination pattern already
     found and fixed in build_judgment_corpus.py (Indian Kanoon's per-page
     "Indian Kanoon - http://..." stamp) -- this re-checks that fix rather
     than assuming it always works.
  5. Does the text contain any suspiciously short "word" immediately
     preceded by an ellipsis-like marker (…) -- confirmed real case:
     Satender Kumar Antil 2026's caption block has "REPORTABLE" truncated
     to "REPOR", "PETITIONER" to "P", "RESPONDENTS" to "RES".

None of these checks can be fully automated to certainty -- they are
heuristic flags for a human to look at, not a pass/fail gate the way
verify_section_coverage is for statutes. A judgment that fails a heuristic
here may still be a perfectly good source; the point is to surface anomalies
for a human decision, not to silently accept or silently discard.

A SEPARATE, chunk-level check (find_duplicate_paragraph_numbers, at the
bottom of this file) operates on *_chunks.json files rather than corpus
records -- see its docstring for what it catches and why.
"""

import re
import unicodedata


CAPTION_PATTERN = re.compile(
    r'^.{0,120}\bvs?\.?\b.{0,80}\bon\b\s+\d{1,2}\s+\w+,?\s+\d{4}',
    re.IGNORECASE | re.DOTALL
)

CLOSING_PATTERN = re.compile(
    r'new\s*\n?\s*delhi[;:,]?\s*\n?\s*\w+\.?\s+\d{1,2},?\s+\d{4}',
    re.IGNORECASE
)

INDIAN_KANOON_FOOTER_PATTERN = re.compile(
    r'Indian Kanoon\s*-\s*https?://', re.IGNORECASE
)

PRIVATE_USE_AREA_RANGES = [
    (0xE000, 0xF8FF),      # Basic Multilingual Plane private use area
    (0xF0000, 0xFFFFD),    # Supplementary Private Use Area-A
    (0x100000, 0x10FFFD),  # Supplementary Private Use Area-B
]


def _is_private_use(char):
    codepoint = ord(char)
    return any(lo <= codepoint <= hi for lo, hi in PRIVATE_USE_AREA_RANGES)


def check_caption_present(text):
    """Heuristic: does the document open with something caption-shaped
    (a case name, 'vs'/'versus', and a date)? A judgment record whose
    corpus text doesn't start this way may have been truncated, or may
    have picked up site-chrome text before the actual content, as
    happened with Youth Bar Association."""
    opening = text[:250]
    return bool(CAPTION_PATTERN.search(opening))


def check_closing_present(text):
    """Heuristic: does the document end with something signature-block
    shaped (a place name, typically 'New Delhi', and a date)? Most Supreme
    Court judgments end this way. A record that doesn't may be truncated
    mid-judgment -- a much more serious problem than a missing caption,
    since it could mean the actual holding was cut off."""
    closing = text[-200:]
    return bool(CLOSING_PATTERN.search(closing))


def find_private_use_glyphs(text):
    """Returns the set of distinct private-use-area characters found, with
    their codepoints, plus a short context snippet for the first occurrence
    of each. Confirmed real case: Youth Bar Association's record contains
    U+EDD9 and U+EDDA at the very start of the text."""
    found = {}
    for i, char in enumerate(text):
        if _is_private_use(char) and char not in found:
            start = max(0, i - 20)
            end = min(len(text), i + 20)
            found[char] = {
                "codepoint": f"U+{ord(char):04X}",
                "context": text[start:end].replace("\n", "\\n"),
            }
    return found


def find_footer_contamination(text):
    """Re-checks for the Indian Kanoon per-page footer stamp that
    build_judgment_corpus.py strips at extraction time. This check exists
    to catch a REGRESSION -- e.g. if extraction is ever re-run without the
    stripping step, or a new document is added through a different path
    that skips it -- not because the stripping is expected to fail."""
    matches = INDIAN_KANOON_FOOTER_PATTERN.findall(text)
    return len(matches)


def find_truncated_caption_words(text):
    """Heuristic: flags short (1-6 letter) all-caps fragments immediately
    following an ellipsis-like marker (…), which is the specific visual
    signature of the truncation defect confirmed in Satender Kumar Antil
    2026's caption ("… P" for "PETITIONER", "… RES" for "RESPONDENTS").
    This is a narrow, evidence-based pattern, not a general truncation
    detector -- it will not catch every possible truncation, only this
    specific documented shape."""
    return re.findall(r'…\s*[A-Z]{1,6}\b', text[:500])


def verify_judgment(record):
    """Run all judgment-appropriate checks against a corpus record dict
    (as produced by build_judgment_corpus.py / promote_primary_judgment.py).
    Returns a report dict. This does NOT gate/block the way
    verify_section_coverage does for statutes -- judgment text is too
    structurally varied for a hard pass/fail. Instead it surfaces flags
    for human review, consistent with the project's "surface uncertainty,
    don't silently guess" principle."""
    text = record.get("text", "")
    flags = []

    if not check_caption_present(text):
        flags.append(
            "No recognisable case caption found in the opening ~250 characters "
            "(expected something like '[Case Name] vs [Party] on [Date]'). "
            "Check whether site-chrome text or other noise precedes the actual "
            "judgment content."
        )

    if not check_closing_present(text):
        flags.append(
            "No recognisable judgment closing found in the final ~200 characters "
            "(expected a signature block with a place and date, typically "
            "'New Delhi; [Month] [Day], [Year]'). This may indicate the "
            "extracted text is truncated before the judgment actually ends -- "
            "verify against the source PDF's last page."
        )

    private_use = find_private_use_glyphs(text)
    if private_use:
        flags.append(
            f"Found {len(private_use)} distinct private-use-area Unicode "
            f"character(s), likely captured UI icon glyphs rather than real "
            f"text: {private_use}"
        )

    footer_count = find_footer_contamination(text)
    if footer_count:
        flags.append(
            f"Found {footer_count} instance(s) of the Indian Kanoon footer "
            f"stamp still present in the text -- extraction cleanup may not "
            f"have run, or may have failed for this document."
        )

    truncated = find_truncated_caption_words(text)
    if truncated:
        flags.append(
            f"Found {len(truncated)} instance(s) of the ellipsis-then-short-caps "
            f"pattern associated with caption-word truncation: {truncated}. "
            f"Verify these aren't cut-off words like 'PETITIONER'/'RESPONDENTS'."
        )

    passed_all_heuristics = len(flags) == 0
    summary = (
        f"{record.get('case_name', '(unnamed)')}: "
        f"{'no anomalies flagged' if passed_all_heuristics else f'{len(flags)} anomal{'y' if len(flags)==1 else 'ies'} flagged'}"
    )

    return {
        "case_name": record.get("case_name"),
        "passed_all_heuristics": passed_all_heuristics,
        "flags": flags,
        "summary": summary,
    }


def find_duplicate_paragraph_numbers(chunks):
    """Chunk-level check (operates on a *_chunks.json list, not a corpus
    record): flags paragraph_number values that appear more than once in
    the same chunked judgment. This is a REAL, confirmed defect class,
    distinct from the corpus-text checks above. Verified TWO distinct real
    causes so far, not one -- do not assume every hit is the same
    phenomenon:

    (a) The judgment quotes ANOTHER COURT'S numbered paragraphs inline
        while discussing/applying that precedent. Confirmed real cases:
        L. Muruganantham quotes a lower court's paragraphs inline mid-
        reasoning; Prabir Purkayastha quotes Pankaj Bansal's paragraphs
        36-39 verbatim before returning to its own paragraphs 36-39;
        Sri Manjunath M P quotes Arnesh Kumar's paragraphs while applying
        it; Vihaan Kumar's own Oka opinion has a duplicate paragraph 29
        from a similar inline quotation.

    (b) The judgment quotes a NON-JUDICIAL numbered instrument (an
        international declaration, a cited report's own numbered
        recommendations, etc.) that happens to also use "N." numbering.
        Confirmed real case: NALSA quotes the Yogyakarta Principles
        (an international declaration on gender identity, itself
        numbered "1.", "2.", "3."...) AND separately quotes a cited
        report's own numbered policy-recommendations list -- neither is
        a "court" being quoted, so this is a genuinely different
        mechanism from (a) even though it produces the same symptom.

    Either way, the chunker cannot reliably distinguish "this is the
    document's own paragraph N" from "this is a quoted/reproduced
    numbered passage that happens to carry the number N" -- doing so
    would need much deeper text analysis (quotation-mark tracking,
    cross-referencing the quoted source's actual text, distinguishing
    judicial from non-judicial numbered sources) that risks being
    fragile and wrong in new ways. Rather than silently resolving this,
    it is surfaced here for human review, consistent with this project's
    "Cannot Determine over silent guessing" principle.

    NOTE on L. Muruganantham specifically: it has an unusually large
    number of duplicates (18 distinct paragraph numbers) and its raw
    number sequence is genuinely messy on inspection -- clean ascending
    runs interrupted by scattered single out-of-place numbers (likely
    citation/footnote fragments matching the "\\nN. " pattern by
    coincidence) plus what looks like a second independently-numbered
    section partway through. This has NOT been fully diagnosed beyond
    confirming causes (a) and (b) apply to some of its duplicates --
    treat this document's paragraph-number lookups with extra caution
    until someone reads it end-to-end."""
    from collections import Counter
    nums = [c["paragraph_number"] for c in chunks]
    counts = Counter(nums)
    return {k: v for k, v in counts.items() if v > 1 and k != "preamble"}


if __name__ == "__main__":
    import json
    import glob

    files = glob.glob("corpus/*.json")
    if not files:
        print("No files found in corpus/.")
    else:
        for filepath in sorted(files):
            with open(filepath, "r", encoding="utf-8") as f:
                record = json.load(f)
            # Skip statutes -- they go through corpus_qa.py's
            # verify_section_coverage instead, not this module.
            if "Act No." in record.get("citation", ""):
                continue
            report = verify_judgment(record)
            print(f"\n{filepath}")
            print(f"  {report['summary']}")
            for flag in report["flags"]:
                print(f"    - {flag}")

    print("\n--- Chunk-level check: duplicate paragraph numbers ---")
    chunk_files = glob.glob("chunks/*_chunks.json")
    for filepath in sorted(chunk_files):
        with open(filepath, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        if not chunks or "paragraph_number" not in chunks[0]:
            continue  # statute chunk files use section_number, not this
        dupes = find_duplicate_paragraph_numbers(chunks)
        if dupes:
            print(f"\n{filepath}")
            print(f"  Duplicate paragraph number(s) found: {dupes}")
            print(f"  Likely cause: this judgment quotes another case's numbered "
                  f"paragraphs inline. Verify which occurrence is the document's "
                  f"own reasoning before relying on a lookup by this number alone.")
            
