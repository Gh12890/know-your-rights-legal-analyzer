
"""
build_statute_concordance.py

Parse the two NCRB "Corresponding Section Table" PDFs into a single
deterministic old<->new statute concordance.

SOURCES (both "For Reference only", NCRB Sankalan portal):
  - old_to_new_sections.pdf : BNS 2023  <-> IPC 1860   (23 pp, whole file is the table)
  - old to new bnss.pdf     : BNSS 2023 <-> CrPC 1973   (table is pp. 20-45 of a 400 pp file)

Both lay out as two columns: NEW act on the left, OLD act on the right.
We split each page's words at x = COLUMN_SPLIT, group into rows by y, and
pair the left (new) cell with the right (old) cell. Markers:
  - "Deleted" in the NEW cell      -> the OLD provision has no successor
  - "New Section" / "New Sub-..."  -> the NEW provision has no predecessor
  - "(Change)" anywhere in a cell  -> renumbered AND substantively altered

Output: statute_concordance.json  (consumed by statute_concordance.py)

This file DECIDES NOTHING legal. It is a navigational lookup. Many rows
are one-to-many in both directions, and "(Change)" means "verify the
element you rely on" -- callers must treat a mapping as a pointer, not
an identity. Run:  python build_statute_concordance.py
"""

import json
import re
import sys

import fitz  # pymupdf

ROW_Y_TOLERANCE = 6.0       # words within this many points of y are the same visual line

# (path, new_act, old_act, first_page, last_page, column_split)
#   pages are 1-indexed inclusive; column_split is the x-coordinate that
#   separates the left (new act) column from the right (old act) column
#   -- the two PDFs are typeset slightly differently.
SOURCES = [
    ("old_to_new_sections.pdf", "BNS", "IPC", 1, 23, 289.0),
    ("old_to_new_bnss.pdf", "BNSS", "CrPC", 20, 45, 289.0),
]

# Highest real section number per act -- anything above this is a year
# ("2023", "1974") or a mis-parsed fragment leaking from a title line.
MAX_SECTION = {"BNS": 358, "IPC": 511, "BNSS": 531, "CrPC": 484}

_SECTION_HEAD = re.compile(r"^(\d+[A-Z]{0,2})\.\s")                       # "41A. Notice of..."
_LEADING_NUM = re.compile(r"(\d+[A-Z]{0,2}(?:\([0-9a-z]+\))?)")           # one section/subsection token
_ALLCAPS = re.compile(r"^[A-Z0-9 .,'–—\-()/]+$")
_NEW_MARKER = re.compile(r"\bnew\s+(section|sub[- ]?section|clause)\b", re.I)
_DELETED = re.compile(r"^\s*deleted\s*$", re.I)


def _rows_from_page(page, column_split):
    """Yield (left_text, right_text) per visual row, top to bottom."""
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, wordno)
    if not words:
        return
    words.sort(key=lambda w: (w[1], w[0]))
    rows = []
    for x0, y0, x1, y1, word, *_ in words:
        placed = False
        for r in rows:
            if abs(r["y"] - y0) <= ROW_Y_TOLERANCE:
                (r["left"] if x0 < column_split else r["right"]).append((x0, word))
                r["y"] = (r["y"] + y0) / 2
                placed = True
                break
        if not placed:
            r = {"y": y0, "left": [], "right": []}
            (r["left"] if x0 < column_split else r["right"]).append((x0, word))
            rows.append(r)
    rows.sort(key=lambda r: r["y"])
    for r in rows:
        left = " ".join(w for _, w in sorted(r["left"]))
        right = " ".join(w for _, w in sorted(r["right"]))
        yield left.strip(), right.strip()


def _looks_like_heading(text):
    t = text.strip().rstrip(".")
    if not t:
        return True
    if t.upper().startswith(("CHAPTER", "PART ", "P A G E", "PAGE ")):
        return True
    if _ALLCAPS.match(t) and not re.search(r"\d", t.split()[0]) and len(t) > 3:
        return True
    if t.lower() in ("homepage", "index"):
        return True
    if t.startswith(("A.", "B.", "C.", "D.", "E.")) and t.upper() == t:
        return True
    return False


def _numbers_in(cell):
    """The section/subsection number(s) a cell BEGINS with, as a list.
    Handles all the NCRB-table shapes:
      '26. Courts by which...'              -> ['26']
      '41A Notice of appearance...'         -> ['41A']   (dot often dropped)
      '35(3), 35(4) 35(5), 35(6)'           -> ['35(3)','35(4)','35(5)','35(6)']
      '318 (4)'                             -> ['318(4)']
      'Assistant Public prosecutors.'       -> []
    Stops at the first token that is not a number / subsection / separator."""
    cell = re.sub(r"(\d)\s+(\()", r"\1\2", cell.strip())   # '318 (4)' -> '318(4)'
    toks = []
    for tok in cell.split():
        m = _LEADING_NUM.match(tok)
        if not m:
            break
        toks.append(m.group(1))
        # a token like '35(6).' or '41A' may carry trailing punctuation/text;
        # if there's a non-separator remainder, this is the last number token
        rest = tok[m.end():].strip(" ,;.")
        if rest:
            break
    return toks


class _Acc:
    """Accumulates the running section context for one column so a bare
    subsection row ('35(3)') inherits the last real section head."""

    def __init__(self):
        self.cur_title = None

    def feed(self, cell):
        nums = _numbers_in(cell)
        m = _SECTION_HEAD.match(cell.strip())
        if m:
            self.cur_title = cell.strip()
        return nums


