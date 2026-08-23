
import fitz

doc = fitz.open("raw_pdfs/bns_2023_gazette.pdf")

page_index = len(doc) // 2
page = doc[page_index]

blocks = page.get_text("blocks")

print(f"Page {page_index} has {len(blocks)} text blocks. Page width: {page.rect.width}\n")

for b in blocks:
    x0, y0, x1, y1, text, block_no, block_type = b
    width = x1 - x0
    preview = text.strip().replace("\n", " ")[:60]
    print(f"Block {block_no}: x0={x0:.0f}, x1={x1:.0f}, width={width:.0f} | \"{preview}\"")

doc.close()