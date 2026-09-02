
"""
test_statute_concordance.py

Regression suite for the old<->new statute concordance
(statute_concordance.json + statute_concordance.py), built from the two
NCRB "Corresponding Section Table" PDFs.

These anchor the ~30 provisions this project actually reasons about
(arrest, FIR, custody, bail, the common offence sections) plus the
parser's structural guarantees (full coverage, repealed/new markers,
one-to-many handling). No API cost, no PDF parsing at test time -- it
reads the committed JSON.

Run with: python test_statute_concordance.py
"""

import json
import os
import sys

from statute_concordance import to_new, to_old, corresponding, describe

FAILURES = []


def check(condition, description):
    print(f"[{'PASS' if condition else 'FAIL'}] {description}")
    if not condition:
        FAILURES.append(description)


def has(result, act, section):
    return bool(result) and any(e["act"] == act and e["section"] == section for e in result)


def changed(result, act, section):
    return any(e["act"] == act and e["section"] == section and e["change"] for e in result or [])


# ---- CrPC -> BNSS: the procedural provisions the arrest module leans on ----

check(has(to_new("CrPC", "41"), "BNSS", "35"),
      "CrPC 41 (arrest without warrant) -> BNSS 35")
check(has(to_new("CrPC", "41A"), "BNSS", "35(3)"),
      "CrPC 41A (notice of appearance / Arnesh Kumar) -> BNSS 35(3)")
check(has(to_new("CrPC", "50"), "BNSS", "47"),
      "CrPC 50 (grounds of arrest + right to bail) -> BNSS 47")
check(has(to_new("CrPC", "50A"), "BNSS", "48"),
      "CrPC 50A (inform relative/friend / D.K. Basu) -> BNSS 48")
check(has(to_new("CrPC", "57"), "BNSS", "58"),
      "CrPC 57 (24-hour production) -> BNSS 58")
check(has(to_new("CrPC", "102"), "BNSS", "106"),
      "CrPC 102 (police power to seize property / Tapas Neogy) -> BNSS 106")
check(has(to_new("CrPC", "154"), "BNSS", "173"),
      "CrPC 154 (FIR) -> BNSS 173")
check(has(to_new("CrPC", "167"), "BNSS", "187"),
      "CrPC 167 (custody / default bail) -> BNSS 187")
check(has(to_new("CrPC", "173"), "BNSS", "193"),
      "CrPC 173 (police report) -> BNSS 193  [renumbering trap: NOT BNSS 173]")
check(has(to_new("CrPC", "438"), "BNSS", "482"),
      "CrPC 438 (anticipatory bail) -> BNSS 482")
check(has(to_new("CrPC", "439"), "BNSS", "483"),
      "CrPC 439 (special powers of HC/Sessions re bail) -> BNSS 483")

# ---- the reverse direction, and the renumbering trap spelled out ----

check(has(to_old("BNSS", "35"), "CrPC", "41"),
      "BNSS 35 -> CrPC 41 (reverse lookup)")
check(has(to_old("BNSS", "173"), "CrPC", "154"),
      "BNSS 173 is the FIR section -> CrPC 154, NOT CrPC 173")
check(not has(to_old("BNSS", "173"), "CrPC", "173"),
      "BNSS 173 does NOT map back to CrPC 173 (that pairing would be the trap)")
check(has(to_old("BNSS", "187"), "CrPC", "167"),
      "BNSS 187 (custody) -> CrPC 167")

# ---- IPC <-> BNS: common offence sections (incl. the goat-theft anchors) ----

check(has(to_new("IPC", "378"), "BNS", "303"), "IPC 378 (theft) -> BNS 303")
check(has(to_old("BNS", "303"), "IPC", "378"), "BNS 303 (theft) -> IPC 378")
check(has(to_new("IPC", "302"), "BNS", "103"), "IPC 302 (murder punishment) -> BNS 103")
check(has(to_new("IPC", "307"), "BNS", "109"), "IPC 307 (attempt to murder) -> BNS 109")
check(has(to_new("IPC", "420"), "BNS", "318(4)"),
      "IPC 420 (cheating + dishonest inducement) -> BNS 318(4)")
check(has(to_new("IPC", "376"), "BNS", "64"), "IPC 376 (punishment for rape) -> BNS 64")
check(has(to_new("IPC", "406"), "BNS", "316(2)"),
      "IPC 406 (criminal breach of trust) -> BNS 316(2)")
check(has(to_new("IPC", "323"), "BNS", "115(2)"),
      "IPC 323 (voluntarily causing hurt) -> BNS 115(2)")
check(has(to_new("IPC", "153A"), "BNS", "196"),
      "IPC 153A (promoting enmity) -> BNS 196")

