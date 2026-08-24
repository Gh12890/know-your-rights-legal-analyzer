
import fitz

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")

target_page = None
for i, page in enumerate(doc):
    page_text = page.get_text()
    if "FIRST SCHEDULE" in page_text and "CLASSIFICATION OF OFFENCES" in page_text:
        target_page = i
        break

if target_page is None:
    print("Could not locate the Schedule's starting page.")
else:
    print(f"Schedule starts on page: {target_page}\n")
    for p_idx in [target_page, target_page + 1]:
        page = doc[p_idx]
        blocks = page.get_text("blocks")
        blocks_sorted = sorted(blocks, key=lambda b: (b[1], b[0]))
        print(f"\n=== Page {p_idx} ===")
        for b in blocks_sorted:
            x0, y0, x1, y1, text, block_no, block_type = b
            width = x1 - x0
            preview = text.strip().replace("\n", " | ")[:60]
            print(f"  x0={x0:.0f}, y0={y0:.0f}, width={width:.0f} | \"{preview}\"")

doc.close()

