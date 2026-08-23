
import fitz
import json
import os
import re

pdf_path = os.path.join("raw_pdfs", "youth_bar_association_indiankanoon.pdf")
doc = fitz.open(pdf_path)
primary_text = ""
for page in doc:
    primary_text += page.get_text()
doc.close()

STRIP_PATTERNS = [
    r'CASE RECAST AI\s*',
    r'8/23/26,?\s*\d{1,2}:\d{2}\s*(AM|PM)\s*',
    r'Youth Bar Association Of India vs Union Of India\s*\.?\s*on 7 September,\s*2016\s*',
    r'https://indiankanoon\.org/doc/151036912/\s*',
    r'(?<!\d)\d/\d(?!\d)\s*',
]

cleaned_text = primary_text
for pattern in STRIP_PATTERNS:
    cleaned_text = re.sub(pattern, ' ', cleaned_text)
cleaned_text = re.sub(r'\s{2,}', ' ', cleaned_text).strip()

with open("corpus/youth_bar_association_v_union_of_india.json", "r", encoding="utf-8") as f:
    record = json.load(f)

old_length = len(record["text"])

record["text"] = cleaned_text
record["source_type"] = "primary"
record["source_url"] = "https://indiankanoon.org/doc/151036912/"
record["notes"] = (
    "[UPGRADED: replaced itatonline digest text with the primary Indian Kanoon transcript "
    "(saved manually via browser, since this document is individually blocked in Indian Kanoon's "
    "robots.txt). Verified against the digest on the FIR-copy provision (guideline a) — substance "
    "matched. Stray print-artifact text ('CASE RECAST AI', repeated page headers) stripped, with a "
    "corrected regex after an initial version wrongly corrupted the case number '68/2016'.]"
)

with open("corpus/youth_bar_association_v_union_of_india.json", "w", encoding="utf-8") as f:
    json.dump(record, f, indent=2, ensure_ascii=False)

print(f"text length: {old_length} -> {len(cleaned_text)} characters")
print(f"\n--- cleaned text preview ---\n{cleaned_text[:800]}")

if "68/2016" in cleaned_text:
    print("\n✓ Case number '68/2016' survived intact.")
else:
    print("\n✗ WARNING: case number pattern not found as expected — check manually.")
    
    
