
import json

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

print("--- Keys near the 49-56 gap ---")
for key in ["47", "48", "49", "56", "57"]:
    if key in schedule:
        print(f"\n{key}: {schedule[key]}")
    else:
        print(f"\n{key}: NOT PRESENT")

print("\n\n--- Keys near the 100-102 gap ---")
for key in ["99", "100", "102", "103"]:
    if key in schedule:
        print(f"\n{key}: {schedule[key]}")
    else:
        print(f"\n{key}: NOT PRESENT")


