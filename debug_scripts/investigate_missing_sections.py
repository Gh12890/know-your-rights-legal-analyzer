
import json
import re

with open("corpus/bharatiya_nyaya_sanhita_2023.json", "r", encoding="utf-8") as f:
    record = json.load(f)

text = record["text"]
lines = text.split("\n")

MISSING = [68, 78, 170, 186, 192, 196, 305]

for num in MISSING:
    print(f"\n=== Looking for section {num} ===")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(rf'^{num}\.', stripped):
            print(f"  Line {i}: {stripped[:100]!r}")
            break
    else:
        print(f"  No line starting with '{num}.' found at all — may be merged into another line or renumbered/omitted in the Act itself.")
        
