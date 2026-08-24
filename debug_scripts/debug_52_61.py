
import json
import re
from build_full_bns_table import chunk_by_section, base_number, get_subsection_text

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

for key in ["52", "53", "61(2)(a)"]:
    base = base_number(key)
    full_text = chunk_by_section.get(base, "")
    sub_match = re.match(rf'^{base}\((\d+)\)', key)
    if sub_match:
        target = get_subsection_text(full_text, sub_match.group(1)) or full_text
    else:
        target = full_text
    clean = re.sub(r'\s+', ' ', target)
    print(f"\n[{key}]")
    print(clean[:400])
    