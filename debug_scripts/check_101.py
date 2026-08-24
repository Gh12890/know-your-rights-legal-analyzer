
import json

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

for key in ["100", "101", "102", "128", "129", "130"]:
    if key in schedule:
        print(f"{key}: PRESENT — {schedule[key]}")
    else:
        print(f"{key}: NOT PRESENT")
        


