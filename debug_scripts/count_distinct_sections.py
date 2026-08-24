
import json
import re

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

def base_number(key):
    m = re.match(r'^(\d+)', str(key))
    return m.group(1) if m else str(key)

all_keys = list(schedule.keys())
base_numbers = set(base_number(k) for k in all_keys)

print(f"Total raw rows extracted: {len(all_keys)}")
print(f"Distinct BASE section numbers covered: {len(base_numbers)}")

bns_total = set(str(n) for n in range(1, 359))
covered = base_numbers & bns_total
not_covered = sorted(bns_total - base_numbers, key=int)

print(f"\nOf BNS's 358 total sections, the Schedule covers: {len(covered)}")
print(f"BNS sections with NO Schedule entry at all (likely non-offence/structural sections): {len(not_covered)}")
print(f"\nThose section numbers: {not_covered}")


