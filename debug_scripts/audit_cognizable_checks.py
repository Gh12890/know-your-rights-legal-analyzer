
import re

with open("main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

lines = main_content.split("\n")
for i, line in enumerate(lines):
    if re.search(r'\bcognizable\b', line, re.IGNORECASE) and 'BNS_SECTION_DATA' not in line:
        print(f"Line {i+1}: {line.strip()}")
        
        