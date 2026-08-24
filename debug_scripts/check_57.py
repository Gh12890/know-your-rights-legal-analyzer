
import json

with open("bns_final_merged_table.json", "r", encoding="utf-8") as f:
    table = json.load(f)

print(json.dumps(table.get("57"), indent=2))

