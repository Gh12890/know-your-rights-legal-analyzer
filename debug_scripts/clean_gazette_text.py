
import json
import re
import os

COMMON_ENGLISH_WORDS = {
    "the", "of", "and", "to", "in", "a", "is", "for", "or", "as", "by", "on",
    "act", "section", "shall", "any", "this", "under", "such", "be", "which",
    "with", "not", "may", "if", "person", "state", "government", "court",
    "chapter", "provided", "means", "who", "has", "been", "part", "an",
    "code", "law", "india", "officer", "police", "case", "provision"
}


def is_probably_english(line, min_word_ratio=0.3, min_words=2):
    """Heuristic: a line is 'probably English' if a reasonable share of its
    words are common English words. Short, mostly-gibberish lines (scrambled
    Hindi-encoding artifacts) fail this check and get dropped."""
    words = re.findall(r"[a-zA-Z]+", line.lower())
    if len(words) < min_words:
        return True
    english_hits = sum(1 for w in words if w in COMMON_ENGLISH_WORDS)
    return (english_hits / len(words)) >= min_word_ratio


def clean_gazette_text(raw_text):
    lines = raw_text.split("\n")
    kept_lines = [line for line in lines if is_probably_english(line)]
    return "\n".join(kept_lines)


def clean_corpus_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        record = json.load(f)

    original_length = len(record["text"])
    record["text"] = clean_gazette_text(record["text"])
    cleaned_length = len(record["text"])

    record["notes"] = record.get("notes", "") + " [Cleaned: scrambled Hindi-encoded lines stripped via heuristic filter.]"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"{filepath}: {original_length} -> {cleaned_length} characters "
          f"({original_length - cleaned_length} characters removed)")


clean_corpus_file(os.path.join("corpus", "bharatiya_nyaya_sanhita_2023.json"))
clean_corpus_file(os.path.join("corpus", "bharatiya_nagarik_suraksha_sanhita_2023.json"))