
"""
Judgment chunking — the counterpart to chunk_corpus.py, which splits statutes
on numbered SECTIONS. Judgments have no such native structure; the closest
analogue is numbered PARAGRAPHS, which most (not all) Indian Supreme Court
judgments use internally.

Findings that shaped this design (verified against all 8 sourced judgments,
not assumed):

1. 7 of 8 documents have genuine, sequential numbered paragraphs extractable
   via a simple "\\nN. " pattern. Verified these are real paragraph numbers,
   not false positives, by checking the sequence is genuinely ascending.

2. Arnesh Kumar is the ONE exception: its paragraph numbers did not survive
   PyMuPDF's text extraction (likely a font/positioning quirk in that
   specific PDF). It falls back to fixed-size chunking, clearly flagged as
   lower quality in its chunk metadata -- not silently treated the same as
   the other 7.

3. Vihaan Kumar genuinely contains TWO separate judicial opinions in one
   document (Oka, J. writing the lead opinion; Kotiswar Singh, J. writing a
   short concurrence) -- confirmed via a judge-signature-marker scan
   ("[Name], J." pattern), not the naive "paragraph restarts to 1" signal,
   which produced a FALSE POSITIVE on NALSA (a restart to 1 there was just
   a numbered recommendations list quoted inside the single judgment, not a
   second opinion -- confirmed by finding only one judge marker in that
   document). Vihaan Kumar's two opinions are chunked separately so
   "paragraph 1" from each opinion never collides.

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
    document -- confirmed reliable against all 8 sourced judgments, unlike
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
    nums = [int(b[1]) for b in boundaries]
    if nums[0] not in (1, 2):
        return False
    total_transitions = len(nums) - 1
    ascending_run = sum(1 for i in range(1, len(nums)) if nums[i] > nums[i - 1])
    # Require the large majority of consecutive transitions to be genuinely
    # ascending. Verified against real data: NALSA has 145 transitions with
    # only 2 genuine violations (a quoted numbered list restarting at 1,
    # a footnote-like aside) -- a 98.6% ascending ratio, correctly accepted.
    # Vihaan Kumar's short concurrence has only 2 transitions (1->2->3),
    # both ascending -- also correctly accepted despite being a tiny sample.
    return ascending_run / max(total_transitions, 1) >= 0.85


def find_paragraph_boundaries(text):
    boundaries = []
    for m in PARAGRAPH_PATTERN.finditer(text):
        boundaries.append((m.start() + 1, m.group(1)))  # +1 to skip the leading \n
    return boundaries


def chunk_by_paragraph(text, base_fields):
    boundaries = find_paragraph_boundaries(text)
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
        
