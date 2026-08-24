
import fitz
import re

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")

pattern = re.compile(r'(?<!\d)86(?!\d)')

for page_idx in range(157, 188):
    page = doc[page_idx]
    text = page.get_text()
    for m in pattern.finditer(text):
        idx = m.start()
        context = text[max(0,idx-40):idx+100].replace("\n", " | ")
        print(f"Page {page_idx}: ...{context}...")

doc.close()

