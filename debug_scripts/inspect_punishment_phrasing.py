
import json

with open("chunks/bharatiya_nyaya_sanhita_2023_chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

TARGET_SECTIONS = ["64(1)", "68", "99", "176", "303(2)"]

for chunk in chunks:
    if chunk["section_number"] in TARGET_SECTIONS:
        print(f"\n=== Section {chunk['section_number']} ===")
        print(chunk["text"][:400])
        
