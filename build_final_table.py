
import json
import re

with open("bns_full_punishment_table.json", "r", encoding="utf-8") as f:
    punishment_table = json.load(f)

with open("bnss_first_schedule.json", "r", encoding="utf-8") as f:
    classification_table = json.load(f)

def get_classification_general(sched_value):
    if isinstance(sched_value, list):
        return next((e for e in sched_value if e.get("condition") == "general"), sched_value[0])
    return sched_value

final_table = {}
conflicts = []

all_keys = set(punishment_table.keys()) | set(classification_table.keys())

for key in all_keys:
    punishment = punishment_table.get(key)
    classification_raw = classification_table.get(key)

    if punishment is None or classification_raw is None:
        conflicts.append({"key": key, "issue": "missing from one of the two source tables",
                          "has_punishment": punishment is not None,
                          "has_classification": classification_raw is not None})
        continue

    classification = get_classification_general(classification_raw)
    has_multiple_conditions = isinstance(classification_raw, list) and len(classification_raw) > 1

    entry = {
        "offence": punishment.get("offence"),
        "max_years": punishment.get("max_years"),
        "life_or_death": punishment.get("life_or_death"),
        "punishment_shape": punishment.get("punishment_shape"),
        "cognizable": classification.get("cognizable"),
        "bailable": classification.get("bailable"),
        "has_multiple_conditions": has_multiple_conditions,
        "needs_review": (
            punishment.get("punishment_shape") == "needs_manual_review"
            or classification.get("cognizable") == "contingent"
            or punishment.get("max_years") == "contingent"
            or has_multiple_conditions
        ),
    }

    if has_multiple_conditions:
        entry["all_conditions"] = classification_raw

    final_table[key] = entry

with open("bns_final_merged_table.json", "w", encoding="utf-8") as f:
    json.dump(final_table, f, indent=2, ensure_ascii=False)

print(f"Merged table: {len(final_table)} entries")
print(f"Entries missing from one source table: {len(conflicts)}")
print(conflicts[:10])

needs_review_count = sum(1 for v in final_table.values() if v["needs_review"])
print(f"\nEntries flagged needs_review (contingent, multi-condition, or unresolved punishment): {needs_review_count}")

clean_count = len(final_table) - needs_review_count
print(f"Entries fully clean and ready for direct use: {clean_count}")


