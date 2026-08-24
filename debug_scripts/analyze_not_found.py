
import json
import re
from build_full_bns_table import chunk_by_section, base_number, get_subsection_text

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

from extract_punishment_years import parse_punishment

not_found_texts = []
for sched_key in schedule.keys():
    base = base_number(sched_key)
    if base not in chunk_by_section:
        continue
    full_text = chunk_by_section[base]
    sub_match = re.match(rf'^{base}\((\d+)\)', sched_key)
    if sub_match:
        target_text = get_subsection_text(full_text, sub_match.group(1)) or full_text
    else:
        target_text = full_text

    if parse_punishment(target_text) is None:
        not_found_texts.append((sched_key, target_text))

print(f"Total not_found: {len(not_found_texts)}\n")
print("--- First 15 full texts, for pattern-spotting ---")
for key, text in not_found_texts[:15]:
    clean = re.sub(r'\s+', ' ', text)
    print(f"\n[{key}] {clean[:250]}")