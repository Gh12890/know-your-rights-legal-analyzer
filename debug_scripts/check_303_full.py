
import fitz
import re

ROW_START_PATTERN = re.compile(r'^\d+[\(\)a-zA-Z0-9]*\s')
HEADER_PREFIX_PATTERN = re.compile(r'^1\s+2\s+3\s+4\s+5\s+6\s+')
NOISE_PATTERNS = [
    re.compile(r'THE GAZETTE OF INDIA EXTRAORDINARY', re.IGNORECASE),
    re.compile(r'^Sec\.\s*\d+\]'),
    re.compile(r'^\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+$'),
]

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")
page = doc[180]
blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))

full_text = ""
capturing = False
for b in blocks:
    text = b[4].strip()
    if not text:
        continue
    if any(p.search(text) for p in NOISE_PATTERNS):
        continue
    text = HEADER_PREFIX_PATTERN.sub('', text)
    if not text:
        continue
    if text.startswith("303(2)"):
        capturing = True
    elif ROW_START_PATTERN.match(text) and capturing:
        break
    if capturing:
        full_text += " " + text

print("FULL raw text for 303(2)'s merged blob:")
print(full_text)
doc.close()
