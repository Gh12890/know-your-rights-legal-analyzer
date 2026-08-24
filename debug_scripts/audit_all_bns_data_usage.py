
import re
with open("main.py", "r", encoding="utf-8") as f:
    lines = f.read().split("\n")
for i, line in enumerate(lines):
    if "BNS_SECTION_DATA" in line:
        print(f"Line {i+1}: {line.strip()}")
        
        