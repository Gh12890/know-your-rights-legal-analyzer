
import json

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

print(json.dumps(schedule.get("57"), indent=2))

