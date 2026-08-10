"""Test combined similarity logic: ratio + first/last letter + sequence order."""
from difflib import SequenceMatcher

def classify(target, attempt):
    t, a = target.lower(), attempt.lower()
    if not a or not t:
        return "unrelated", 0.0

    ratio = round(SequenceMatcher(None, t, a).ratio(), 2)

    first_match = t[0] == a[0]
    last_match = t[-1] == a[-1]

    shared = set(t) & set(a)
    shared_count = len(shared)

    t_shared = [c for c in t if c in shared]
    a_shared = [c for c in a if c in shared]
    order_match = t_shared == a_shared

    lcp = 0
    for i in range(min(len(t), len(a))):
        if t[i] == a[i]: lcp += 1
        else: break

    lcs = 0
    for i in range(1, min(len(t), len(a)) + 1):
        if t[-i] == a[-i]: lcs += 1
        else: break

    # --- Classification logic ---
    if ratio >= 0.5:
        return "misspelling", ratio

    if shared_count == 0:
        return "unrelated", ratio

    # Short words (2-3 letters): need >= 1 shared letter AND (first or last match) AND order preserved
    if len(t) <= 3:
        if shared_count >= 1 and (first_match or last_match) and order_match:
            return "misspelling", ratio
        else:
            return "unrelated", ratio

    # Longer words (4+ letters): need >= 2 shared letters AND some positional overlap
    if len(t) >= 4:
        if shared_count >= 2 and (first_match or last_match or lcp >= 1 or lcs >= 1):
            return "misspelling", ratio
        elif ratio >= 0.4:
            return "misspelling", ratio
        else:
            return "unrelated", ratio

    return "unrelated", ratio


print(f"{'target':12s} {'attempt':12s} {'ratio':>6s} {'result':12s}  notes")
print("-" * 80)

cases = [
    # Real misspellings
    ("which", "wich"), ("which", "whch"), ("which", "whic"),
    ("cat", "ct"), ("cat", "bat"), ("cat", "car"),
    ("standstill", "standstil"), ("phone", "fone"), ("phone", "phon"),
    ("me", "m"), ("he", "she"),
    ("bombastic", "bombastc"),
    # Completely different
    ("which", "book"), ("which", "xyz"), ("which", "dog"),
    ("cat", "xyz"), ("cat", "dog"), ("cat", "run"),
    ("standstill", "cat"), ("phone", "dog"),
    ("to", "xyz"), ("to", "in"), ("me", "dog"), ("me", "xyz"),
    ("bombastic", "cat"), ("bombastic", "xyz"),
    # Borderline short words
    ("to", "do"), ("to", "no"), ("to", "go"), ("to", "so"), ("to", "ot"),
    ("me", "be"), ("me", "we"), ("he", "be"),
    # Borderline longer words
    ("which", "while"), ("which", "where"), ("which", "white"),
    ("which", "when"), ("which", "what"),
    ("cat", "can"), ("cat", "cap"), ("cat", "rat"),
]

for target, attempt in cases:
    result, ratio = classify(target, attempt)
    t, a = target.lower(), attempt.lower()
    first = "1st=Y" if t[0]==a[0] else "1st=N"
    last = "last=Y" if t[-1]==a[-1] else "last=N"
    shared = len(set(t) & set(a))
    notes = f"{first} {last} shared={shared} ratio={ratio}"
    print(f"{target:12s} {attempt:12s} {ratio:6.2f} {result:12s}  {notes}")
