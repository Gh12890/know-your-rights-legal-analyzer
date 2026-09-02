
from main import BNS_SECTION_DATA, get_max_years_from_sections, build_grounded_section_context, compute_bail_pathway_info

TEST_CASES = {
    "A clean, simple section": ["57"],
    "A life-or-death section": ["64(1)"],
    "A contingent/needs_review section": ["49"],
    "A mix of clean and contingent": ["57", "49"],
    "An unrecognized section": ["999999"],
}

for label, sections in TEST_CASES.items():
    print(f"\n{'='*20} {label}: {sections} {'='*20}")

    print("build_grounded_section_context:")
    print(build_grounded_section_context(sections))

    print("\nget_max_years_from_sections:")
    print(get_max_years_from_sections(sections))

    print("\ncompute_bail_pathway_info:")
    print(compute_bail_pathway_info(sections))


# ---- Project 3: draft layer, assembled from a synthetic arrest analysis ----
from draft_layer import draft_for

_demo_analysis = {
    "extracted_fields": {"sections_cited": ["303(2)"], "arrest_datetime_full": "12-07-2026 09:30"},
    "compliance": {"compliance_checks": [
        {"requirement": "S.35(3) BNSS notice before arrest [Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273]",
         "status": "May be Non-Compliant",
         "explanation": "Offence up to 7 years; the record is silent on any prior notice to appear."},
    ]},
}
print(f"\n{'='*20} draft_layer: representation to the Magistrate {'='*20}")
print(draft_for(_demo_analysis, "magistrate"))
    