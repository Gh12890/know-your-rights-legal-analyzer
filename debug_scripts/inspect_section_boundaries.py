import json
import re

with open("corpus/bharatiya_nyaya_sanhita_2023.json", "r", encoding="utf-8") as f:
    record = json.load(f)

text = record["text"]
lines = text.split("\n")

SECTION_START_PATTERN = re.compile(r'^\d+[A-Z]?\.\s*[A-Z\(]')

matches = []
for i, line in enumerate(lines):
    stripped = line.strip()
    if SECTION_START_PATTERN.match(stripped):
        matches.append((i, stripped[:70]))

print(f"Total lines: {len(lines)}")
print(f"Lines matching widened pattern: {len(matches)}\n")

print("First 15 matches:")
for line_no, preview in matches[:15]:
    print(f"  Line {line_no}: {preview}")

print("\nLast 10 matches:")
for line_no, preview in matches[-10:]:
    print(f"  Line {line_no}: {preview}")

numbers_found = []
for _, preview in matches:
    m = re.match(r'^(\d+)', preview)
    if m:
        numbers_found.append(int(m.group(1)))

expected = set(range(numbers_found[0], numbers_found[-1] + 1))
found = set(numbers_found)
missing = sorted(expected - found)
print(f"\nSection numbers with NO match found in range {numbers_found[0]}-{numbers_found[-1]}: {missing}")

