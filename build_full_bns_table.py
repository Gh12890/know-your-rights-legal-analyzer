
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

def get_lettered_clause_text(full_text, letter, sub_num=None):
    """Isolate a lettered clause like (a)/(b)/(c). If sub_num is given, search
    only within that numbered subsection's span first (handles nested keys
    like 111(2)(a)); otherwise search the whole section text (handles bare
    keys like 125(a))."""
    search_text = full_text
    base_offset = 0
    if sub_num is not None:
        sub_text = get_subsection_text(full_text, sub_num)
        if sub_text is not None:
            search_text = sub_text

    start_pattern = re.compile(rf'\({letter}\)\s')
    start_match = start_pattern.search(search_text)
    if not start_match:
        return None
    start = start_match.start()

    next_letter = chr(ord(letter) + 1)
    next_pattern = re.compile(rf'\({next_letter}\)\s')
    next_match = next_pattern.search(search_text, start_match.end())
    explanation_match = re.search(r'\bExplanation', search_text[start_match.end():])

    end_candidates = [len(search_text)]
    if next_match:
        end_candidates.append(next_match.start())
    if explanation_match:
        end_candidates.append(start_match.end() + explanation_match.start())

    end = min(end_candidates)
    return search_text[start:end]

def get_offence_description(text):
    """Offence description, ending at whichever comes first: a comma, period,
    em-dash, or the phrase "shall be punish" (the consistent boundary between
    offence description and punishment clause in BNS's drafting style)."""
    text = re.sub(r'\s+', ' ', text)
    m = re.match(r'^(\d+[\(\)a-zA-Z0-9]*\.?\s*)?(\(\d+\)\s*)?(\([a-zA-Z]\)\s*)?(.+?)(?:,|\.|\u2014|\s+shall be punish)', text, re.IGNORECASE)
    return m.group(4).strip() if m else None




full_table = {}
missing_chunk = []
no_punishment_found = []

for sched_key in schedule.keys():
    base = base_number(sched_key)
    if base not in chunk_by_section:
        missing_chunk.append(sched_key)
        continue

    full_text = chunk_by_section[base]

    # Three possible key shapes, checked most-specific first:
    #   base(NUM)(LETTER)  e.g. 111(2)(a)  -- nested letter clause inside a numbered subsection
    #   base(LETTER)       e.g. 125(a)     -- bare letter clause off the base section
    #   base(NUM)          e.g. 111(7)     -- plain numbered subsection
    nested_match = re.match(rf'^{base}\((\d+)\)\(([a-zA-Z])\)', sched_key)
    bare_letter_match = re.match(rf'^{base}\(([a-zA-Z])\)', sched_key)
    sub_match = re.match(rf'^{base}\((\d+)\)$', sched_key)

    if nested_match:
        sub_num, letter = nested_match.group(1), nested_match.group(2)
        target_text = get_lettered_clause_text(full_text, letter, sub_num=sub_num)
        if target_text is None:
            target_text = get_subsection_text(full_text, sub_num) or full_text
    elif bare_letter_match:
        letter = bare_letter_match.group(1)
        target_text = get_lettered_clause_text(full_text, letter)
        if target_text is None:
            target_text = full_text
    elif sub_match:
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
        "max_months": punishment.get("max_months"),
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

