
import json
import re
from bns_section_data import BNS_SECTION_DATA

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    schedule = json.load(f)

def base_number(key):
    m = re.match(r'^(\d+)', str(key))
    return m.group(1) if m else str(key)

def get_general_entry(sched_value):
    if isinstance(sched_value, list):
        return next((e for e in sched_value if e.get("condition") == "general"), sched_value[0])
    return sched_value

def has_conditions(sched_value):
    return isinstance(sched_value, list) and len(sched_value) > 1

schedule_by_base = {}
for sched_key, sched_val in schedule.items():
    base = base_number(sched_key)
    schedule_by_base.setdefault(base, []).append((sched_key, sched_val))

matches = []
mismatches = []
unmatched = []
ambiguous = []
has_uncaptured_conditions = []

for sec, data in BNS_SECTION_DATA.items():
    base = base_number(sec)
    candidates = schedule_by_base.get(base)

    if not candidates:
        unmatched.append(sec)
        continue

    exact = next((c for c in candidates if c[0] == sec), None)
    if exact:
        chosen_raw = exact[1]
    else:
        general_entries = [get_general_entry(c[1]) for c in candidates]
        cognizable_vals = set(e["cognizable"] for e in general_entries)
        bailable_vals = set(e["bailable"] for e in general_entries)
        if len(cognizable_vals) == 1 and len(bailable_vals) == 1:
            chosen_raw = candidates[0][1]
        else:
            ambiguous.append({"our_key": sec, "schedule_candidates": [c[0] for c in candidates]})
            continue

    chosen = get_general_entry(chosen_raw)
    if has_conditions(chosen_raw):
        has_uncaptured_conditions.append(sec)

    our_cognizable = data.get("cognizable")
    our_bailable = data.get("bailable")
    sched_cognizable = chosen["cognizable"]
    sched_bailable = chosen["bailable"]

    if sched_cognizable == "contingent":
        continue

    if our_cognizable == sched_cognizable and our_bailable == sched_bailable:
        matches.append(sec)
    else:
        mismatches.append({
            "section": sec,
            "our_cognizable": our_cognizable, "schedule_cognizable": sched_cognizable,
            "our_bailable": our_bailable, "schedule_bailable": sched_bailable,
        })

print(f"Total entries in BNS_SECTION_DATA: {len(BNS_SECTION_DATA)}")
print(f"  Matches:              {len(matches)}")
print(f"  MISMATCHES:           {len(mismatches)}")
print(f"  Unmatched:            {len(unmatched)}")
print(f"  Ambiguous:            {len(ambiguous)}")
print(f"  Have Schedule conditions our hand-typed data doesn't capture: {len(has_uncaptured_conditions)}")

if mismatches:
    print(f"\n{'='*20} MISMATCHES {'='*20}")
    for m in mismatches:
        print(f"\n{m['section']}: ours cog={m['our_cognizable']} bail={m['our_bailable']} | Schedule cog={m['schedule_cognizable']} bail={m['schedule_bailable']}")

if has_uncaptured_conditions:
    print(f"\n{'='*20} SECTIONS WITH UNCAPTURED CONDITIONS {'='*20}")
    print(has_uncaptured_conditions)

if unmatched:
    print(f"\n{'='*20} UNMATCHED {'='*20}")
    print(unmatched)
    
    