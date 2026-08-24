
import json
import re

with open("chunks/bharatiya_nyaya_sanhita_2023_chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

chunk_by_section = {c["section_number"]: c["text"] for c in chunks}
full_text = chunk_by_section["64"]

def get_subsection_text(full_text, sub_num):
    start_pattern = re.compile(rf'\({sub_num}\)\s')
    start_match = start_pattern.search(full_text)
    if not start_match:
        return None, "NO START MATCH"
    start = start_match.start()

    next_sub_pattern = re.compile(rf'\({int(sub_num)+1}\)\s')
    next_match = next_sub_pattern.search(full_text, start_match.end())
    explanation_match = re.search(r'\bExplanation', full_text[start_match.end():])

    end_candidates = [len(full_text)]
    if next_match:
        end_candidates.append(next_match.start())
    if explanation_match:
        end_candidates.append(start_match.end() + explanation_match.start())

    end = min(end_candidates)
    return full_text[start:end], f"start={start}, end={end}, next_match={bool(next_match)}, explanation={bool(explanation_match)}"

result, debug_info = get_subsection_text(full_text, "1")
print(f"Debug info: {debug_info}")
print(f"\nExtracted text for (1):")
print(result)

