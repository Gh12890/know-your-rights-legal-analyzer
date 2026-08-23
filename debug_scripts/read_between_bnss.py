
import json
import re

with open("corpus/bharatiya_nagarik_suraksha_sanhita_2023.json", "r", encoding="utf-8") as f:
    record = json.load(f)

text = record["text"]

def show_window(low, high):
    print(f"\n{'='*20} Between section {low} and {high} {'='*20}")
    low_match = re.search(rf'\b{low}\.\s*[A-Z\(]', text)
    high_match = re.search(rf'\b{high}\.\s*[A-Z\(]', text)
    if low_match and high_match:
        snippet = text[low_match.start():high_match.start()]
        print(snippet)
    else:
        print(f"Could not locate anchor ({low} found={bool(low_match)}, {high} found={bool(high_match)})")

show_window(203, 205)

