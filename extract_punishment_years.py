
import json
import re

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
}

def word_to_number(word):
    return NUMBER_WORDS.get(word.lower())

NUM_PATTERN = r'(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|\d+)'

PATTERNS = [
        (re.compile(
        r'one-half of the longest term|one-fourth part of the longest term|one-half of the imprisonment|'
        r'punished with the punishment provided for the offence|'
        r'liable for the act done, in the same manner|'
        r'shall be deemed to have committed such act',
        re.IGNORECASE),
     "fraction_of_underlying_offence"),
        

    (re.compile(r'on first conviction.*second or subsequent conviction', re.IGNORECASE | re.DOTALL),
     "tiered_by_conviction"),

    # Death/life-alternative patterns must be checked before the generic
    # ceiling/not-exceeding patterns below — otherwise a sentence like
    # "death or imprisonment for life, or imprisonment for a term not
    # exceeding ten years" gets matched only on its trailing fragment and
    # silently downgraded to a plain 10-year ceiling, dropping the death/life
    # alternative entirely. Real bug found and fixed: Section 107.
    (re.compile(rf'punished with death,?\s*or\s*(?:with\s*)?imprisonment for life,?\s*or\s*imprisonment for a term not exceeding {NUM_PATTERN} years', re.IGNORECASE),
     "death_or_life_or_term"),

    (re.compile(r'punished with death,?\s*or\s*(with\s*)?imprisonment for life', re.IGNORECASE),
     "death_or_life_only"),

    (re.compile(rf'not be less than {NUM_PATTERN} years?,?\s*but which may extend to imprisonment for life', re.IGNORECASE),
     "range_to_life"),

    (re.compile(rf'imprisonment for life,? or with imprisonment.*?may extend to {NUM_PATTERN} years?', re.IGNORECASE | re.DOTALL),
     "life_or_term"),

    (re.compile(rf'not be less than {NUM_PATTERN} years?,?\s*but which may extend to (?:imprisonment for )?{NUM_PATTERN} years?', re.IGNORECASE),
     "range"),

    (re.compile(rf'may extend to {NUM_PATTERN} years?', re.IGNORECASE),
     "ceiling_only"),

    (re.compile(rf'not exceeding {NUM_PATTERN} years?', re.IGNORECASE),
     "ceiling_only"),

    (re.compile(rf'may extend to {NUM_PATTERN} months?', re.IGNORECASE),
     "ceiling_only_months"),

    (re.compile(r'may extend to imprisonment for life', re.IGNORECASE),
     "ceiling_to_life"),
]


def parse_punishment(text):
    """Returns a dict describing the punishment shape found, or None if no
    recognizable punishment clause exists in this text at all."""
    text = re.sub(r'\s+', ' ', text)

    for pattern, shape in PATTERNS:
        ...  # (rest of the function unchanged)
    for pattern, shape in PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        
        
        if shape == "death_or_life_only":
            return {"shape": "death_or_life_only", "max_years": None, "life_or_death": True,
                    "note": "Death or life imprisonment, no separate fixed-term ceiling stated."}

        if shape == "death_or_life_or_term":
            # Death or life imprisonment is an available sentence alongside a
            # fixed-term alternative — max_years is kept None (not the term
            # figure) because the applicable maximum consequence is still
            # death/life, and reporting the term alone would understate that.
            term_str = m.group(1)
            term_years = word_to_number(term_str) if not term_str.isdigit() else int(term_str)
            return {"shape": "death_or_life_or_term", "max_years": None, "life_or_death": True,
                    "note": f"Death or life imprisonment, with a fixed-term alternative up to {term_years} years also available in the text."}

        if shape == "fraction_of_underlying_offence":
            return {"shape": "contingent", "max_years": "contingent", "life_or_death": "contingent",
                    "note": "Punishment is a fraction of the underlying offence's term — not a fixed value."}
        if shape == "tiered_by_conviction":
            return {"shape": "tiered_by_conviction", "max_years": "see_subsections", "life_or_death": "see_subsections",
                    "note": "Punishment differs by conviction count — needs sub-entry parsing, not a single value."}
        if shape == "range_to_life":
            return {"shape": "range_to_life", "max_years": None, "life_or_death": True,
                    "min_years": word_to_number(m.group(1)) if not m.group(1).isdigit() else int(m.group(1))}
        if shape == "life_or_term":
            # Convention match with existing hand-typed data (confirmed via
            # Section 89): when life_or_death is True, max_years is set to
            # None, even when an alternative fixed term is also mentioned.
            years_str = m.group(1)
            alt_years = word_to_number(years_str) if not years_str.isdigit() else int(years_str)
            return {"shape": "life_or_term", "max_years": None,
                    "life_or_death": True,
                    "note": f"Alternative fixed term of {alt_years} years also available in the text."}
        if shape == "range":
            min_str, max_str = m.group(1), m.group(2)
            return {"shape": "range",
                    "min_years": word_to_number(min_str) if not min_str.isdigit() else int(min_str),
                    "max_years": word_to_number(max_str) if not max_str.isdigit() else int(max_str),
                    "life_or_death": False}
        if shape == "ceiling_only":
            years_str = m.group(1)
            return {"shape": "ceiling_only",
                    "max_years": word_to_number(years_str) if not years_str.isdigit() else int(years_str),
                    "life_or_death": False}
        if shape == "ceiling_only_months":
            # Months-only punishment ceiling (e.g. "may extend to three months").
            # Stored as a SEPARATE max_months field, never silently converted
            # into a fractional max_years value — downstream code must treat
            # months-only sections as their own known case, not guess a year
            # figure from it.
            months_str = m.group(1)
            months_val = word_to_number(months_str) if not months_str.isdigit() else int(months_str)
            return {"shape": "ceiling_only_months",
                    "max_years": None,
                    "max_months": months_val,
                    "life_or_death": False}
        if shape == "ceiling_to_life":
            return {"shape": "ceiling_to_life", "max_years": None, "life_or_death": True,
                    "note": "Ceiling of life imprisonment, no stated minimum term."}

    return None


if __name__ == "__main__":
    test_cases = {
        "57": "shall be punished with imprisonment of either description for a term which may extend to seven years and with fine.",
        "64": "shall be punished with rigorous imprisonment of either description for a term which shall not be less than ten years, but which may extend to imprisonment for life, and shall also be liable to fine.",
        "89": "shall be punished with imprisonment for life, or with imprisonment of either description for a term which may extend to ten years, and shall also be liable to fine.",
        "67": "shall be punished with imprisonment of either description for a term which shall not be less than two years but which may extend to seven years, and shall also be liable to fine.",
        "56": "shall be punished with imprisonment of any description provided for that offence, for a term which may extend to one-half of the longest term provided for that offence.",
    }
    for sec, text in test_cases.items():
        print(f"[{sec}] {parse_punishment(text)}")
        
