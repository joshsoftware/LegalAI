"""Name and employer string similarity.

Base similarity comes from RapidFuzz's token_set_ratio (handles word
reordering and extra/missing tokens). On top of that, an initials-expansion
pass resolves abbreviations like "Ankita A.S" vs "Ankita Advitot Sunil",
which plain character-level fuzzy matching can't do on its own.
"""

from rapidfuzz import fuzz

MIN_OVERLAP_TOKEN = 1


def _tokenize(name: str) -> list[str]:
    return [tok.strip(".").lower() for tok in name.replace(".", ". ").split() if tok.strip(".")]


def _is_initial(token: str) -> bool:
    return len(token) == 1


def _initials_genuine_match(tokens_a: list[str], tokens_b: list[str]) -> bool:
    """True if the side with more single-letter tokens is a genuine
    initials-abbreviation of the other side's full-word tokens.

    Every initial on the shorter side must either (a) match the first
    letter of a distinct, unused full word on the other side, or (b) have
    no full word left to compare against at all (the other name simply
    doesn't spell out that token, e.g. a middle/last name omitted
    entirely). What's never tolerated is an initial whose letter
    contradicts one of the available full words when a candidate exists
    to compare against — that's what keeps a genuinely wrong initial
    (e.g. "P" when the real name starts with "A") from being boosted.
    """
    full_a = [t for t in tokens_a if not _is_initial(t)]
    full_b = [t for t in tokens_b if not _is_initial(t)]
    initials_a = [t for t in tokens_a if _is_initial(t)]
    initials_b = [t for t in tokens_b if _is_initial(t)]

    # Pick the side that actually has initials to expand.
    if initials_b and not initials_a:
        initials, full = initials_b, full_a
    elif initials_a and not initials_b:
        initials, full = initials_a, full_b
    else:
        return False

    if not initials or not full:
        return False

    # There must be at least one shared full token (anchor) between the
    # two names, otherwise this is likely a different person entirely.
    shared_full_words = set(full_a) & set(full_b)
    if not shared_full_words:
        return False

    # Words already spelled out identically on both sides (e.g. a shared
    # first name) don't need to be re-derived from an initial — only the
    # remaining full words are available to satisfy the initials.
    remaining_full = list(full)
    for word in shared_full_words:
        if word in remaining_full:
            remaining_full.remove(word)

    available_first_letters = [w[0] for w in remaining_full]
    matched_any = False
    for letter in initials:
        if letter in available_first_letters:
            available_first_letters.remove(letter)
            matched_any = True
        elif available_first_letters:
            # A candidate full word exists but its first letter doesn't
            # match this initial — a genuine contradiction, not boosted.
            return False
        # else: no remaining full word to check this initial against —
        # tolerated as an omitted token, not a contradiction.

    return matched_any


def _base_token_set_ratio(a: str, b: str) -> float:
    return float(fuzz.token_set_ratio(a.lower(), b.lower()))


def name_similarity(name_a: str, name_b: str) -> float:
    if not name_a or not name_b:
        return 0.0

    base = _base_token_set_ratio(name_a, name_b)

    tokens_a = _tokenize(name_a)
    tokens_b = _tokenize(name_b)

    if _initials_genuine_match(tokens_a, tokens_b):
        return 100.0

    return base


def employer_similarity(employer_a: str, employer_b: str) -> float:
    if not employer_a or not employer_b:
        return 0.0
    return _base_token_set_ratio(employer_a, employer_b)
