
import re
from build_full_bns_table import chunk_by_section, base_number, get_subsection_text

TARGETS = ["351(3)", "195(1)", "308(5)"]

for key in TARGETS:
    base = base_number(key)
    full_text = chunk_by_section.get(base, "")
    sub_match = re.match(rf'^{base}\((\d+)\)', key)
    target_text = get_subsection_text(full_text, sub_match.group(1)) if sub_match else full_text
    print(f"\n[{key}]")
    print((target_text or "")[:200])
    
