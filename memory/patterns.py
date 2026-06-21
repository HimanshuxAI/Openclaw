import re


ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
ERROR_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b")
FILE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])((?:[A-Za-z]:)?[A-Za-z0-9_./\\-]+\.py)(?=::|:\d+|\s|$)"
)


def extract_error_type(failure_text):
    match = ERROR_PATTERN.search(failure_text)
    if match:
        return match.group(1)
    if re.search(r"(?:^|\n)\s*[E>]?[ \t]*assert\b", failure_text, re.IGNORECASE):
        return "AssertionError"
    return ""


def normalize_error_message(failure_text):
    cleaned = ANSI_PATTERN.sub("", failure_text)
    error_type = extract_error_type(cleaned)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    selected = ""
    if error_type:
        selected = next((line for line in lines if error_type in line), "")
    if not selected and error_type == "AssertionError":
        selected = next(
            (line for line in lines if re.match(r"^[E>]?\s*assert\b", line, re.IGNORECASE)),
            "",
        )
    if not selected and lines:
        selected = lines[0]

    selected = re.sub(r"^[E>]\s*", "", selected)
    if error_type and f"{error_type}:" in selected:
        selected = selected.split(f"{error_type}:", 1)[1]
    selected = re.sub(r"0x[0-9a-fA-F]+", "<address>", selected)
    selected = re.sub(r"\b\d+(?:\.\d+)?\b", "<number>", selected)
    selected = re.sub(r"\s+", " ", selected).strip().lower()
    return selected


def extract_file(failure_text):
    match = FILE_PATTERN.search(failure_text)
    if not match:
        return ""
    return match.group(1).replace("\\", "/")
