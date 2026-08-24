
import json

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

print("--- Section 339 full raw text ---")
print(schedule.get("339"))

print("\n--- Section 78(2) full entry (list or dict?) ---")
print(json.dumps(schedule.get("78(2)"), indent=2))

print("\n--- bns_section_data.py's value for 78(2), for comparison ---")
from bns_section_data import BNS_SECTION_DATA
print(BNS_SECTION_DATA.get("78(2)"))

