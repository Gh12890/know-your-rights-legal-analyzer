
import json
import os

_TABLE_PATH = os.path.join(os.path.dirname(__file__), "bns_final_merged_table.json")

with open(_TABLE_PATH, "r", encoding="utf-8") as _f:
    _raw_table = json.load(_f)

BNS_SECTION_DATA = _raw_table



if __name__ == "__main__":
    print(f"Loaded {len(BNS_SECTION_DATA)} sections from {_TABLE_PATH}")
    clean = sum(1 for v in BNS_SECTION_DATA.values() if not v.get("needs_review"))
    print(f"  {clean} fully clean, {len(BNS_SECTION_DATA) - clean} flagged needs_review")
    