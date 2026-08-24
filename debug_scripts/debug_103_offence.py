
import re
from build_full_bns_table import chunk_by_section, base_number, get_subsection_text, get_offence_description

key = "103(1)"
base = base_number(key)
full_text = chunk_by_section.get(base, "")

sub_match = re.match(rf'^{base}\((\d+)\)', key)
sub_num = sub_match.group(1)
target_text = get_subsection_text(full_text, sub_num)
print(f"Extracted text:\n{target_text}\n")
print(f"get_offence_description result: {get_offence_description(target_text)}")
