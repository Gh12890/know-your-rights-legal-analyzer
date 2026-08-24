
import json

with open("corpus/bharatiya_nagarik_suraksha_sanhita_2023.json", "r", encoding="utf-8") as f:
    record = json.load(f)

text = record["text"]
print(f"Total BNSS text length: {len(text)} characters\n")

markers = ["FIRST SCHEDULE", "CLASSIFICATION OF OFFENCES", "Cognizable", "Non-Bailable"]
for marker in markers:
    idx = text.find(marker)
    if idx != -1:
        print(f"Found '{marker}' at character position {idx}")
        print(f"  Context: ...{text[max(0,idx-100):idx+200]}...\n")
    else:
        print(f"'{marker}' NOT found anywhere in the extracted text.\n")

print(f"\n--- Last 1500 characters of the document (tail end) ---")
print(text[-1500:])

