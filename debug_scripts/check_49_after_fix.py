
import json

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

print("--- Keys starting with '49' ---")
matches_49 = [k for k in schedule if k.startswith("49")]
print(matches_49)
for k in matches_49:
    print(f"  {k}: {schedule[k]}")

print("\n--- Keys starting with '1' that are short (possible header-fusion victims) ---")
matches_1 = [k for k in schedule if k.startswith("1") and len(k) <= 3]
print(sorted(matches_1))
for k in sorted(matches_1)[:10]:
    print(f"  {k}: {schedule[k]}")

print(f"\nTotal keys in schedule: {len(schedule)}")