from collections import defaultdict
from pathlib import Path, PurePosixPath
import re

from rag.router import analyze_failure


ASSERT_PATTERN = re.compile(r"(?:^|\n)\s*[E>]?\s*(assert\b[^\n]*)", re.IGNORECASE)
COMPARE_PATTERN = re.compile(r"assert\s+(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+)")
NUMBER_OR_STRING_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\""
)
SIGNALS = ("minimality", "relevance", "history", "intent")
DEFAULT_WEIGHTS = {
    "minimality": 0.18,
    "relevance": 0.16,
    "history": 0.12,
    "intent": 0.20,
}
CLUSTER_ALIASES = {
    "type": "type_error",
    "syntax": "type_error",
    "runtime": "logic",
    "unknown": "logic",
}


def cluster_failure(failure_text):
    kind = analyze_failure(failure_text)["kind"]
    if kind in {"assertion", "import"}:
        return kind
    return CLUSTER_ALIASES.get(kind, kind)


def _clean_value(value):
    return value.strip().strip("'\"")


def extract_test_intent(failure_text):
    analysis = analyze_failure(failure_text)
    assertions = []
    expected = []
    actual = []
    vector = []

    for match in ASSERT_PATTERN.finditer(failure_text):
        assertion = match.group(1).strip()
        if assertion not in assertions:
            assertions.append(assertion)
        comparison = COMPARE_PATTERN.search(assertion)
        if comparison:
            left, _, right = comparison.groups()
            actual.extend(
                _clean_value(value)
                for value in NUMBER_OR_STRING_PATTERN.findall(left)
            )
            expected.extend(
                _clean_value(value)
                for value in NUMBER_OR_STRING_PATTERN.findall(right)
            )

    for line in failure_text.splitlines():
        comparison = COMPARE_PATTERN.search(line)
        if comparison:
            left, _, right = comparison.groups()
            actual.extend(
                _clean_value(value)
                for value in NUMBER_OR_STRING_PATTERN.findall(left)
            )
            expected.extend(
                _clean_value(value)
                for value in NUMBER_OR_STRING_PATTERN.findall(right)
            )

    identifiers = [
        identifier
        for identifier in analysis["identifiers"]
        if identifier.lower() not in {"assertionerror", "expected"}
    ]
    for token in identifiers + expected:
        normalized = token.strip().strip("'\"")
        if normalized and normalized not in vector:
            vector.append(normalized)
    node = analysis["node"]
    return {
        "cluster": cluster_failure(failure_text),
        "node": "::".join(node) if node else "",
        "assertions": assertions[:3],
        "expected": list(dict.fromkeys(expected))[:5],
        "actual": list(dict.fromkeys(actual))[:5],
        "identifiers": identifiers[:8],
        "vector": vector[:12],
    }


def intent_signal(patch, failure_text):
    intent = extract_test_intent(failure_text)
    patch_text = patch.lower()
    vector = [token.lower() for token in intent["vector"] if token]
    if not vector:
        return 0.0
    hits = sum(1 for token in vector if token in patch_text)
    return round(min(1.0, hits / len(vector)), 6)


def learned_signal_weights(memory, cluster):
    weights = DEFAULT_WEIGHTS.copy()
    evidence = defaultdict(
        lambda: {
            "hit_success": 0,
            "hit_total": 0,
            "miss_success": 0,
            "miss_total": 0,
        }
    )
    for record in memory or []:
        if record.get("cluster") != cluster or "score_signals" not in record:
            continue
        success = bool(record.get("success"))
        for signal in SIGNALS:
            value = float(record.get("score_signals", {}).get(signal, 0.0) or 0.0)
            if value >= 0.5:
                evidence[signal]["hit_total"] += 1
                evidence[signal]["hit_success"] += int(success)
            else:
                evidence[signal]["miss_total"] += 1
                evidence[signal]["miss_success"] += int(success)

    for signal, counts in evidence.items():
        if counts["hit_total"] == 0:
            continue
        hit_rate = counts["hit_success"] / counts["hit_total"]
        miss_rate = (
            counts["miss_success"] / counts["miss_total"]
            if counts["miss_total"]
            else 0.5
        )
        weights[signal] = max(
            0.04,
            min(0.32, weights[signal] + (hit_rate - miss_rate) * 0.16),
        )
    return {signal: round(weights[signal], 6) for signal in SIGNALS}


def combine_score(signals, weights):
    confidence = 0.52
    for signal in SIGNALS:
        confidence += float(signals.get(signal, 0.0)) * float(weights.get(signal, 0.0))
    return min(1.0, round(confidence, 6))


def _single_line_replacement(patch):
    removed = []
    added = []
    target = ""
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) == 4:
                target = parts[2][2:]
        elif line.startswith(("---", "+++", "@@")):
            continue
        elif line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    if len(removed) == 1 and len(added) == 1:
        return target, removed[0], added[0]
    return "", "", ""


def _is_test_path(path):
    parts = PurePosixPath(path).parts
    return "tests" in parts or PurePosixPath(path).name.startswith("test_")


def suggest_generalizations(repo_path, successful_patch, limit=3):
    target, old, new = _single_line_replacement(successful_patch)
    if not old or old == new:
        return []
    repo = Path(repo_path)
    suggestions = []
    for path in sorted(repo.rglob("*.py")):
        relative = path.relative_to(repo).as_posix()
        if relative == target or _is_test_path(relative):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for index, line in enumerate(lines, start=1):
            if line != old:
                continue
            suggestions.append(
                "\n".join(
                    [
                        f"diff --git a/{relative} b/{relative}",
                        f"--- a/{relative}",
                        f"+++ b/{relative}",
                        f"@@ -{index} +{index} @@",
                        f"-{old}",
                        f"+{new}",
                        "",
                    ]
                )
            )
            break
        if len(suggestions) >= limit:
            break
    return suggestions
