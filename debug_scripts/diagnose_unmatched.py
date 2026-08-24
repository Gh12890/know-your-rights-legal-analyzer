
import json
from bns_section_data import BNS_SECTION_DATA

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

TARGETS = ["49", "55", "71", "77", "303(2)"]

print("--- What BNS_SECTION_DATA says for these keys ---")
for key in TARGETS:
    if key in BNS_SECTION_DATA:
        print(f"{key}: {BNS_SECTION_DATA[key]}")
    else:
        print(f"{key}: NOT in BNS_SECTION_DATA")

print("\n--- All schedule_data keys that START with these base numbers ---")
for base in ["49", "55", "71", "77", "303"]:
    matching_keys = [k for k in schedule.keys() if k.startswith(base)]
    print(f"\nKeys starting with '{base}': {matching_keys}")
    for k in matching_keys:
        print(f"  {k}: {schedule[k]}")