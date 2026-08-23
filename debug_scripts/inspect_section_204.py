
import fitz

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")

target_page = None
for i, page in enumerate(doc):
    page_text = page.get_text()
    if "203." in page_text and "journey or voyage" in page_text:
        target_page = i
        break

if target_page is None:
    print("Could not locate the page by text search.")
else:
    print(f"Found candidate page: {target_page}\n")
    page = doc[target_page]
    blocks = page.get_text("blocks")
    blocks_sorted = sorted(blocks, key=lambda b: b[1])

    for b in blocks_sorted:
        x0, y0, x1, y1, text, block_no, block_type = b
        width = x1 - x0
        preview = text.strip().replace("\n", " ")[:80]
        print(f"Block {block_no}: x0={x0:.0f}, y0={y0:.0f}, width={width:.0f} | \"{preview}\"")

doc.close()

