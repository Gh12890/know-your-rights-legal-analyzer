
import json
import os
import re
import glob
from corpus_qa import verify_section_coverage, DEFAULT_SECTION_PATTERN


def find_section_boundaries(text):
    boundaries = []
    offset = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if DEFAULT_SECTION_PATTERN.match(stripped):
            m = re.match(r'^(\d+[A-Z]?)', stripped)
            if m:
                boundaries.append((offset, m.group(1)))
        offset += len(line) + 1
    return boundaries


def chunk_document(text, act_name, citation, source_url, source_type):
    boundaries = find_section_boundaries(text)
    chunks = []

    if boundaries and boundaries[0][0] > 0:
        preamble_text = text[:boundaries[0][0]].strip()
        if preamble_text:
            chunks.append({
                "act_name": act_name,
                "citation": citation,
                "section_number": "preamble",
                "text": preamble_text,
                "source_url": source_url,
                "source_type": source_type,
            })

    for i, (start_offset, section_num) in enumerate(boundaries):
        end_offset = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        section_text = text[start_offset:end_offset].strip()
        chunks.append({
            "act_name": act_name,
            "citation": citation,
            "section_number": section_num,
            "text": section_text,
            "source_url": source_url,
            "source_type": source_type,
        })

    return chunks


def chunk_corpus_file(json_path, output_dir="chunks"):
    with open(json_path, "r", encoding="utf-8") as f:
        record = json.load(f)

    qa_report = verify_section_coverage(record["text"])
    print(f"\n{json_path}")
    print(f"  QA: {qa_report['summary']}")

    if not qa_report["passed"]:
        print("  SKIPPED — document failed QA, will not chunk broken data.")
        return None

    chunks = chunk_document(
        text=record["text"],
        act_name=record["case_name"],
        citation=record["citation"],
        source_url=record["source_url"],
        source_type=record["source_type"],
    )

    os.makedirs(output_dir, exist_ok=True)
    safe_name = record["case_name"].lower().replace(" ", "_").replace(".", "").replace(",", "")
    out_path = os.path.join(output_dir, f"{safe_name}_chunks.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"  Wrote {len(chunks)} chunks to {out_path}")
    return out_path


if __name__ == "__main__":
    for filepath in glob.glob("corpus/*.json"):
        chunk_corpus_file(filepath)
        