check(changed(to_new("IPC", "302"), "BNS", "103"),
      "IPC 302 -> BNS 103 is flagged as substantively changed")

# ---- one-to-many: a bare section unions its whole subsection cluster ----

r = to_old("BNS", "318")
check(has(r, "IPC", "415") and has(r, "IPC", "420"),
      "BNS 318 (bare) unions the whole cheating cluster: IPC 415 AND 420")
check(to_old("BNS", "318(4)") == [{"act": "IPC", "section": "420", "change": False}],
      "BNS 318(4) (specific) resolves to exactly IPC 420")

# ---- repealed / newly-added: key present, counterpart empty (not None) ----

for repealed in ("124A", "377", "497"):
    check(to_new("IPC", repealed) == [],
          f"IPC {repealed} is in the table but has no BNS successor (repealed) -> []")
check(to_new("IPC", "99999") is None,
      "a section not in the table at all -> None (distinct from repealed's [])")

check(to_old("BNSS", "111") == [] or to_old("BNSS", "111") is None
      or all(e["act"] == "CrPC" for e in to_old("BNSS", "111")),
      "BNSS 111 (organised crime, new) resolves without error")

# ---- input normalisation ----

check(to_new("ipc", "s. 420") == to_new("IPC", "420"),
      "act alias 'ipc' and 'S. 420' prefix are normalised")
check(to_new("Code of Criminal Procedure", "41") == to_new("CrPC", "41"),
      "long-form act name 'Code of Criminal Procedure' is normalised")
check(corresponding("IPC", "378") == to_new("IPC", "378")
      and corresponding("BNS", "303") == to_old("BNS", "303"),
      "corresponding() dispatches by act direction")

# ---- wrong-direction guard ----

try:
    to_new("BNS", "303")
    check(False, "to_new() on a new-code act should raise")
except ValueError:
    check(True, "to_new() on a new-code act raises ValueError")

# ---- structural guarantees on the committed JSON ----

_raw = json.load(open(os.path.join(os.path.dirname(__file__), "statute_concordance.json"),
                     encoding="utf-8"))
import re

bns_nums = sorted({int(re.match(r"\d+", p["new"]).group())
                   for p in _raw["pairs"] if p["new_act"] == "BNS" and p["new"]})
bnss_nums = sorted({int(re.match(r"\d+", p["new"]).group())
                    for p in _raw["pairs"] if p["new_act"] == "BNSS" and p["new"]})
check(bns_nums == list(range(1, 359)),
      f"every BNS section 1-358 appears in the concordance (got {len(bns_nums)})")
check(bnss_nums == list(range(1, 532)),
      f"every BNSS section 1-531 appears in the concordance (got {len(bnss_nums)})")
check(all(1 <= int(re.match(r"\d+", p["old"]).group()) <= 511
          for p in _raw["pairs"] if p["old_act"] == "IPC" and p["old"]),
      "no IPC 'section' above 511 leaked in (year / fragment guard)")
check(sum(1 for p in _raw["pairs"] if p["kind"] == "repealed") >= 20,
      "at least 20 repealed old-act provisions detected")
check(sum(1 for p in _raw["pairs"] if p["kind"] == "new_provision") >= 30,
      "at least 30 newly-added provisions detected")


# ---- scan_old_refs: free-text scan for old IPC/CrPC section references ----

from statute_concordance import scan_old_refs

check(scan_old_refs("") == [] and scan_old_refs(None) == [],
      "scan_old_refs on empty / None -> [], never crashes")
check(scan_old_refs("this cites Section 35 BNSS and Section 187 BNSS only") == [],
      "no old-act token -> nothing scanned (a bare 'Section 35' is never guessed as CrPC)")

_r = scan_old_refs("Reference: S.187 BNSS / S.167(2) CrPC")
check(_r == [{"old": "CrPC 167(2)", "new": "BNSS 187", "changed": False}],
      "an explicit 'S.167(2) CrPC' resolves to BNSS 187, the mixed-code tag's BNSS half ignored")

_r2 = scan_old_refs("charged under Section 41A of the Code of Criminal Procedure and Section 420 IPC")
check({e["old"] for e in _r2} == {"CrPC 41A", "IPC 420"},
      "both an IPC and a CrPC reference in one string are picked up")

_r3 = scan_old_refs("the FIR invokes Section 124A of the Indian Penal Code")
check(_r3 == [{"old": "IPC 124A", "new": None, "changed": True}],
      "a repealed-without-successor provision comes back with new=None")

check(scan_old_refs("Section 302 IPC")[0]["changed"] is True,
      "the 'changed' flag rides along (IPC 302 -> BNS 103, substantively altered)")

_dupes = scan_old_refs("Section 420 IPC ... later, again Section 420 IPC")
check(len(_dupes) == 1, "a reference repeated in the text is deduped")


print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
