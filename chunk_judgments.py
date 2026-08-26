
"""
Judgment chunking — the counterpart to chunk_corpus.py, which splits statutes
on numbered SECTIONS. Judgments have no such native structure; the closest
analogue is numbered PARAGRAPHS, which most (not all) Indian Supreme Court
judgments use internally.

Findings that shaped this design (verified against all 12 sourced
judgments, not assumed):

1. Most documents have genuine, sequential numbered paragraphs extractable
   via a simple "\\nN. " pattern. Verified these are real paragraph numbers,
   not false positives, by checking the sequence is genuinely ascending.

2. Arnesh Kumar is the ONE exception with zero usable paragraph numbering:
   its paragraph numbers did not survive PyMuPDF's text extraction (likely
   a font/positioning quirk in that specific PDF). It falls back to
   fixed-size chunking, clearly flagged as lower quality in its chunk
   metadata -- not silently treated the same as the others.

3. Vihaan Kumar genuinely contains TWO separate judicial opinions in one
   document (Oka, J. writing the lead opinion; Kotiswar Singh, J. writing a
   short concurrence) -- confirmed via a judge-signature-marker scan
   ("[Name], J." pattern), not the naive "paragraph restarts to 1" signal,
   which produced a FALSE POSITIVE on NALSA (a restart to 1 there was just
   a numbered recommendations list quoted inside the single judgment, not a
   second opinion -- confirmed by finding only one judge marker in that
   document). Vihaan Kumar's two opinions are chunked separately so
   "paragraph 1" from each opinion never collides.

4. Sri Manjunath M P v State of Karnataka's case CAPTION lists petitioners
   and respondents as numbered items (6, 7, 8, then 1, 2...) using the
   exact same "\\nN. " pattern as real paragraph numbers, appearing BEFORE
   the judgment's own genuine 1, 2, 3... sequence. The original sequence
   validator required the very FIRST match overall to be 1 or 2, which
   wrongly rejected this document's otherwise-clean sequence entirely,
   falling back to degraded fixed-size chunking. Fixed by scanning forward
   for where a genuine long ascending run actually begins, skipping a
   non-sequential preamble. A SECOND, related defect in the same document:
   the respondent list's own numbering (1, 2 for two respondents)
   immediately precedes the real judgment body which ALSO starts at "2."
   ("2. Heard learned counsels..."), producing an accepted-looking
   1, 2, 2, 3, 4... sequence where the first "2" is still caption content.
   Detected as an immediate duplicate near the sequence start and skipped.

5. Multiple documents (Prakash Ranjan, Rakhi Mitra, Satender Kumar Antil
   2026, Sri Manjunath M P, and even Vihaan Kumar's own Oka opinion)
   contain genuine duplicate paragraph numbers caused by quoting another
   case's numbered paragraphs inline while discussing/applying that
   precedent. This is NOT auto-resolved here -- distinguishing "the
   court's own paragraph N" from "a quoted excerpt that retained its
   original paragraph N" would need much deeper text analysis (quotation
   tracking, cross-referencing the quoted case) that risks being fragile
   and wrong in new ways. Surfaced instead via judgment_qa.py's chunk-level
   duplicate check for human review. retrieval.py's get_judgment_paragraphs
   already handles this safely by design -- it returns ALL matching chunks
   for a requested paragraph number rather than silently picking one, the
   same honest-collision pattern used for the BNS/BNSS section-number
   overlap and Vihaan Kumar's dual opinions.

Chunk shape mirrors chunk_corpus.py's statute chunks where reasonable
(case_name, citation, source_url, source_type) but swaps section_number for
paragraph_number, and adds opinion_author for documents with more than one
opinion.
"""

import json
import os
import re
import glob


PARAGRAPH_PATTERN = re.compile(r'\n(\d{1,3})\.\s')
JUDGE_MARKER_PATTERN = re.compile(r'\n([A-Z][A-Za-z\.\s]{2,40}),?\s*J\.\s*\n')

FALLBACK_CHUNK_SIZE = 1500  # chars, for documents with no usable paragraph numbering


