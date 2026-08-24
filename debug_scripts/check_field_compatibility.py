
import json

with open("bns_final_merged_table.json", "r", encoding="utf-8") as f:
    new_table = json.load(f)

clean_entry_key = next(k for k, v in new_table.items() if not v["needs_review"])
print(f"Sample CLEAN entry [{clean_entry_key}]:")
print(json.dumps(new_table[clean_entry_key], indent=2))

required_fields = ["offence", "max_years", "life_or_death", "cognizable", "bailable"]
missing = [f for f in required_fields if f not in new_table[clean_entry_key]]
print(f"\nRequired fields missing from new entries: {missing}")

