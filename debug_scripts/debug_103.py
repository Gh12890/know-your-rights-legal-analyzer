
import json
import re

with open("chunks/bharatiya_nyaya_sanhita_2023_chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

chunk_by_section = {c["section_number"]: c["text"] for c in chunks}

if "103" in chunk_by_section:
    print("Found base chunk '103':")
    print(chunk_by_section["103"][:600])
else:
    print("'103' NOT found as a base chunk. Nearby keys:")
    nearby = [k for k in chunk_by_section if k.startswith("10")]
    print(sorted(nearby))
    