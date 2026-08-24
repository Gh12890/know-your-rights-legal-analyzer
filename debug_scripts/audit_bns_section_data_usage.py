
import re

with open("main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

usages = re.findall(r'.*BNS_SECTION_DATA.*', main_content)
print(f"Total lines referencing BNS_SECTION_DATA: {len(usages)}\n")
for line in usages:
    print(line.strip())
    
