
import fitz
import re
import json

ROW_START_PATTERN = re.compile(r'^\d+[\(\)a-zA-Z0-9]*\s')

NOISE_PATTERNS = [
    re.compile(r'THE GAZETTE OF INDIA EXTRAORDINARY', re.IGNORECASE),
    re.compile(r'^Sec\.\s*\d+\]'),
    re.compile(r'^\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+$'),
]

HEADER_PREFIX_PATTERN = re.compile(r'^1\s+2\s+3\s+4\s+5\s+6\s+')
CONTINGENT_PATTERN = re.compile(r'According as|Same as for( the)? offence', re.IGNORECASE)

SUBCONDITION_X0_MIN = 85
SUBCONDITION_X0_MAX = 105


def is_noise(text):
    return any(p.search(text) for p in NOISE_PATTERNS)


def strip_fused_header(text):
    return HEADER_PREFIX_PATTERN.sub('', text)


def extract_schedule_rows(pdf_path, start_page, end_page):
    doc = fitz.open(pdf_path)
    rows = []
    current_row_text = ""
    current_section = None
    subcondition_texts = []

    def flush_current():
        if current_section is not None:
            rows.append({
                "section": current_section,
                "raw_text": current_row_text.strip(),
                "subconditions": list(subcondition_texts)
            })

    for page_idx in range(start_page, end_page + 1):
        page = doc[page_idx]
        blocks = page.get_text("blocks")
        blocks_sorted = sorted(blocks, key=lambda b: (b[1], b[0]))

        for b in blocks_sorted:
            x0, y0, x1, y1, text, block_no, block_type = b
            stripped = text.strip()
            if not stripped or is_noise(stripped):
                continue

            stripped = strip_fused_header(stripped)
            if not stripped:
                continue

            if ROW_START_PATTERN.match(stripped):
                flush_current()
                m = re.match(r'^(\d+[\(\)a-zA-Z0-9]*)', stripped)
                current_section = m.group(1)
                current_row_text = stripped
                subcondition_texts = []
            elif SUBCONDITION_X0_MIN <= x0 <= SUBCONDITION_X0_MAX and current_section is not None:
                subcondition_texts.append(stripped)
            else:
                current_row_text += " " + stripped

    flush_current()
    doc.close()
    return rows


def classify_text(raw_text):
    if CONTINGENT_PATTERN.search(raw_text):
        return "contingent", "contingent"

    if re.search(r'\bNon-cognizable\b', raw_text, re.IGNORECASE):
        cognizable = False
    elif re.search(r'\bCognizable\b', raw_text, re.IGNORECASE):
        cognizable = True
    else:
        cognizable = None

    if re.search(r'\bNon-bailable\b', raw_text, re.IGNORECASE):
        bailable = False
    elif re.search(r'\bBailable\b', raw_text, re.IGNORECASE):
        bailable = True
    else:
        bailable = None

    return cognizable, bailable


rows = extract_schedule_rows("raw_pdfs/bnss_2023_gazette.pdf", 157, 187)
print(f"Extracted {len(rows)} raw row candidates.\n")

schedule_data = {}
unclassified = []
contingent_count = 0
multi_entry_count = 0

for row in rows:
    cognizable, bailable = classify_text(row["raw_text"])
    if cognizable == "contingent":
        contingent_count += 1
    elif cognizable is None or bailable is None:
        unclassified.append(row["section"])

    entry = {
        "cognizable": cognizable,
        "bailable": bailable,
        "raw_text_preview": row["raw_text"][:150],
        "condition": "general"
    }

    if row["subconditions"]:
        multi_entry_count += 1
        sub_entries = []
        for sub_text in row["subconditions"]:
            sub_cog, sub_bail = classify_text(sub_text)
            sub_entries.append({
                "cognizable": sub_cog,
                "bailable": sub_bail,
                "raw_text_preview": sub_text[:150],
                "condition": sub_text[:80]
            })
        schedule_data[row["section"]] = [entry] + sub_entries
    else:
        schedule_data[row["section"]] = entry

with open("bnss_first_schedule.json", "w", encoding="utf-8") as f:
    json.dump(schedule_data, f, indent=2, ensure_ascii=False)

print(f"Saved {len(schedule_data)} section entries to bnss_first_schedule.json")
print(f"Sections with multiple conditional entries: {multi_entry_count}")
print(f"Contingent entries: {contingent_count}")
print(f"Unclassified: {len(unclassified)} -> {unclassified[:30]}")

print(f"\n--- Spot check: Section 303(2) should now be a LIST of 2 entries ---")
print(json.dumps(schedule_data.get("303(2)"), indent=2))

print(f"\n--- Spot check: Section 64(1) unchanged, single entry ---")
for key in schedule_data:
    if key.startswith("64(1)"):
        print(json.dumps(schedule_data[key], indent=2))
        
