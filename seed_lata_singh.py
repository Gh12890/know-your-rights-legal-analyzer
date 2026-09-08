"""
seed_lata_singh.py  (one-off, 2026-09-08)

Seeds Lata Singh v State of Uttar Pradesh, (2006) 5 SCC 475 into the
corpus -- the missing "right to marry a person of one's own choice"
landmark. Lata Singh is almost exactly the vibeathon test scenario: the
woman's brothers filed a FALSE kidnapping report against the man she
married of her own free will (inter-caste, against the family's wishes),
and his relatives were arrested and jailed. The Supreme Court held that a
major is free to marry whom she likes, that no offence was made out, and
quashed the proceedings as an abuse of process -- and directed police
protection for such couples nationwide.

Writes chunks/lata_singh_v_state_of_uttar_pradesh_chunks.json and
corpus/lata_singh_v_state_of_uttar_pradesh.json, verifying every chunk's
text is a verbatim substring of a fresh clean_document() of the IK doc.

Run:  python seed_lata_singh.py
Then: python embed_corpus.py   (incremental -- only embeds the new chunks)
"""
import json
import os

from dotenv import load_dotenv
load_dotenv()

import indiankanoon_client as ik
from ik_text_cleaner import clean_document

IK_DOC_ID = "1364215"
CASE_NAME = "Lata Singh v State of Uttar Pradesh"
CITATION = "(2006) 5 SCC 475"
SOURCE_URL = f"https://indiankanoon.org/doc/{IK_DOC_ID}/"

CHUNKS_PATH = "chunks/lata_singh_v_state_of_uttar_pradesh_chunks.json"
CORPUS_PATH = "corpus/lata_singh_v_state_of_uttar_pradesh.json"

# Which cleaned-paragraph indices to keep, and the descriptive slug for each.
WANT = {
    16: "major_free_to_marry_no_offence_made_out",
    17: "false_criminal_case_is_abuse_of_process",
    19: "right_of_a_major_to_marry_of_choice_and_police_protection_direction",
}


def main():
    doc = ik.get_document(IK_DOC_ID)
    cleaned = clean_document(doc.get("doc") or "")
    paras = cleaned["paragraphs"]
    body = cleaned["body_text"]

    chunks = []
    for idx, slug in WANT.items():
        text = paras[idx]["text"]
        if text not in body:
            raise SystemExit(f"VERBATIM CHECK FAILED for idx {idx} ({slug})")
        chunks.append({
            "case_name": CASE_NAME,
            "citation": CITATION,
            "source_url": SOURCE_URL,
            "source_type": "primary",
            "opinion_author": None,
            "paragraph_number": slug,
            "text": text,
            "chunk_method": "curated_excerpt",
        })

    os.makedirs("chunks", exist_ok=True)
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    os.makedirs("corpus", exist_ok=True)
    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "case_name": CASE_NAME,
            "citation": CITATION,
            "court": "Supreme Court of India",
            "source_url": SOURCE_URL,
            "source_type": "primary",
            "retrieved_date": "2026-09-08",
            "ik_doc_id": IK_DOC_ID,
            "bench": cleaned.get("bench"),
            "author": cleaned.get("author"),
            "why_seeded": (
                "The corpus had no 'right to marry a person of one's own "
                "choice' landmark. Lata Singh is the on-point authority for "
                "a false kidnapping FIR by a woman's family over a marriage "
                "they disapproved of, and for the police-protection "
                "direction for inter-caste / inter-religious couples."
            ),
            "chunk_slugs": list(WANT.values()),
        }, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(chunks)} verbatim-verified chunks to {CHUNKS_PATH}")
    for c in chunks:
        print(f"  [{c['paragraph_number']}] {c['text'][:90].strip()}...")
    print(f"Wrote {CORPUS_PATH}")
    print("\nNext: python embed_corpus.py")


if __name__ == "__main__":
    main()
