import os

# threshold at which a word/part appears as a suggestion
SUGGEST_THRESHOLD = 2  # >= 2 uses

def parts_from_text(raw_text: str):
    """
    Returns a list of unique, trimmed parts split on commas/newlines,
    preserving the first-seen order.
    """
    if not raw_text:
        return []
    t = raw_text.replace("\r", "").replace("\n", ",")
    parts = [p.strip() for p in t.split(",")]
    seen = set()
    unique = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            unique.append(p)
    return unique

class SuggestionStore:
    """
    Keeps frequency counts for parts; persists semicolon-separated file:
    <part>;<count> per line. Renders suggestions alphabetically.
    """
    def __init__(self, path: str):
        self.path = path
        self.counts = {}  # part -> int
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or ";" not in line:
                        continue
                    tag, cnt = line.split(";", 1)
                    try:
                        c = int(cnt)
                        self.counts[tag] = max(self.counts.get(tag, 0), c)
                    except ValueError:
                        pass
        except FileNotFoundError:
            self.counts = {}
        except Exception:
            pass
        self.save_alpha()  # keep alpha on disk

    def save_alpha(self):
        try:
            items = sorted(self.counts.items(), key=lambda t: t[0].lower())
            with open(self.path, "w", encoding="utf-8") as f:
                for tag, cnt in items:
                    f.write(f"{tag};{cnt}\n")
        except Exception:
            pass

    def process_text_for_counts(self, raw_text: str):
        for p in parts_from_text(raw_text):
            self.counts[p] = self.counts.get(p, 0) + 1
        self.save_alpha()

    def clear(self):
        self.counts.clear()
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def suggestions_alpha(self):
        """Return [(part, count)] for parts with count >= threshold, alphabetically sorted."""
        items = [(p, c) for p, c in self.counts.items() if c >= SUGGEST_THRESHOLD]
        items.sort(key=lambda t: t[0].lower())
        return items
