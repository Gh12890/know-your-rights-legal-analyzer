
"""
itact_section_data.py

Structured cognizable/bailable/punishment data for the Information
Technology Act, 2000 criminal sections -- Phase 3b of the
loc-transit-remand-plan. Mirrors bns_section_data_v2.py's shape exactly
(a flat dict, same per-section schema: offence, max_years, max_months,
life_or_death, punishment_shape, cognizable, bailable,
has_multiple_conditions, needs_review, [all_conditions]) so every
existing consumer of BNS_SECTION_DATA's schema (chat_assistant.py's
enrichment, semantic_retrieval.py's variant formatting) generalizes to
this table with the same code shape.

SOURCING: real Bare Act text fetched from Indian Kanoon's own
section-index (e.g. "Section 66 in The Information Technology Act,
2000", tid 326206 -- IK indexes individual central-act sections as
their own documents, sourced from the official gazette/India Code the
same way judgment text is) -- NOT recalled from training data. The
official India Code PDF (indiacode.nic.in) returned HTTP 403 when
fetched directly.

COGNIZABLE/BAILABLE RULE: Section 77B of the IT Act (inserted by the
2008 Amendment) states -- confirmed via a real, verbatim quote in Dr.
K.A. Koshy v State of Kerala (Kerala HC, 2010) AND cross-checked against
an independent secondary source -- "notwithstanding anything contained
in the Code of Criminal Procedure, 1973, the offence punishable with
imprisonment of three years and above shall be cognizable and the
offence punishable with imprisonment of three years shall be bailable."
Applied here as: >=3 years -> cognizable; <=3 years -> bailable (so an
offence with EXACTLY a 3-year ceiling is BOTH -- confirmed as the real,
applied outcome in Ambikesh Mahapatra v State of West Bengal, Calcutta
HC 2015, where a 3-year IT Act offence was treated as cognizable AND
the accused were held entitled to bail from the police station itself).
This is a mechanical application of a real, quoted statutory rule, same
discipline as how BNSS's First Schedule mechanically drives
BNS_SECTION_DATA's cognizable/bailable fields -- not a guess.

DELIBERATELY EXCLUDED: Section 66A. It was struck down as
unconstitutional (Shreya Singhal v Union of India, (2015) 5 SCC 1) --
see itact_section_status.py, Phase 3a. Including it here would wrongly
imply it is valid, in-force law with a real cognizable/bailable
classification to state; that module's dedicated override handles it
correctly (a struck-down-status flag, not a "current text" lookup) and
already runs earlier in chat_assistant.py's override chain, so this
table intentionally has no "66A" key at all.
"""

import json
import os

_TABLE_PATH = os.path.join(os.path.dirname(__file__), "itact_section_data.json")

with open(_TABLE_PATH, "r", encoding="utf-8") as _f:
    _raw_table = json.load(_f)

ITACT_SECTION_DATA = _raw_table


if __name__ == "__main__":
    print(f"Loaded {len(ITACT_SECTION_DATA)} sections from {_TABLE_PATH}")
    clean = sum(1 for v in ITACT_SECTION_DATA.values() if not v.get("needs_review"))
    print(f"  {clean} fully clean, {len(ITACT_SECTION_DATA) - clean} flagged needs_review")
    assert "66A" not in ITACT_SECTION_DATA, "66A must stay excluded -- see module docstring"
