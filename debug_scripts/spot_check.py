
import json

with open("corpus/bharatiya_nyaya_sanhita_2023.json", "r", encoding="utf-8") as f:
    record = json.load(f)

text = record["text"]
midpoint = len(text) // 2

print(f"Total length: {len(text)} characters\n")
print("--- Sample from the middle of the document ---")
print(text[midpoint:midpoint + 1500])