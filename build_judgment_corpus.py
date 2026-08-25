
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
    
        {
        # Re-download of the original Youth Bar Association source, which had
        # confirmed contamination (2 stray private-use-area glyphs at the
        # very start, likely captured UI icons; truncated party labels
        # "Petitio"/"Respond") found by judgment_qa.py. This v2 download,
        # via the same clean method used for the other 7 judgments this
        # session, opens directly with the real case caption -- no glyphs
        # found on inspection. Replaces the original corpus record.
        "pdf": "youth_bar_association_indiankanoon_v2.pdf",
        "case_name": "Youth Bar Association v Union of India",
        "citation": "AIR 2016 SC 4136",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/151036912/",
        "output": "corpus/youth_bar_association_v_union_of_india.json",
    },
    {
        "pdf": "l_muruganantham_indiankanoon.PDF",
        "case_name": "L. Muruganantham v State of Tamil Nadu",
        "citation": "2025 INSC 844",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/77627897/",
        "output": "corpus/l_muruganantham_v_state_of_tamil_nadu.json",
    },
        {
        # NOT a Supreme Court judgment -- see main-block note below. Kept in
        # the corpus per explicit user decision (2026-08-25) to broaden
        # beyond pure SC precedent rather than drop non-SC sources.
        #
        # CONFIRMED: this document does NOT cite or apply Arnesh Kumar,
        # D.K. Basu, Vihaan Kumar, or Satender Kumar Antil anywhere in its
        # text (checked directly) -- it is a 2020 civil writ petition
        # against Bihar's Excise Department, unrelated in subject matter to
        # the arrest-procedure doctrine line the rest of this corpus is
        # built around. Kept per user instruction, but it is NOT an
        # applying-precedent source for anything main.py currently checks.
        "pdf": "prakash_ranjan_indiankanoon.PDF",
        "case_name": "Prakash Ranjan v State of Bihar",
        "citation": "Civil Writ Jurisdiction Case No. 20349 of 2019",
        "court": "High Court of Judicature at Patna",
        "source_url": "https://indiankanoon.org/doc/195353027/",
        "output": "corpus/prakash_ranjan_v_state_of_bihar.json",
    },
    {
        # NOT a Supreme Court judgment -- see main-block note below.
        #
        # CONFIRMED: this document cites and applies Arnesh Kumar v State of
        # Bihar and Satender Kumar Antil v CBI (checked directly). It is an
        # APPLYING/ILLUSTRATIVE precedent, not a binding rule-source -- it
        # shows a High Court applying existing Supreme Court doctrine to a
        # specific fact pattern (per user framing, 2026-08-26: HC judgments
        # in this corpus mainly reiterate SC precedent rather than create
        # new binding law). Should be presented, if ever surfaced, as an
        # example of application/consequences, subordinate to and never
        # replacing the Arnesh Kumar / Satender Kumar Antil corpus entries.
        "pdf": "rakhi_mitra_indiankanoon.PDF",
        "case_name": "Rakhi Mitra and Anr v State of West Bengal",
        "citation": "2025:CHC-AS:1826",
        "court": "High Court at Calcutta",
        "source_url": "https://indiankanoon.org/doc/106336343/",
        "output": "corpus/rakhi_mitra_v_state_of_west_bengal.json",
    },
    {
        # NOT a Supreme Court judgment -- see main-block note below.
        #
        # CONFIRMED: this document cites and applies Arnesh Kumar v State of
        # Bihar (checked directly). Same APPLYING/ILLUSTRATIVE status as
        # Rakhi Mitra above -- shows a High Court applying Arnesh Kumar to
        # quash proceedings on vague S.498A-style allegations. Subordinate
        # to, never a substitute for, the Arnesh Kumar corpus entry itself.
        "pdf": "sri_manjunath_mp_indiankanoon.PDF",
        "case_name": "Sri Manjunath M P v State of Karnataka",
        "citation": "2026:KHC:2726",
        "court": "High Court of Karnataka at Bengaluru",
        "source_url": "https://indiankanoon.org/doc/107568550/",
        "output": "corpus/sri_manjunath_mp_v_state_of_karnataka.json",
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
        # NOTE: an earlier version of this pattern required a literal leading
    # \n before the case-name-repeat line and an optional trailing \n after
    # the page number. That created a REAL overlap bug: re.sub/finditer
    # don't allow overlapping matches, and each match's trailing \n was
    # also the NEXT footer's required leading \n -- so whichever footer's
    # leading \n got "consumed" by the previous match's greedy trailing \n
    # would silently fail to match. This surfaced as exactly the LAST
    # footer on every document surviving un-stripped (confirmed real case:
    # Prakash Ranjan, caught by judgment_qa.py). Fixed by not requiring a
    # leading \n at all -- the "Indian Kanoon - <url>" line itself is
    # distinctive enough to anchor on without it.
    escaped_url = re.escape(source_url.replace("https://", "http://").rstrip("/"))
    footer_pattern = re.compile(
        rf'[^\n]{{1,150}}\nIndian Kanoon - {escaped_url}/\n\d+\n?',
        re.IGNORECASE
    )
    cleaned = footer_pattern.sub('', text)

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
        if j["pdf"] == "satender_kumar_antil_2026_indiankanoon.pdf":
            notes += (
                ' KNOWN DEFECT: PDF source has a pre-existing text-extraction artifact (confirmed present'
                ' in the raw PyMuPDF output before any cleanup) truncating 3 words in the page-1 case'
                ' caption only: "REPORTABLE" -> "REPOR", "PETITIONER" -> "P", "RESPONDENTS" -> "RES".'
                ' Confirmed isolated to the caption block; the substantive judgment text (holdings,'
                ' reasoning) reads clean with no other documents in this batch showing the same defect.'
                ' Not corrected, since guessing the missing letters would mean inserting text not actually'
                ' extracted from the source -- left as-is and flagged here instead, consistent with the'
                ' "Cannot Determine over silent guessing" principle used elsewhere in this project.'
            )
        if j["pdf"] in (
            "prakash_ranjan_indiankanoon.PDF",
            "rakhi_mitra_indiankanoon.PDF",
            "sri_manjunath_mp_indiankanoon.PDF",
        ):
            notes += (
                ' DEVIATION FROM CORPUS NORM: every other record in this corpus is a Supreme Court of'
                ' India judgment, added to ground the "binding Supreme Court procedural requirements" this'
                ' project checks against (see README). This record is a High Court judgment instead'
                f' ({j["court"]}) and is not currently cited anywhere in main.py\'s compliance logic.'
                ' Kept in the corpus per explicit user decision (2026-08-25) to broaden sourcing rather than'
                ' drop it, but it should NOT be treated as equivalent authority to the Supreme Court records'
                ' here -- a High Court ruling binds only within its own state/UT, not nationally.'
            )
        if j["pdf"] == "prakash_ranjan_indiankanoon.PDF":
            notes += (
                ' PRECEDENT STATUS (confirmed by direct text search, 2026-08-26): this document does NOT'
                ' cite Arnesh Kumar, D.K. Basu, Vihaan Kumar, or Satender Kumar Antil anywhere -- it is a'
                ' 2020 civil writ petition against Bihar\'s Excise Department, topically unrelated to the'
                ' arrest-procedure doctrine line the rest of this corpus grounds. It is NOT an applying-'
                ' precedent source for anything currently checked in main.py.'
            )
        if j["pdf"] in ("rakhi_mitra_indiankanoon.PDF", "sri_manjunath_mp_indiankanoon.PDF"):
            cited = "Arnesh Kumar v State of Bihar and Satender Kumar Antil v CBI" if j["pdf"] == "rakhi_mitra_indiankanoon.PDF" else "Arnesh Kumar v State of Bihar"
            notes += (
                f' PRECEDENT STATUS (confirmed by direct text search, 2026-08-26): this document cites and'
                f' applies {cited}. Per user framing (2026-08-26): High Court judgments in this corpus mainly'
                f' reiterate/apply existing Supreme Court precedent rather than create new binding law. This'
                f' record is an APPLYING/ILLUSTRATIVE precedent -- useful for showing practical consequences'
                f' and how a court rules when the cited Supreme Court doctrine is applied to specific facts --'
                f' not a rule-source in its own right. If ever surfaced by retrieval logic, it should be'
                f' presented as an example of application, clearly subordinate to and never in place of the'
                f' Supreme Court judgment(s) it applies.'
            )
        if j["pdf"] == "youth_bar_association_indiankanoon_v2.pdf":
            notes += (
                ' [SUPERSEDED 2026-08-25]: Replaced an earlier download (same source_url, same case) after'
                ' judgment_qa.py flagged 2 stray private-use-area Unicode glyphs (U+EDD9, U+EDDA, likely'
                ' captured UI icon fonts) and truncated party labels ("Petitio"/"Respond") in that'
                ' extraction. This download shows neither defect on re-verification with judgment_qa.py --'
                ' opens directly with the real case caption, no stray glyphs found, party labels intact.'
                ' One benign QA flag remains (closing-signature heuristic miss on the Court Master sign-off'
                ' format, same false-positive pattern seen on D.K. Basu and Pankaj Bansal -- confirmed NOT'
                ' a truncation on manual inspection).'
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