
import fitz

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")

TARGETS = ["100", "101", "102", "128", "129", "130"]

for page_idx in range(157, 188):
    page = doc[page_idx]
    page_text = page.get_text()
    found_here = [t for t in TARGETS if f"\n{t} " in page_text or page_text.strip().startswith(t)]
    if found_here:
        print(f"Page {page_idx}: contains {found_here}")

doc.close()


