
import fitz
import json
import os
import re

pdf_path = os.path.join("raw_pdfs", "youth_bar_association_indiankanoon.pdf")
doc = fitz.open(pdf_path)
primary_text = ""
for page in doc:
    primary_text += page.get_text()
doc.close()

with open("corpus/youth_bar_association_v_union_of_india.json", "r", encoding="utf-8") as f:
    secondary_record = json.load(f)
secondary_text = secondary_record["text"]

print(f"Primary (Indian Kanoon):  {len(primary_text)} characters")
print(f"Secondary (itatonline):   {len(secondary_text)} characters\n")

print("--- Searching PRIMARY for FIR-copy provision ---")
match = re.search(r'.{0,50}entitled to get a copy of.{0,300}', primary_text, re.DOTALL)
print(match.group(0) if match else "NOT FOUND in primary text")

print("\n--- Searching SECONDARY for the same provision ---")
match2 = re.search(r'.{0,50}entitled to get a copy of.{0,300}', secondary_text, re.DOTALL)
print(match2.group(0) if match2 else "NOT FOUND in secondary text")
