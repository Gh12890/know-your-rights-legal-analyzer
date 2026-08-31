
"""
build_cheque_bounce_judgment_corpus.py

Sources the 5 cheque-bounce Supreme Court judgments read and verified
in this session (2026-08-30) into the SAME corpus record shape
build_judgment_corpus.py and build_freeze_judgment_corpus.py already
produce, so chunk_judgments.py, judgment_qa.py, and embed_corpus.py all
work on these unmodified.

Each case was read IN FULL and its vital holding distilled before
being included here -- see each entry's "notes" field for what was
specifically established and how it feeds into the cheque-bounce
module's redesigned architecture.
"""

import json
import os
from datetime import datetime

from indiankanoon_client import get_document
from ik_text_cleaner import clean_document

CHEQUE_BOUNCE_JUDGMENTS = [
    {
        "tid": "150051",
        "case_name": "Rangappa v Sri Mohan",
        "citation": "(2010) 11 SCC 441",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/150051/",
        "output": "corpus/rangappa_v_sri_mohan.json",
        "notes": (
            "Read in full, 2026-08-30. VITAL HOLDING: Section 139's presumption "
            "of a legally enforceable debt/liability is MANDATORY, not merely "
            "permissive, and extends to the existence of the debt itself -- "
            "not just the accused's signature (overruling the narrower view "
            "in K.N. Beena). Once signature is admitted/proved, the burden "
            "shifts entirely to the accused to rebut on a PREPONDERANCE OF "
            "PROBABILITIES -- rebuttal can come from positive defence "
            "evidence or effective cross-examination alone, but a bare denial "
            "is insufficient. FEEDS INTO: explain_debt_presumption_status "
            "(new function) -- this case establishes that 'was this an "
            "enforceable debt' is not a fact the tool can verify from a "
            "notice; it is a rebuttable legal presumption the case itself "
            "resolves."
        ),
    },
    {
        "tid": "157736723",
        "case_name": "Bir Singh v Mukesh Kumar",
        "citation": "(2019) 4 SCC 197",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/157736723/",
        "output": "corpus/bir_singh_v_mukesh_kumar.json",
        "notes": (
            "Read in full, 2026-08-30. VITAL HOLDING: the Section 139 "
            "presumption arises automatically once signature is admitted, "
            "EVEN IF the complainant never specifically deposes the cheque "
            "was given 'in discharge of' a debt. Two concrete sub-holdings: "
            "(1) a BLANK CHEQUE voluntarily signed and handed over, later "
            "filled in by the payee, still attracts the presumption; (2) a "
            "'FRIENDLY LOAN' or informal, undocumented lending arrangement "
            "does NOT defeat the presumption. FEEDS INTO: "
            "explain_debt_presumption_status -- rules out 'it was a blank "
            "cheque' and 'it was just an informal loan' as standalone "
            "defences."
        ),
    },
    {
        "tid": "1594211",
        "case_name": "Damodar S. Prabhu v Sayed Babalal H",
        "citation": "(2010) 5 SCC 663",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/1594211/",
        "output": "corpus/damodar_s_prabhu_v_sayed_babalal_h.json",
        "notes": (
            "Read in full, 2026-08-30. VITAL HOLDING: establishes a binding, "
            "graduated cost-imposition scheme for compounding Section 138 "
            "cases -- minimal/no cost if compounded at first or second "
            "hearing; escalating cost (roughly 10% of cheque amount at trial "
            "court post-conviction, 15% at High Court, 20% at Supreme Court) "
            "payable to a legal aid fund if compounded later. Confirms "
            "compounding remains available at any stage, including after "
            "conviction and on appeal. NOT about guilt, defences, or "
            "presumptions -- purely about strategy/timing of resolution. "
            "FEEDS INTO: compute_settlement_cost_incentive (new function, "
            "informational sidebar, NEVER a compliance verdict -- same "
            "pattern as compute_bail_pathway_info elsewhere in this "
            "project)."
        ),
    },
    {
        "tid": "175356438",
        "case_name": "Kaveri Plastics v Mahdoom Bawa Bahrudeen Noorul",
        "citation": "2025 INSC (Supreme Court, 19 September 2025)",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/175356438/",
        "output": "corpus/kaveri_plastics_v_mahdoom_bawa_bahrudeen_noorul.json",
        "notes": (
            "Read in full, 2026-08-30. TWO SEPARATE VITAL HOLDINGS in this "
            "one judgment. "
            "(1) SECURITY/MATURITY HOLDING: a cheque given as security for a "
            "FUTURE OR CONTINGENT liability does NOT attract Section 138 if "
            "dishonoured before the liability matures. The label 'security "
            "cheque' is NOT itself determinative -- what matters is whether "
            "the debt had actually become due and payable AT THE TIME OF "
            "DISHONOUR. FEEDS INTO: check_debt_maturity_status (new "
            "function) -- replaces the old flat 'debt vs security' binary. "
            "(2) AMOUNT-MATCHING HOLDING (paragraph 14, quoting Suman Sethi "
            "v Ajay K. Churiwal, (2000) 2 SCC 380, VERBATIM -- cited via this "
            "quotation rather than a separate fetch, per explicit 2026-08-30 "
            "decision): the demand notice must clearly and specifically "
            "demand the CHEQUE AMOUNT itself. ADDITIONAL amounts (interest, "
            "costs) mentioned ALONGSIDE the cheque amount do NOT by "
            "themselves invalidate the notice, PROVIDED the cheque amount "
            "remains specifically and severably demanded. This directly "
            "corrects the previous check_amount_match, which treated ANY "
            "co-mention of interest as an automatic defect regardless of "
            "severability. FEEDS INTO: corrected check_amount_match."
        ),
    },
    {
        "tid": "178325150",
        "case_name": "Prakash Chimanlal Sheth v Jagruti Keyur Rajpopat",
        "citation": "2025 INSC 897",
        "court": "Supreme Court of India",
        "source_url": "https://indiankanoon.org/doc/178325150/",
        "output": "corpus/prakash_chimanlal_sheth_v_jagruti_keyur_rajpopat.json",
        "notes": (
            "Read in full, 2026-08-30. VITAL HOLDING: a Section 138 "
            "complaint must be filed at the place where the cheque was "
            "PRESENTED FOR COLLECTION and dishonoured -- not wherever the "
            "complainant resides, not where the loan was advanced, not "
            "where the demand notice was sent from. Applies and reaffirms "
            "the binding territorial-jurisdiction framework from the "
            "Constitution Bench in Dashrath Rupsingh Rathod v State of "
            "Maharashtra (2014), codified in Section 142(2) NI Act (2015 "
            "amendment). A pure procedural/venue gatekeeping question, "
            "structurally similar to the arrest module's cognizability "
            "check or the freeze module's Section 106/107 authorization "
            "check. FEEDS INTO: check_jurisdiction (new function)."
        ),
    },
]


def build_and_save(entry):
    doc = get_document(entry["tid"])
    cleaned = clean_document(doc["doc"])
    text = cleaned["body_text"]

    os.makedirs(os.path.dirname(entry["output"]), exist_ok=True)
    record = {
        "case_name": entry["case_name"],
        "citation": entry["citation"],
        "court": entry["court"],
        "source_url": entry["source_url"],
        "source_type": "primary",
        "retrieved_date": datetime.now().strftime("%Y-%m-%d"),
        "text": text,
        "notes": entry["notes"],
    }
    with open(entry["output"], "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"{entry['case_name']}: {len(text)} chars -> {entry['output']}")
    return entry["output"]


if __name__ == "__main__":
    results = []
    for entry in CHEQUE_BOUNCE_JUDGMENTS:
        out_path = build_and_save(entry)
        results.append((entry["case_name"], out_path))

    print(f"\n{len(results)} of {len(CHEQUE_BOUNCE_JUDGMENTS)} cheque-bounce judgments processed.")
    print("\nNext step: run chunk_judgments.py, which will pick these up")
    print("automatically from corpus/*.json alongside the existing 15.")
    
