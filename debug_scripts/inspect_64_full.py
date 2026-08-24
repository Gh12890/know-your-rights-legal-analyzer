
import json

with open("chunks/bharatiya_nyaya_sanhita_2023_chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

for chunk in chunks:
    if chunk["section_number"] == "64":
        print(chunk["text"])
        break
else:
    print("Section 64 chunk not found at all — checking what keys DO exist near it:")
    nearby = [c["section_number"] for c in chunks if c["section_number"].startswith("6") and len(c["section_number"]) <= 3]
    print(sorted(nearby))
    