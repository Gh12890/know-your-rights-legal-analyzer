
import re

with open("main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

lines = main_content.split("\n")
for i, line in enumerate(lines):
    if re.search(r'\bdata\[["\']?(cognizable|bailable|life_or_death)["\']?\]', line) or \
       re.search(r'\.get\(["\']?(cognizable|bailable|life_or_death)["\']?\)', line):
        print(f"Line {i+1}: {line.strip()}")
        
