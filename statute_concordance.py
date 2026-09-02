
"""
statute_concordance.py

Deterministic old<->new statute lookup, built from the two NCRB
"Corresponding Section Table" PDFs by build_statute_concordance.py.

  IPC 1860  <-> BNS 2023
  CrPC 1973 <-> BNSS 2023

WHAT THIS IS: a navigational aid. Given a section number in one code it
tells you the corresponding section(s) in the other, plus whether the
provision was substantively changed in the recodification.

WHAT THIS IS NOT: a legal verdict. The source tables are marked "For
Reference only". Mappings are frequently one-to-many in BOTH directions
(BNS 318 <- IPC 415/417/418/420; IPC 308-cluster -> BNS 308(1)..(7)),
and `change=True` means "renumbered AND substantively altered -- do not
assume the element you care about survived unchanged". Callers must
treat a result as a pointer to verify, never as an identity.

Consistent with the project's one architectural principle: this is pure
Python lookup over a checked table. No LLM, no inference.

    from statute_concordance import to_new, to_old, describe

    to_new("IPC", "420")    -> [{"act": "BNS", "section": "318(4)", "change": False}]
    to_new("IPC", "302")    -> [{"act": "BNS", "section": "103", "change": True}]
    to_old("BNSS", "35")    -> [{"act": "CrPC", "section": "41", "change": False}]
    to_new("IPC", "124A")   -> []      # in the table, but repealed with no successor
    to_new("IPC", "99999")  -> None    # not in the table at all
    describe("CrPC", "41A") -> "CrPC Section 41A corresponds to BNSS Section 35(3) ..."
"""

import json
import os
import re

_PATH = os.path.join(os.path.dirname(__file__), "statute_concordance.json")

with open(_PATH, encoding="utf-8") as _fh:
    _RAW = json.load(_fh)

_NEW_TO_OLD = _RAW["new_to_old"]   # "BNS 303" -> [{"act","section","change"}, ...]
_OLD_TO_NEW = _RAW["old_to_new"]

# --- act-name normalisation ------------------------------------------------
_ACT_ALIASES = {
    "ipc": "IPC", "penalcode": "IPC", "indianpenalcode": "IPC",
    "bns": "BNS", "bharatiyanyayasanhita": "BNS", "nyayasanhita": "BNS",
    "crpc": "CrPC", "cr.p.c": "CrPC", "codeofcriminalprocedure": "CrPC",
    "criminalprocedurecode": "CrPC", "cpc_criminal": "CrPC",
    "bnss": "BNSS", "bharatiyanagariksurakshasanhita": "BNSS",
    "nagariksurakshasanhita": "BNSS",
}
_OLD_ACTS = {"IPC", "CrPC"}
_NEW_ACTS = {"BNS", "BNSS"}


def _norm_act(act):
    key = re.sub(r"[^a-z.]", "", (act or "").lower())
    if key in _ACT_ALIASES:
        return _ACT_ALIASES[key]
    up = (act or "").strip().upper()
    return {"IPC": "IPC", "BNS": "BNS", "CRPC": "CrPC", "BNSS": "BNSS"}.get(up)


def _norm_section(section):
    """'S. 420' / 'section 420' / '420 ' -> '420'; '318 (4)' -> '318(4)'."""
    s = str(section).strip()
    s = re.sub(r"(?i)^\s*(section|sec\.?|s\.?)\s*", "", s)
    s = re.sub(r"(\d)\s+\(", r"\1(", s)
    return s.strip()


def _bare(section):
    m = re.match(r"\d+[A-Z]{0,2}", section)
    return m.group(0) if m else section


def _lookup(index, act, section):
    """Return the list of corresponding provisions, or None if the
    section is not in the table at all. An empty list means the section
    IS in the table but has no counterpart (repealed / newly added)."""
    act = _norm_act(act)
    if not act:
        return None
    section = _norm_section(section)

    hits, seen, found_any = [], set(), False

    def _take(entries):
        nonlocal found_any
        found_any = True
        for e in entries:
            sig = (e["act"], e["section"])
            if sig not in seen:
                seen.add(sig)
                hits.append(dict(e))

    exact = f"{act} {section}"
    if exact in index:
        _take(index[exact])

    if "(" in section:
        # '318(4)': also fall back to the bare-section row if the
        # subsection itself wasn't a distinct row
        bkey = f"{act} {_bare(section)}"
        if not hits and bkey in index:
            _take(index[bkey])
    else:
        # bare '318': also union every '318(x)' subsection row, so the
        # caller sees the whole cluster of predecessors/successors
        pref = f"{act} {section}("
        for k, entries in index.items():
            if k.startswith(pref):
                _take(entries)

    return hits if found_any else None


def to_new(act, section):
    """Old-code section -> list of new-code provisions (or None/[])."""
    if _norm_act(act) in _NEW_ACTS:
        raise ValueError(f"{act!r} is already a new code; use to_old()")
    return _lookup(_OLD_TO_NEW, act, section)


def to_old(act, section):
    """New-code section -> list of old-code provisions (or None/[])."""
    if _norm_act(act) in _OLD_ACTS:
        raise ValueError(f"{act!r} is already an old code; use to_new()")
    return _lookup(_NEW_TO_OLD, act, section)


def corresponding(act, section):
    """Direction-agnostic: dispatches to to_new / to_old by act."""
    a = _norm_act(act)
    if a in _OLD_ACTS:
        return to_new(act, section)
    if a in _NEW_ACTS:
        return to_old(act, section)
    return None


def describe(act, section):
    """One-line human-readable summary, safe to show a layperson."""
    a = _norm_act(act)
    res = corresponding(act, section)
    sec = _norm_section(section)
    if res is None:
        return f"{a or act} Section {sec} is not in the concordance table."
    if not res:
        other = "BNS/BNSS" if a in _OLD_ACTS else "IPC/CrPC"
        return (f"{a} Section {sec} has no direct counterpart in the "
                f"{other} recodification (repealed or newly introduced).")
    parts = []
    for e in res:
        tag = " (substantially changed — verify the specific point)" if e["change"] else ""
        parts.append(f"{e['act']} Section {e['section']}{tag}")
    lead = "corresponds to" if len(parts) == 1 else "corresponds to any of"
    return f"{a} Section {sec} {lead} " + "; ".join(parts) + "."


if __name__ == "__main__":
    for a, s in [("IPC", "420"), ("IPC", "302"), ("IPC", "378"), ("IPC", "124A"),
                 ("CrPC", "41"), ("CrPC", "41A"), ("CrPC", "167"), ("CrPC", "173"),
                 ("BNS", "318"), ("BNS", "303"), ("BNSS", "35"), ("BNSS", "187"),
                 ("IPC", "99999")]:
        print(f"{a:5} {s:7} -> {describe(a, s)}")
