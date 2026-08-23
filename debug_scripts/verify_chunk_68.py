
import json

with open("chunks/bharatiya_nyaya_sanhita_2023_chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

section_68 = next((c for c in chunks if c["section_number"] == "68"), None)

if section_68 is None:
    print("Section 68 chunk not found!")
else:
    print(f"act_name: {section_68['act_name']}")
    print(f"citation: {section_68['citation']}")
    print(f"section_number: {section_68['section_number']}")
    print(f"text length: {len(section_68['text'])} characters")
    print(f"\n--- full text ---\n{section_68['text']}")
    
    