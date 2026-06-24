from difflib import SequenceMatcher
from collections import Counter
from pathlib import PurePosixPath

from memory.patterns import extract_error_type, extract_file, normalize_error_message


REPLAY_THRESHOLD = 0.88
TEMPLATE_THRESHOLD = 0.78


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


def find_fix_templates(failure, memory):
    candidates = []
    latest_by_patch = {}
    for record in memory:
        patch = record.get("patch")
        if patch and record.get("timestamp", "") >= latest_by_patch.get(patch, {}).get(
            "timestamp", ""
        ):
            latest_by_patch[patch] = record
    patch_counts = Counter(
        record["patch"] for record in memory if record.get("success") and record.get("patch")
    )
    for record in memory:
        if not record.get("success") or not record.get("patch"):
            continue
        latest = latest_by_patch.get(record["patch"], {})
        if not latest.get("success"):
            continue
        score = similarity_score(failure, record)
        cluster_bonus = min(0.12, max(0, patch_counts[record["patch"]] - 1) * 0.04)
        confidence = min(1.0, round(score + cluster_bonus, 6))
        if confidence >= TEMPLATE_THRESHOLD:
            candidates.append((confidence, patch_counts[record["patch"]], record))

    candidates.sort(key=lambda item: (item[0], item[1], item[2].get("timestamp", "")), reverse=True)
    seen = set()
    templates = []
    for confidence, count, record in candidates:
        patch = record["patch"]
        if patch in seen:
            continue
        seen.add(patch)
        templates.append(
            {
                "score": confidence,
                "count": count,
                "record": record.copy(),
            }
        )
        if len(templates) == 3:
            break
    return templates
