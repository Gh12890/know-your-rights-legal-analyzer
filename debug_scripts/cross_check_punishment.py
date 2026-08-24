
from bns_section_data import BNS_SECTION_DATA

CHECK = ["57", "64", "89", "67", "56"]

for sec in CHECK:
    if sec in BNS_SECTION_DATA:
        print(f"{sec}: {BNS_SECTION_DATA[sec]}")
    else:
        print(f"{sec}: not in bns_section_data.py")
        
