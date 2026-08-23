
import fitz
import json
import os
import re

MAIN_BODY_X0_MIN = 110
MAIN_BODY_X0_MAX = 250
MIN_WIDTH = 20
FOOTNOTE_X0_THRESHOLD = 480

FOOTER_PATTERN = re.compile(r"THE GAZETTE OF INDIA EXTRAORDINARY", re.IGNORECASE)


def is_chapter_heading(text):
    stripped = text.strip()
    return stripped.upper().startswith("CHAPTER") or (
        len(stripped) < 80 and stripped.isupper() and not any(c.isdigit() for c in stripped[:3])
    )


def extract_main_body_text(pdf_path):
    doc = fitz.open(pdf_path)
    full_text_parts = []

    for page in doc:
        blocks = page.get_text("blocks")
        blocks_sorted = sorted(blocks, key=lambda b: b[1])

        for b in blocks_sorted:
            x0, y0, x1, y1, text, block_no, block_type = b
            width = x1 - x0
            stripped_text = text.strip()

            if not stripped_text:
                continue
            if FOOTER_PATTERN.search(stripped_text):
                continue
            if x0 >= FOOTNOTE_X0_THRESHOLD:
                continue
            if is_chapter_heading(stripped_text):
                full_text_parts.append(stripped_text)
                continue
            if MAIN_BODY_X0_MIN <= x0 <= MAIN_BODY_X0_MAX and width >= MIN_WIDTH:
                full_text_parts.append(stripped_text)

    doc.close()
    return "\n".join(full_text_parts)


def update_corpus_record(json_path, pdf_path):
    with open(json_path, "r", encoding="utf-8") as f:
        record = json.load(f)

    old_length = len(record["text"])
    new_text = extract_main_body_text(pdf_path)
    record["text"] = new_text
    record["notes"] = record.get("notes", "") + " [Re-extracted v3: width threshold reduced to a sanity floor only; x0 range is now the sole reliable discriminator for marginal notes.]"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"{json_path}: {old_length} -> {len(new_text)} characters")


update_corpus_record(
    os.path.join("corpus", "bharatiya_nyaya_sanhita_2023.json"),
    os.path.join("raw_pdfs", "bns_2023_gazette.pdf")
)
update_corpus_record(
    os.path.join("corpus", "bharatiya_nagarik_suraksha_sanhita_2023.json"),
    os.path.join("raw_pdfs", "bnss_2023_gazette.pdf")
)