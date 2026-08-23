
import json
import re

with open("corpus/bharatiya_nyaya_sanhita_2023.json", "r", encoding="utf-8") as f:
    record = json.load(f)

text = record["text"]

start = re.search(r'\b68\.\s*[A-Z\(]', text)
end = re.search(r'\b69\.\s*[A-Z\(]', text)

if start and end:
    print(text[start.start():end.start()])
else:
    print("Could not locate section 68 or 69 anchors.")