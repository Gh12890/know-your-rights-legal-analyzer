
import json
import re

with open("chunks/bharatiya_nyaya_sanhita_2023_chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

def base_number(key):
    m = re.match(r'^(\d+)', str(key))
    return m.group(1) if m else str(key)

real_offence_bases = set(base_number(k) for k in schedule.keys())

pattern = re.compile(r'shall be punished[^.]*\.', re.IGNORECASE)

count = 0
for chunk in chunks:
    if chunk["section_number"] not in real_offence_bases:
        continue
    matches = pattern.findall(chunk["text"])
    for m in matches[:1]:
        print(f"[{chunk['section_number']}] {m.strip()[:200]}")
        count += 1
    if count >= 25:
        break
    
