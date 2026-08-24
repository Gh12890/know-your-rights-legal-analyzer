
import json
import re
from build_full_bns_table import chunk_by_section, base_number, get_subsection_text
from extract_punishment_years import parse_punishment

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

for n in range(49, 63):
    matching_keys = [k for k in schedule.keys() if base_number(k) == str(n)]
    for key in matching_keys:
        base = base_number(key)
        full_text = chunk_by_section.get(base, "")
        sub_match = re.match(rf'^{base}\((\d+)\)', key)
        target = get_subsection_text(full_text, sub_match.group(1)) if sub_match else full_text
        target = target or full_text
        result = parse_punishment(target)
        shape = result["shape"] if result else "not_found"
        print(f"[{key}] -> {shape}")
        