def find_judge_markers(text):
    """Returns list of (judge_name, position) for each 'J.' signature marker
    found. More than one distinct marker indicates a multi-opinion
    document -- confirmed reliable against all 12 sourced judgments, unlike
    the paragraph-restart heuristic which false-positived on NALSA."""
    markers = []
    for m in JUDGE_MARKER_PATTERN.finditer(text):
        markers.append((m.group(1).strip(), m.start()))
    return markers


def split_by_opinion(text):
    """Splits text into one or more (opinion_author, opinion_text) segments
    based on judge markers. Single-opinion documents return one segment
    with opinion_author=None."""
    markers = find_judge_markers(text)
    distinct_authors = []
    for name, _ in markers:
        if name not in distinct_authors:
            distinct_authors.append(name)

    if len(distinct_authors) <= 1:
        return [(None, text)]

    # Multi-opinion: split at each marker position, using the marker's own
    # position as the start of that opinion's text (so the "X, J." line
    # itself is included in that opinion's chunk).
    segments = []
    for i, (name, pos) in enumerate(markers):
        end = markers[i + 1][1] if i + 1 < len(markers) else len(text)
        segments.append((name, text[pos:end]))
    return segments


def find_genuine_sequence_start(boundaries):
    """Finds the index into `boundaries` where a genuine ascending
    paragraph sequence actually begins, skipping over a non-sequential
    preamble if one exists. Confirmed real case: Sri Manjunath M P v State
    of Karnataka's caption lists petitioners/respondents as numbered items
    (6, 7, 8, 1, 2...) using the exact same "\\nN. " pattern as real
    paragraph numbers, BEFORE the judgment's own genuine 1, 2, 3... sequence
    begins. Requiring the very first match overall to be 1 or 2 (the old
    behaviour) wrongly rejected this document's real, otherwise-clean
    sequence entirely. This scans forward for the first position where a
    long ascending run actually starts, so a short non-sequential prefix
    doesn't sink an otherwise genuine sequence. Returns None if no genuine
    start is found anywhere.

    Also handles a SECOND real defect found in the same document: the
    party list's own numbering can itself look like a clean ascending
    sequence (1, 2 for two respondents) immediately followed by the real
    judgment body ALSO starting at "2." ("2. Heard learned counsels...").
    This produces a genuine-looking 1, 2, 2, 3, 4... sequence where the
    first "2" is still party-listing content, not judgment prose. Detected
    here as an immediate duplicate number within the first few boundaries
    of an otherwise-accepted sequence, and skipped past."""
    nums = [int(b[1]) for b in boundaries]
    for start in range(len(nums)):
        if nums[start] not in (1, 2):
            continue
        remaining = nums[start:]
        if len(remaining) < 2:
            continue
        transitions = len(remaining) - 1
        ascending = sum(1 for i in range(1, len(remaining)) if remaining[i] > remaining[i - 1])
        if ascending / transitions < 0.85:
            continue
        # Found an accepted sequence -- now check for an immediate
        # duplicate near its start (the caption/body collision case).
        for i in range(1, min(4, len(remaining))):
            if remaining[i] == remaining[i - 1]:
                # Duplicate found this early: the real sequence begins
                # at the SECOND occurrence of the duplicated number.
                return start + i
        return start
    return None


def is_genuine_paragraph_sequence(boundaries):
    """Validates that found paragraph markers form a real ascending sequence
    starting near 1, rather than trusting a raw count threshold. Confirmed
    real case: Vihaan Kumar's second (concurring) opinion has only 3
    paragraph markers -- too few for a naive count-based threshold like
    '>=5', but genuinely real and correctly ordered (1, 2, 3), since the
    opinion itself is short ("a few lines in supplement"). A count
    threshold would wrongly reject this as noise; a sequence check
    correctly accepts it."""
    if len(boundaries) < 2:
        return False
    return find_genuine_sequence_start(boundaries) is not None


def find_paragraph_boundaries(text):
    boundaries = []
    for m in PARAGRAPH_PATTERN.finditer(text):
        boundaries.append((m.start() + 1, m.group(1)))  # +1 to skip the leading \n
    return boundaries


