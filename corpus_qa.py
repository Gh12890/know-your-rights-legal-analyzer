
"""
Reusable corpus quality-assurance module.

Run this against ANY numbered-section legal document (BNS, BNSS, a future
Act, an amendment) after extraction, before trusting it for chunking or
retrieval.
"""

import re
from collections import Counter

DEFAULT_SECTION_PATTERN = re.compile(r'^\d+[A-Z]?\.\s*[A-Z\(]')


def verify_section_coverage(text, pattern=DEFAULT_SECTION_PATTERN):
    lines = text.split("\n")
    matches = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if pattern.match(stripped):
            matches.append((i, stripped[:70]))

    numbers_found = []
    for _, preview in matches:
        m = re.match(r'^(\d+)', preview)
        if m:
            numbers_found.append(int(m.group(1)))

    if not numbers_found:
        return {
            "passed": False,
            "total_matches": 0,
            "missing": [],
            "duplicates": {},
            "summary": "No section numbers matched at all — pattern may not fit this document's format, or extraction failed entirely."
        }

    expected_range = set(range(numbers_found[0], numbers_found[-1] + 1))
    found_set = set(numbers_found)
    missing = sorted(expected_range - found_set)

    counts = Counter(numbers_found)
    duplicates = {n: c for n, c in counts.items() if c > 1}

    passed = (len(missing) == 0) and (len(duplicates) == 0)

    summary = (
        f"Range {numbers_found[0]}-{numbers_found[-1]}: {len(numbers_found)} sections matched. "
        f"Missing: {missing if missing else 'none'}. "
        f"Duplicates: {duplicates if duplicates else 'none'}. "
        f"{'PASS' if passed else 'FAIL — investigate before using this document for chunking.'}"
    )

    return {
        "passed": passed,
        "total_matches": len(numbers_found),
        "range": (numbers_found[0], numbers_found[-1]),
        "missing": missing,
        "duplicates": duplicates,
        "summary": summary,
    }


if __name__ == "__main__":
    import json
    import sys
    import glob

    files = glob.glob("corpus/*.json")
    if not files:
        print("No files found in corpus/.")
        sys.exit(0)

    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            record = json.load(f)
        report = verify_section_coverage(record["text"])
        print(f"\n{filepath}")
        print(f"  {report['summary']}")
        
