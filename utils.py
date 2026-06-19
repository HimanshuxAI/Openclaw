def extract_failure(result):
    parts = [result.get("output", "").strip(), result.get("errors", "").strip()]
    return "\n\n".join(part for part in parts if part)


def log(message):
    print(f"[openclaw] {message}", flush=True)
