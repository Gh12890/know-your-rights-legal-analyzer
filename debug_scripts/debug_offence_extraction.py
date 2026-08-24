
import json
import re
from build_full_bns_table import chunk_by_section, base_number, get_subsection_text, get_offence_description

key = "113(2)(a)"
base = base_number(key)
full_text = chunk_by_section.get(base, "")

sub_match = re.match(rf'^{base}\((\d+)\)', key)
print(f"sub_match for '{key}': {sub_match}")
if sub_match:
    sub_num = sub_match.group(1)
    target_text = get_subsection_text(full_text, sub_num)
    print(f"\nExtracted subsection text (first 300 chars):")
    print(target_text[:300] if target_text else "None")
    print(f"\nget_offence_description result: {get_offence_description(target_text) if target_text else 'N/A - target_text was None'}")