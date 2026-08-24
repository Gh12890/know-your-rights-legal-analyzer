
import fitz

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")

TARGETS = ["85", "86", "87", "113", "114", "115", "137", "138", "139", "269", "270", "271", "329", "330", "331", "334", "335", "336"]

for page_idx in range(157, 188):
    page = doc[page_idx]
    text = page.get_text()
    for t in TARGETS:
        if t in text:
            idx = text.find(t)
            context = text[max(0,idx-20):idx+80].replace("\n", " | ")
            print(f"Page {page_idx}, '{t}': ...{context}...")
doc.close()


