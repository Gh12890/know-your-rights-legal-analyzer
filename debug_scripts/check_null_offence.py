
import json

with open("bns_final_merged_table.json", "r", encoding="utf-8") as f:
    new_table = json.load(f)

null_offence_clean = [k for k, v in new_table.items() if v["offence"] is None and not v["needs_review"]]
null_offence_all = [k for k, v in new_table.items() if v["offence"] is None]

print(f"Entries with offence=None among the 'clean' (needs_review=False) set: {len(null_offence_clean)}")
print(f"Entries with offence=None across ALL 436: {len(null_offence_all)}")
print(f"\nFirst 15 clean-but-null-offence keys: {null_offence_clean[:15]}")

