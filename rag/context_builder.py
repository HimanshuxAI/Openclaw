import math


MAX_CONTEXT_TOKENS = 1800


def _token_count(text):
    return max(len(text.split()), math.ceil(len(text) / 4))


def build_context(chunks):
    blocks = []
    used_tokens = 0
    seen = set()

    for chunk in chunks:
        key = (chunk["file"], tuple(chunk["lines"]), chunk["content"])
        if key in seen:
            continue
        seen.add(key)

        start_line, declared_end = chunk["lines"]
        header = f"FILE: {chunk['file']} (lines {start_line}-{declared_end})"
        available = MAX_CONTEXT_TOKENS - used_tokens - _token_count(header)
        if available <= 0:
            break

        selected = []
        selected_tokens = 0
        for line in chunk["content"].splitlines(keepends=True):
            line_tokens = _token_count(line)
            if selected_tokens + line_tokens > available:
                break
            selected.append(line)
            selected_tokens += line_tokens

        if not selected or selected_tokens == 0:
            continue
        actual_end = min(declared_end, start_line + len(selected) - 1)
        header = f"FILE: {chunk['file']} (lines {start_line}-{actual_end})"
        block = f"{header}\n{''.join(selected).rstrip()}"
        block_tokens = _token_count(block)
        if used_tokens + block_tokens > MAX_CONTEXT_TOKENS:
            break
        blocks.append(block)
        used_tokens += block_tokens

    return "\n\n".join(blocks)
