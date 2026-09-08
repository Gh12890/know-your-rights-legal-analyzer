"""
Vibeathon Step 3 corpus top-up (batch 4).

Two cases, both cleanly on-point for a hero scenario, both fetched live,
cleaned, checked for finality, and curated into curated_excerpt chunks using
ONLY the court's own operative words (no block-quotes-of-other-cases).

  - Lalita Kumari v Government of Uttar Pradesh, (2014) 2 SCC 1 (Constitution
    Bench) -> FIR_NOT_REGISTERED. The operative holding para 111 (i,ii,iv,v,
    vi,vii) + the framed issue.
  - Deepa v S. Vijayalakshmi (Madras HC, DB, 7 Feb 2025) -> ARREST_WOMAN
    night-arrest right. Squarely on Section 43(5) BNSS: holds it directory,
    not mandatory (the exact nuance statute_doctrine_map already carries).

Run from the project root:  python seed_batch4.py
Writes chunks/lalita_kumari_v_government_of_uttar_pradesh_chunks.json and
chunks/deepa_v_s_vijayalakshmi_chunks.json, then verifies every chunk text is
a verbatim substring of a fresh clean_document() of the same doc.
"""
import json
import os
import re
from dotenv import load_dotenv
load_dotenv()

import indiankanoon_client as ik
from ik_text_cleaner import clean_document
from ik_triage import classify_document_finality

# Page furniture the Madras HC PDF embeds mid-paragraph (running header /
# footer / URL / page-of-page). Dropping these lines is cosmetic cleanup of
# non-substantive OCR artefacts, not editing the court's words -- the
# verbatim check below runs against a body denoised the same way.
_NOISE = re.compile(
    r"^\s*(https?://\S+"
    r"|\d{1,3}/\d{1,3}"
    r"|W\.A\.?\(MD\)\s*Nos?\..*"
    r"|W\.P\.?\s*No\..*"
    r"|\x0c)\s*$"
)


def _denoise(text: str) -> str:
    lines = [ln for ln in (text or "").splitlines() if not _NOISE.match(ln)]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()

SPECS = [
    {
        "slug": "lalita_kumari_v_government_of_uttar_pradesh",
        "docid": "10239019",
        "case_name": "Lalita Kumari v Government of Uttar Pradesh",
        "citation": "(2014) 2 SCC 1",
        "source_url": "https://indiankanoon.org/doc/10239019/",
        "chunks": [
            ("111_issue_bound_to_register_fir", [2]),
            ("111_i_ii_registration_mandatory_no_preliminary_inquiry", [225, 226]),
            ("111_iv_v_duty_to_register_and_scope_of_preliminary_inquiry", [228, 229]),
            ("111_vi_vii_categories_for_preliminary_inquiry_and_time_limit",
             [231, 232, 233, 234, 235, 236, 237, 238]),
        ],
    },
    {
        "slug": "deepa_v_s_vijayalakshmi",
        "docid": "99998710",
        "case_name": "Deepa v S. Vijayalakshmi",
        "citation": "2025 SCC OnLine Mad (MD) (W.A.(MD) Nos. 1155 of 2020, 1200 & 1216 of 2019)",
        "source_url": "https://indiankanoon.org/doc/99998710/",
        "chunks": [
            ("issue_whether_s43_5_bnss_is_mandatory", [12]),
            ("s43_5_bnss_identically_worded_to_s46_4_crpc", [20]),
            ("held_s46_4_crpc_s43_5_bnss_not_mandatory", [22]),
            ("no_consequence_of_non_compliance_victim_cannot_suffer", [27]),
        ],
    },
]


def build(spec):
    doc = ik.get_document(spec["docid"])
    cleaned = clean_document(doc.get("doc") or "")
    paras = cleaned["paragraphs"]
    finality = classify_document_finality(paras)
    print(f"\n{spec['case_name']}  (doc {spec['docid']}, {len(paras)} paras)")
    print(f"  finality: {finality}")
    if finality["is_procedural_order"] is True:
        raise SystemExit(f"  ABORT: {spec['slug']} classified as a procedural order")

    full_body = _denoise("\n".join((p.get("text") or "") for p in paras))
    records = []
    for label, idxs in spec["chunks"]:
        text = "\n\n".join(_denoise(paras[i].get("text") or "") for i in idxs)
        # verbatim guarantee: each denoised component paragraph must appear
        # in the denoised body
        for i in idxs:
            frag = _denoise(paras[i].get("text") or "")
            if frag and frag not in full_body:
                raise SystemExit(f"  NOT VERBATIM: {spec['slug']} idx {i}")
        records.append({
            "case_name": spec["case_name"],
            "citation": spec["citation"],
            "source_url": spec["source_url"],
            "source_type": "primary",
            "opinion_author": None,
            "paragraph_number": label,
            "text": text,
            "chunk_method": "curated_excerpt",
        })
        print(f"  + {label}  ({len(text)} chars)")

    path = os.path.join("chunks", f"{spec['slug']}_chunks.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"  wrote {path}  ({len(records)} chunks)")

    # re-verify from a completely fresh fetch+clean
    doc2 = ik.get_document(spec["docid"])
    body2 = _denoise("\n".join((p.get("text") or "")
                     for p in clean_document(doc2.get("doc") or "")["paragraphs"]))
    for r in records:
        for part in r["text"].split("\n\n"):
            if part.strip() and part.strip() not in body2:
                raise SystemExit(f"  RE-VERIFY FAILED: {spec['slug']} / {r['paragraph_number']}")
    print("  re-verify OK (fresh fetch)")


if __name__ == "__main__":
    for s in SPECS:
        build(s)
    print("\nDONE. Next: python embed_corpus.py")
