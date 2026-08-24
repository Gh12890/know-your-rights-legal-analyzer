
import fitz

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")
page = doc[180]
blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))

for b in blocks:
    x0, y0, x1, y1, text, block_no, block_type = b
    stripped = text.strip().replace("\n", " | ")
    if "303" in stripped or "Where value" in stripped or "Snatching" in stripped:
        print(f"x0={x0:.0f}, y0={y0:.0f}, width={x1-x0:.0f} | \"{stripped[:100]}\"")

doc.close()

