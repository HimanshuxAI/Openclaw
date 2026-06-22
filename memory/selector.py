from difflib import SequenceMatcher
from pathlib import PurePosixPath

from memory.patterns import extract_error_type, extract_file, normalize_error_message


REPLAY_THRESHOLD = 0.88


def similarity_score(failure, record):
    error_type = extract_error_type(failure)
    message = normalize_error_message(failure)
    file = extract_file(failure)

    same_error = bool(error_type and record.get("error_type") == error_type)
    record_message = record.get("error_message", "")
    message_similarity = (
        SequenceMatcher(None, message, record_message).ratio()
        if message and record_message
        else 0.0
    )
    record_file = record.get("file", "")
    same_file = bool(file and record_file and file == record_file)
    same_basename = bool(
        file
        and record_file
        and PurePosixPath(file).name == PurePosixPath(record_file).name
    )

    if not same_error and not same_file and message_similarity < 0.45:
        return 0.0

    score = 0.35 if same_error else 0.0
    score += message_similarity * 0.35
    if same_file:
        score += 0.20
    elif same_basename:
        score += 0.12
    if record.get("success"):
        score += 0.10
    return min(1.0, round(score, 6))


def find_similar_cases(failure, memory):
    ranked = []
    for record in memory:
        score = similarity_score(failure, record)
        if score > 0:
            ranked.append((score, record))

    ranked.sort(
        key=lambda item: (item[0], item[1].get("timestamp", "")),
        reverse=True,
    )
    return [
        {"score": score, "record": record.copy()}
        for score, record in ranked[:3]
    ]
