from difflib import SequenceMatcher

from memory.patterns import extract_error_type, extract_file, normalize_error_message


def find_similar_cases(failure, memory):
    error_type = extract_error_type(failure)
    message = normalize_error_message(failure)
    file = extract_file(failure)
    ranked = []

    for record in memory:
        score = 0.0
        if error_type and record.get("error_type") == error_type:
            score += 50
        if file and record.get("file") == file:
            score += 40
        if message and record.get("error_message"):
            similarity = SequenceMatcher(None, message, record["error_message"]).ratio()
            if similarity >= 0.45:
                score += similarity * 30
        if score > 0:
            ranked.append((score, record))

    ranked.sort(
        key=lambda item: (item[0], item[1].get("timestamp", "")),
        reverse=True,
    )
    return [record.copy() for _, record in ranked[:3]]
