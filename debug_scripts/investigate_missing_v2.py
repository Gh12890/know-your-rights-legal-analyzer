
import json
import re

with open("corpus/bharatiya_nyaya_sanhita_2023.json", "r", encoding="utf-8") as f:
    record = json.load(f)

text = record["text"]

STILL_MISSING = [68, 78, 170, 186, 196, 305]

for num in STILL_MISSING:
    print(f"\n=== Section {num} — searching anywhere in text, not just line-start ===")
    pattern = re.compile(rf'\b{num}\.\s*[A-Z\(]')
    match = pattern.search(text)
    if match:
        start = max(0, match.start() - 80)
        end = min(len(text), match.start() + 100)
        context = text[start:end].replace("\n", " | ")
        print(f"  Found mid-text: ...{context}...")
    else:
        print(f"  Not found anywhere in the text at all, in this exact shape.")