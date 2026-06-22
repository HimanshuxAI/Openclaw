import re

from memory.patterns import extract_error_type


LOCATION_PATTERN = re.compile(r"((?:[A-Za-z]:)?[^:\s]+\.py):(\d+)")
NODE_PATTERN = re.compile(
    r"(?:FAILED\s+)?((?:[A-Za-z]:)?[^:\s]+\.py)::([A-Za-z_][A-Za-z0-9_]*)"
)
IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
IGNORED_IDENTIFIERS = {
    "assert",
    "error",
    "failed",
    "failure",
    "false",
    "from",
    "in",
    "line",
    "none",
    "pytest",
    "test",
    "traceback",
    "true",
}


def classify_failure(failure_text):
    error_type = extract_error_type(failure_text)
    if error_type in {"SyntaxError", "IndentationError", "TabError"}:
        return "syntax"
    if error_type in {"ImportError", "ModuleNotFoundError"}:
        return "import"
    if error_type == "AssertionError" or re.search(
        r"(?:^|\n)\s*[E>]?[ \t]*assert\b", failure_text, re.IGNORECASE
    ):
        return "assertion"
    if error_type in {"TypeError", "AttributeError"}:
        return "type"
    if error_type:
        return "runtime"
    return "unknown"


def extract_locations(failure_text):
    locations = []
    seen = set()
    for path, line in LOCATION_PATTERN.findall(failure_text):
        location = (path.replace("\\", "/"), int(line))
        if location not in seen:
            seen.add(location)
            locations.append(location)
    return tuple(locations)


def extract_pytest_node(failure_text):
    match = NODE_PATTERN.search(failure_text)
    if not match:
        return None
    return match.group(1).replace("\\", "/"), match.group(2)


def extract_identifiers(failure_text):
    values = []
    seen = set()
    for identifier in IDENTIFIER_PATTERN.findall(failure_text):
        normalized = identifier.lower()
        if len(identifier) < 3 or normalized in IGNORED_IDENTIFIERS:
            continue
        if identifier not in seen:
            seen.add(identifier)
            values.append(identifier)
    return tuple(values)


def analyze_failure(failure_text):
    return {
        "kind": classify_failure(failure_text),
        "locations": extract_locations(failure_text),
        "node": extract_pytest_node(failure_text),
        "identifiers": extract_identifiers(failure_text),
        "error_type": extract_error_type(failure_text),
    }
