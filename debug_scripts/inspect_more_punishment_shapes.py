
import json
import re

with open("chunks/bharatiya_nyaya_sanhita_2023_chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

pattern = re.compile(r'[^.]*\b(imprisonment|fine|death)\b[^.]*\.', re.IGNORECASE)

count = 0
for chunk in chunks[10:40]:
    sentences = pattern.finditer(chunk["text"])
    for m in list(sentences)[:1]:
        print(f"[{chunk['section_number']}] {m.group(0).strip()[:200]}")
        count += 1
    if count > 20:
        break
    