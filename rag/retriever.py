from collections import Counter
import re

from rag.indexer import get_index
from rag.router import analyze_failure


DEFAULT_TOP_K = 5
TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
PATCH_FILE_PATTERN = re.compile(r"^diff --git a/(.+?) b/\1$", re.MULTILINE)
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


def _path_matches(reported, indexed):
    reported = reported.replace("\\", "/")
    return reported == indexed or reported.endswith(f"/{indexed}")


def _simple_scope(chunk):
    return chunk["scope"].rsplit(".", 1)[-1]


def _containing(index, path, line):
    return [
        chunk
        for chunk in index
        if _path_matches(path, chunk["file"])
        and chunk["lines"][0] <= line <= chunk["lines"][1]
    ]


def _keyword_score(chunk, terms):
    content_counts = Counter(_tokens(chunk["content"]))
    path_counts = Counter(_tokens(chunk["file"]))
    scope_counts = Counter(_tokens(chunk["scope"]))
    return sum(
        content_counts[term] + 3 * path_counts[term] + 4 * scope_counts[term]
        for term in terms
    )


def _history_bonus(chunk, error_type, memory):
    if not error_type:
        return 0
    bonus = 0
    for record in memory or ():
        if not record.get("success") or record.get("error_type") != error_type:
            continue
        match = PATCH_FILE_PATTERN.search(record.get("patch", ""))
        if match and match.group(1) == chunk["file"]:
            bonus += 80
    return bonus


def _public_chunk(chunk):
    return {
        "file": chunk["file"],
        "content": chunk["content"],
        "lines": tuple(chunk["lines"]),
        "scope": chunk["scope"],
        "kind": chunk["kind"],
    }


def retrieve_context(failure_text, k=DEFAULT_TOP_K, memory=None):
    if k <= 0:
        return []

    index = get_index()
    evidence = analyze_failure(failure_text)
    terms = set(_tokens(failure_text))
    scores = {}

    def add(chunk, score):
        key = (chunk["file"], chunk["lines"], chunk["scope"])
        scores[key] = (max(score, scores.get(key, (0, chunk))[0]), chunk)

    selected = []
    locations = evidence["locations"]
    node = evidence["node"]

    if evidence["kind"] == "syntax":
        for order, (path, line) in enumerate(reversed(locations)):
            for chunk in _containing(index, path, line):
                add(chunk, 1200 - order * 10)
                selected.append(chunk)
        for chunk in index:
            if any(_path_matches(path, chunk["file"]) for path, _ in locations):
                if chunk["kind"] == "module":
                    add(chunk, 700)

    elif evidence["kind"] == "assertion":
        test_scopes = []
        if node:
            node_path, node_scope = node
            for chunk in index:
                if (
                    chunk["is_test"]
                    and _path_matches(node_path, chunk["file"])
                    and _simple_scope(chunk) == node_scope
                ):
                    add(chunk, 1200)
                    test_scopes.append(chunk)
        if not test_scopes:
            for path, line in locations:
                for chunk in _containing(index, path, line):
                    if chunk["is_test"]:
                        add(chunk, 1150)
                        test_scopes.append(chunk)
        called = {name for chunk in test_scopes for name in chunk["calls"]}
        for chunk in index:
            if not chunk["is_test"] and _simple_scope(chunk) in called:
                add(chunk, 900)

    elif evidence["kind"] == "import":
        for order, (path, line) in enumerate(reversed(locations)):
            for chunk in _containing(index, path, line):
                add(chunk, 1200 - order * 10)
                selected.append(chunk)
            for chunk in index:
                if _path_matches(path, chunk["file"]) and chunk["kind"] == "module":
                    add(chunk, 1100 - order * 10)
        identifiers = set(evidence["identifiers"])
        for chunk in index:
            if _simple_scope(chunk) in identifiers:
                add(chunk, 900)

    elif evidence["kind"] in {"type", "runtime"}:
        for order, (path, line) in enumerate(reversed(locations)):
            for chunk in _containing(index, path, line):
                add(chunk, 1200 - order * 10)
                selected.append(chunk)
        called = {name for chunk in selected for name in chunk["calls"]}
        for chunk in index:
            if _simple_scope(chunk) in called:
                add(chunk, 850)
            if evidence["kind"] == "type" and chunk["kind"] == "module":
                if any(_path_matches(path, chunk["file"]) for path, _ in locations):
                    add(chunk, 700)

    if not scores:
        for chunk in index:
            keyword_score = _keyword_score(chunk, terms)
            if keyword_score > 0:
                add(chunk, keyword_score)

    ranked = []
    for base_score, chunk in scores.values():
        score = base_score + _keyword_score(chunk, terms)
        score += _history_bonus(chunk, evidence["error_type"], memory)
        ranked.append((score, chunk))

    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1]["file"],
            item[1]["lines"][0],
            item[1]["lines"][1],
        )
    )
    limit = min(k, 2) if evidence["kind"] == "unknown" else k
    return [_public_chunk(chunk) for _, chunk in ranked[:limit]]
