
import json
import re

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

def base_number(key):
    m = re.match(r'^(\d+)', str(key))
    return m.group(1) if m else str(key)

base_numbers = set(base_number(k) for k in schedule.keys())
bns_total = set(str(n) for n in range(1, 359))

covered = base_numbers & bns_total
not_covered = sorted(bns_total - base_numbers, key=int)

print(f"Distinct base section numbers now covered: {len(covered)}")
print(f"Still not covered: {len(not_covered)}")
print(not_covered)

