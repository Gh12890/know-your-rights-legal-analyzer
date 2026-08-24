
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
    