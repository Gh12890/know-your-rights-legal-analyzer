
import fitz
import json
import os
from datetime import datetime


def extract_text_from_pdf(filepath):
    """Same pattern as main.py's extract_text_from_pdf — reused, not reinvented."""
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def save_document(text, case_name, citation, court, source_url, source_type, notes="", output_dir="corpus"):
    """Save a retrieved document with metadata as a JSON record."""
    os.makedirs(output_dir, exist_ok=True)

    record = {
        "case_name": case_name,
        "citation": citation,
        "court": court,
        "source_url": source_url,
        "source_type": source_type,
        "retrieved_date": datetime.now().strftime("%Y-%m-%d"),
        "notes": notes,
        "text": text
    }

    safe_filename = case_name.lower().replace(" ", "_").replace(".", "").replace(",", "") + ".json"
    filepath = os.path.join(output_dir, safe_filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"Saved to {filepath}")
    return filepath


# --- BNS ---
bns_text = extract_text_from_pdf(os.path.join("raw_pdfs", "bns_2023_gazette.pdf"))
save_document(
    text=bns_text,
    case_name="Bharatiya Nyaya Sanhita 2023",
    citation="Act No. 45 of 2023",
    court="Ministry of Law and Justice (Legislative Department) — Official Gazette",
    source_url="https://egazette.gov.in/WriteReadData/2023/250883.pdf",
    source_type="primary",
    notes="Bilingual gazette PDF — contains scrambled Hindi-encoded lines mixed with English text. "
          "Hindi-line cleaning is a known pending task before this is chunk-ready for retrieval."
)

# --- BNSS ---
bnss_text = extract_text_from_pdf(os.path.join("raw_pdfs", "bnss_2023_gazette.pdf"))
save_document(
    text=bnss_text,
    case_name="Bharatiya Nagarik Suraksha Sanhita 2023",
    citation="Act No. 46 of 2023",
    court="Ministry of Home Affairs — Official Gazette (mirrored via MHA site)",
    source_url="https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf",
    source_type="primary",
    notes="Bilingual gazette PDF despite '_english_' in the source filename — still contains scrambled "
          "Hindi-encoded lines mixed with English text. Hindi-line cleaning is a known pending task "
          "before this is chunk-ready for retrieval."
)

print("Both documents saved to corpus/ with metadata.")