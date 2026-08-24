
import fitz

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")

TARGETS = ["100", "101", "102", "128", "129", "130"]

for page_idx in range(157, 188):
    page = doc[page_idx]
    page_text = page.get_text()
    for t in TARGETS:
        if t in page_text:
            idx = page_text.find(t)
            context = page_text[max(0,idx-30):idx+60].replace("\n", " | ")
            print(f"Page {page_idx}: found '{t}' — context: ...{context}...")
            