def build():
    concordance = {
        "_meta": {
            "note": "Navigational lookup only, NOT a legal verdict. Sources are "
                    "NCRB 'For Reference only' tables. Mappings are often one-to-many "
                    "in both directions; '(Change)' means the provision was renumbered "
                    "AND substantively altered -- verify the specific element relied on.",
            "sources": [s[0] for s in SOURCES],
        },
        "pairs": [],   # list of {new_act,new,old_act,old,change,kind}
    }

    for path, new_act, old_act, p0, p1, column_split in SOURCES:
        try:
            doc = fitz.open(path)
        except Exception as e:
            sys.exit(f"cannot open {path!r}: {e}")

        left_acc, right_acc = _Acc(), _Acc()
        pending_change = False
        held_new = held_old = None
        n_pairs_before = len(concordance["pairs"])

        for pno in range(p0 - 1, min(p1, doc.page_count)):
            for left, right in _rows_from_page(doc[pno], column_split):
                if not left and not right:
                    continue
                blob = f"{left} || {right}"
                if "(change)" in blob.lower():
                    pending_change = True

                # NEW provision with no OLD predecessor
                if _NEW_MARKER.search(right) and left:
                    nums = left_acc.feed(left)
                    for n in _sane(nums or _numbers_in(left) or _trailing_nums(left_acc), new_act):
                        concordance["pairs"].append({
                            "new_act": new_act, "new": n, "old_act": old_act,
                            "old": None, "change": True, "kind": "new_provision",
                        })
                    pending_change = False
                    continue

                # OLD provision with no NEW successor
                if _DELETED.match(left) and right:
                    right_acc.feed(right)
                    for o in _sane(_numbers_in(right), old_act):
                        concordance["pairs"].append({
                            "new_act": new_act, "new": None, "old_act": old_act,
                            "old": o, "change": True, "kind": "repealed",
                        })
                    pending_change = False
                    continue

                if _looks_like_heading(left) and _looks_like_heading(right):
                    continue

                new_nums = _sane(left_acc.feed(left), new_act)
                old_nums = _sane(right_acc.feed(right), old_act)

                # The two columns sometimes land the paired section numbers
                # on slightly different y-rows (BNSS 39 / CrPC 42). Hold a
                # lone number from one side until the other side's next
                # number row arrives, then pair them.
                if new_nums and not old_nums:
                    held_new = (new_nums, pending_change or "(change)" in blob.lower())
                    if held_old:
                        _emit(concordance, new_act, old_act, held_new[0], held_old[0],
                              held_new[1] or held_old[1])
                        held_new = held_old = None
                    pending_change = False
                    continue
                if old_nums and not new_nums:
                    held_old = (old_nums, pending_change or "(change)" in blob.lower())
                    if held_new:
                        _emit(concordance, new_act, old_act, held_new[0], held_old[0],
                              held_new[1] or held_old[1])
                        held_new = held_old = None
                    pending_change = False
                    continue
                if not new_nums or not old_nums:
                    continue  # a wrapped continuation line - nothing to pair

                held_new = held_old = None
                _emit(concordance, new_act, old_act, new_nums, old_nums,
                      pending_change or "(change)" in blob.lower())
                pending_change = False

        print(f"{path}: {len(concordance['pairs']) - n_pairs_before} pairs "
              f"(pages {p0}-{p1})")

    _write_indexes(concordance)
    with open("statute_concordance.json", "w", encoding="utf-8") as fh:
        json.dump(concordance, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote statute_concordance.json  "
          f"({len(concordance['pairs'])} pairs, "
          f"{len(concordance['new_to_old'])} new keys, "
          f"{len(concordance['old_to_new'])} old keys)")


def _emit(conc, new_act, old_act, new_nums, old_nums, change):
    for n in new_nums:
        for o in old_nums:
            conc["pairs"].append({
                "new_act": new_act, "new": n, "old_act": old_act,
                "old": o, "change": change, "kind": "mapped",
            })


def _sane(nums, act):
    """Drop tokens whose integer part exceeds the act's real section count
    (years, page numbers, fragments leaking from a title line)."""
    cap = MAX_SECTION.get(act, 10**6)
    out = []
    for n in nums:
        base = int(re.match(r"\d+", n).group())
        if 1 <= base <= cap:
            out.append(n)
    return out


def _trailing_nums(acc):
    if acc.cur_title:
        m = _SECTION_HEAD.match(acc.cur_title)
        if m:
            return [m.group(1)]
    return []


def _write_indexes(conc):
    """Two flat dicts for statute_concordance.py to load directly."""
    new_to_old, old_to_new = {}, {}
    for p in conc["pairs"]:
        if p["new"] and p["old"]:
            new_to_old.setdefault(f"{p['new_act']} {p['new']}", []).append(
                {"act": p["old_act"], "section": p["old"], "change": p["change"]})
            old_to_new.setdefault(f"{p['old_act']} {p['old']}", []).append(
                {"act": p["new_act"], "section": p["new"], "change": p["change"]})
        elif p["new"] and p["kind"] == "new_provision":
            new_to_old.setdefault(f"{p['new_act']} {p['new']}", [])  # key exists, empty
        elif p["old"] and p["kind"] == "repealed":
            old_to_new.setdefault(f"{p['old_act']} {p['old']}", [])
    # dedupe
    for idx in (new_to_old, old_to_new):
        for k, v in idx.items():
            seen, uniq = set(), []
            for e in v:
                sig = (e["act"], e["section"])
                if sig not in seen:
                    seen.add(sig)
                    uniq.append(e)
            idx[k] = uniq
    conc["new_to_old"] = new_to_old
    conc["old_to_new"] = old_to_new


if __name__ == "__main__":
    build()