def chunk_by_paragraph(text, base_fields):
    boundaries = find_paragraph_boundaries(text)

    # Trim any non-sequential preamble (confirmed real case: Sri Manjunath
    # M P's numbered party-listing caption uses the same digit-period
    # pattern as real paragraphs before the genuine 1, 2, 3... sequence
    # starts) so those false-positive matches don't get chunked as if they
    # were real early paragraphs.
    genuine_start = find_genuine_sequence_start(boundaries)
    if genuine_start is not None and genuine_start > 0:
        boundaries = boundaries[genuine_start:]

    chunks = []

    if boundaries and boundaries[0][0] > 0:
        preamble = text[:boundaries[0][0]].strip()
        if preamble:
            chunks.append({
                **base_fields,
                "paragraph_number": "preamble",
                "text": preamble,
                "chunk_method": "paragraph_number",
            })

    for i, (start, para_num) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        chunk_text = text[start:end].strip()
        chunks.append({
            **base_fields,
            "paragraph_number": para_num,
            "text": chunk_text,
            "chunk_method": "paragraph_number",
        })
    return chunks


def chunk_by_fixed_size(text, base_fields, size=FALLBACK_CHUNK_SIZE):
    """Fallback for documents with no usable paragraph numbering (confirmed
    real case: Arnesh Kumar). Splits on paragraph breaks (double newline)
    where the document has them; confirmed real case: Arnesh Kumar's
    extraction has NO double-newlines anywhere (single-newline throughout),
    so this falls back further to single-newline splitting rather than
    silently producing one giant unsplit chunk, which is what happened
    before this was checked explicitly."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current = []
    current_len = 0
    chunk_index = 1

    for para in paragraphs:
        if current_len + len(para) > size and current:
            chunks.append({
                **base_fields,
                "paragraph_number": f"fallback_{chunk_index}",
                "text": "\n\n".join(current),
                "chunk_method": "fixed_size_fallback",
            })
            chunk_index += 1
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append({
            **base_fields,
            "paragraph_number": f"fallback_{chunk_index}",
            "text": "\n\n".join(current),
            "chunk_method": "fixed_size_fallback",
        })
    return chunks


def chunk_judgment(record):
    base_fields = {
        "case_name": record["case_name"],
        "citation": record["citation"],
        "source_url": record["source_url"],
        "source_type": record["source_type"],
    }

    opinions = split_by_opinion(record["text"])
    all_chunks = []

    for opinion_author, opinion_text in opinions:
        opinion_fields = {**base_fields, "opinion_author": opinion_author}
        boundaries = find_paragraph_boundaries(opinion_text)

        # Require the found paragraph markers to form a genuine ascending
        # sequence before trusting paragraph-based chunking for this
        # opinion segment -- not just a raw count, since a real short
        # opinion (confirmed case: Vihaan Kumar's 3-paragraph concurrence)
        # can have very few markers and still be entirely genuine.
        if is_genuine_paragraph_sequence(boundaries):
            chunks = chunk_by_paragraph(opinion_text, opinion_fields)
        else:
            chunks = chunk_by_fixed_size(opinion_text, opinion_fields)

        all_chunks.extend(chunks)

    return all_chunks


def chunk_judgment_file(json_path, output_dir="chunks"):
    with open(json_path, "r", encoding="utf-8") as f:
        record = json.load(f)

    chunks = chunk_judgment(record)

    method_counts = {}
    for c in chunks:
        method_counts[c["chunk_method"]] = method_counts.get(c["chunk_method"], 0) + 1
    opinion_authors = sorted(set(c["opinion_author"] for c in chunks if c["opinion_author"]))

    print(f"\n{json_path}")
    print(f"  {len(chunks)} chunks | methods: {method_counts}"
          + (f" | opinions: {opinion_authors}" if opinion_authors else ""))

    os.makedirs(output_dir, exist_ok=True)
    safe_name = record["case_name"].lower().replace(" ", "_").replace(".", "").replace(",", "")
    out_path = os.path.join(output_dir, f"{safe_name}_chunks.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"  Wrote to {out_path}")
    return out_path


if __name__ == "__main__":
    for filepath in sorted(glob.glob("corpus/*.json")):
        with open(filepath, "r", encoding="utf-8") as f:
            record = json.load(f)
        # Skip statutes -- they go through chunk_corpus.py instead.
        if "Act No." in record.get("citation", ""):
            continue
        chunk_judgment_file(filepath)
        
