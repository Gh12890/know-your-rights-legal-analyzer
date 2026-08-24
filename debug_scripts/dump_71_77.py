
import fitz

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")

for page_idx in range(157, 188):
    page = doc[page_idx]
    text = page.get_text()
    if "70" in text or "72" in text or "76" in text or "78" in text:
        print(f"\n{'='*20} PAGE {page_idx} {'='*20}")
        print(text)
        print()
        
