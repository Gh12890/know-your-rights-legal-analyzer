
import fitz
import json
import os

pdf_path = os.path.join("raw_pdfs", "youth_bar_association_indiankanoon.pdf")

doc = fitz.open(pdf_path)
text = ""
for page in doc:
    text += page.get_text()
doc.close()

print(f"Extracted {len(text)} characters from {pdf_path}.\n")
print("--- First 1500 characters ---")
print(text[:1500])


