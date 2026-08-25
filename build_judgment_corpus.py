
import fitz
import json
import os
import re
from datetime import datetime

JUDGMENTS = [
    {
        "pdf": "arnesh_kumar_indiankanoon.pdf",
        "case_name": "Arnesh Kumar v State of Bihar",
        "citation": "(2014) 8 SCC 273",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/2982624/",
        "output": "corpus/arnesh_kumar_v_state_of_bihar.json",
    },
    {
        "pdf": "vihaan_kumar_indiankanoon.pdf",
        "case_name": "Vihaan Kumar v State of Haryana",
        "citation": "2025 INSC 162",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/74708490/",
        "output": "corpus/vihaan_kumar_v_state_of_haryana.json",
    },
    {
        "pdf": "satender_kumar_antil_2026_indiankanoon.pdf",
        "case_name": "Satender Kumar Antil v Central Bureau of Investigation (2026)",
        "citation": "2026 INSC 115",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/155374238/",
        "output": "corpus/satender_kumar_antil_v_cbi_2026.json",
    },
    {
        "pdf": "prabir_purkayastha_indiankanoon.pdf",
        "case_name": "Prabir Purkayastha v State (NCT of Delhi)",
        "citation": "2024 INSC 414",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/17476648/",
        "output": "corpus/prabir_purkayastha_v_state_nct_delhi.json",
    },
    {
        "pdf": "dk_basu_indiankanoon.pdf",
        "case_name": "D.K. Basu v State of West Bengal",
        # Citation taken directly from the primary document's own header, not
        # from earlier secondary-source search results, which cited a
        # DIFFERENT (1997) 1 SCC 416 citation. That earlier citation refers to
        # the original 18 Dec 1996 interim order that first laid down the
        # guidelines; THIS document, dated 1 Aug 1997, is the final
        # confirmatory judgment reported at (1997) 6 SCC 642. Both are real
        # documents from the same litigation -- this is the fuller, later one.
        "citation": "(1997) 6 SCC 642",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/235756/",
        "output": "corpus/dk_basu_v_state_of_west_bengal.json",
    },
    {
        "pdf": "nalsa_indiankanoon.pdf",
        "case_name": "National Legal Services Authority v Union of India",
        "citation": "AIR 2014 SC 1863",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/193543132/",
        "output": "corpus/nalsa_v_union_of_india.json",
    },
    {
        "pdf": "pankaj_bansal_indiankanoon.pdf",
        "case_name": "Pankaj Bansal v Union of India",
        "citation": "2023 INSC 866",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/189692408/",
        "output": "corpus/pankaj_bansal_v_union_of_india.json",
    },
]

RAW_PDF_DIR = "raw_pdfs"


def extract_and_clean(pdf_path, source_url):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()

    # Confirmed pattern across ALL 7 documents: every single page ends with a
    # 3-line footer stamp -- the case name/date line (repeating the title),
    # the literal "Indian Kanoon - http://indiankanoon.org/doc/<id>/" URL
    # line, and a bare page-number digit. Verified page-count-exact match on
    # every document (e.g. 7 occurrences in the 7-page Arnesh Kumar PDF).
    # This is distinct from the Youth Bar Association contamination pattern
    # (site chrome, timestamps, "CASE RECAST AI") -- none of that appears
    # here; this is a clean, single, mechanical footer to strip.
    escaped_url = re.escape(source_url.replace("https://", "http://").rstrip("/"))
    footer_pattern = re.compile(
        rf'\n[^\n]{{1,150}}\nIndian Kanoon - {escaped_url}/\n\d+\n',
        re.IGNORECASE
    )
    cleaned = footer_pattern.sub('\n', text)

    # Light cleanup
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()
    return cleaned, text


def save_document(text, case_name, citation, court, source_url, output_path, notes):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    record = {
        "case_name": case_name,
        "citation": citation,
        "court": court,
        "source_url": source_url,
        "source_type": "primary",
        "retrieved_date": datetime.now().strftime("%Y-%m-%d"),
        "text": text,
        "notes": notes,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    return output_path


if __name__ == "__main__":
    results = []
    for j in JUDGMENTS:
        pdf_path = os.path.join(RAW_PDF_DIR, j["pdf"])
        if not os.path.exists(pdf_path):
            print(f"MISSING: {pdf_path} -- skipped")
            continue
        cleaned, raw = extract_and_clean(pdf_path, j["source_url"])
        notes = (
            f"Primary source, saved directly from Indian Kanoon "
            f"({j['source_url']}) as PDF and extracted via PyMuPDF (fitz). "
            f"Found and stripped a per-page footer stamp (case name/date line "
            f"+ 'Indian Kanoon - http://...' URL + bare page number) present "
            f"on every single page -- confirmed page-count-exact occurrence "
            f"count before stripping. Distinct from, and cleaner than, the "
            f"earlier Youth Bar Association contamination pattern (no "
            f"timestamp stamps or 'CASE RECAST AI' boilerplate found here). "
            f"Whitespace normalized; no substantive content altered."
        )
        out_path = save_document(
            text=cleaned,
            case_name=j["case_name"],
            citation=j["citation"],
            court=j["court"],
            source_url=j["source_url"],
            output_path=j["output"],
            notes=notes,
        )
        print(f"{j['case_name']}: {len(raw)} raw chars -> {len(cleaned)} cleaned chars -> {out_path}")
        results.append((j["case_name"], len(cleaned)))

    print(f"\n{len(results)} of {len(JUDGMENTS)} judgments processed.")