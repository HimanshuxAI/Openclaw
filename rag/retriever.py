from collections import Counter
import re

from rag.indexer import get_index


DEFAULT_TOP_K = 5
EXACT_PATH_BONUS = 100
TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
STOP_WORDS = {
    "and",
    "assert",
    "error",
    "failed",
    "failure",
    "from",
    "line",
    "pytest",
    "test",
    "the",
    "traceback",
    "with",
}


def _tokens(text):
    return [
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOP_WORDS
    ]


def retrieve_context(failure_text, k=DEFAULT_TOP_K):
    if k <= 0:
        return []
    terms = set(_tokens(failure_text))
    if not terms:
        return []

    ranked = []
    normalized_failure = failure_text.lower()
    for chunk in get_index():
        content_counts = Counter(_tokens(chunk["content"]))
        path_counts = Counter(_tokens(chunk["file"]))
        score = sum(content_counts[term] + 3 * path_counts[term] for term in terms)
        if chunk["file"].lower() in normalized_failure:
            score += EXACT_PATH_BONUS
        if score > 0:
            ranked.append((score, chunk))

    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1]["file"],
            item[1]["lines"][0],
            item[1]["lines"][1],
        )
    )
    return [chunk.copy() for _, chunk in ranked[:k]]
