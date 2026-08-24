
import fitz

doc = fitz.open("raw_pdfs/bnss_2023_gazette.pdf")

for i, page in enumerate(doc):
    page_text = page.get_text()
    if "THE FIRST SCHEDULE" in page_text:
        print(f"Page {i}: contains 'THE FIRST SCHEDULE'")
    if "CLASSIFICATION OF OFFENCES AGAINST OTHER LAWS" in page_text or "II.—CLASSIFICATION" in page_text:
        print(f"Page {i}: contains Part II header (offences against other laws)")
    if "THE SECOND SCHEDULE" in page_text:
        print(f"Page {i}: contains 'THE SECOND SCHEDULE' (end boundary)")

doc.close()

