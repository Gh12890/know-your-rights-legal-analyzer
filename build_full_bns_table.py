
import json
import re
from extract_punishment_years import parse_punishment

with open("chunks/bharatiya_nyaya_sanhita_2023_chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

chunk_by_section = {c["section_number"]: c["text"] for c in chunks}

def base_number(key):
    m = re.match(r'^(\d+)', str(key))
    return m.group(1) if m else str(key)

def get_subsection_text(full_text, sub_num):
    start_pattern = re.compile(rf'\({sub_num}\)\s')
    start_match = start_pattern.search(full_text)
    if not start_match:
        return None
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
    return full_text[start:end]


def get_offence_description(text):
    m = re.match(r'^\d+[\(\)a-zA-Z0-9]*\.?\s*(\(\d+\)\s*)?(.+?)[,\.]', text)
    return m.group(2).strip() if m else None


full_table = {}
missing_chunk = []
no_punishment_found = []

for sched_key in schedule.keys():
    base = base_number(sched_key)
    if base not in chunk_by_section:
        missing_chunk.append(sched_key)
        continue

    full_text = chunk_by_section[base]

    sub_match = re.match(rf'^{base}\((\d+)\)', sched_key)
    if sub_match:
        sub_num = sub_match.group(1)
        target_text = get_subsection_text(full_text, sub_num)
        if target_text is None:
            target_text = full_text
    else:
        target_text = full_text

    punishment = parse_punishment(target_text)
    if punishment is None:
        no_punishment_found.append(sched_key)
        punishment = {"shape": "needs_manual_review", "max_years": None, "life_or_death": None,
                      "note": "Automated parser could not confidently determine punishment shape from this text — verify manually before use."}

    full_table[sched_key] = {
        "offence": get_offence_description(target_text),
        "max_years": punishment.get("max_years"),
        "life_or_death": punishment.get("life_or_death"),
        "punishment_shape": punishment.get("shape"),
        "punishment_note": punishment.get("note"),
    }

with open("bns_full_punishment_table.json", "w", encoding="utf-8") as f:
    json.dump(full_table, f, indent=2, ensure_ascii=False)

print(f"Built table with {len(full_table)} entries.")
print(f"Sections with no matching chunk found: {len(missing_chunk)} -> {missing_chunk[:20]}")
print(f"Sections where NO punishment sentence was found at all: {len(no_punishment_found)} -> {no_punishment_found[:20]}")

shapes = {}
for v in full_table.values():
    s = v["punishment_shape"]
    shapes[s] = shapes.get(s, 0) + 1
print(f"\nBreakdown by punishment shape found: {shapes}")

