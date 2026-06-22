import math


MAX_CONTEXT_TOKENS = 1800


def estimate_tokens(text):
    return max(len(text.split()), math.ceil(len(text) / 4))


def _header(chunk, end_line=None):
    start_line, declared_end = chunk["lines"]
    end_line = declared_end if end_line is None else end_line
    scope = chunk.get("scope")
    suffix = f" SCOPE: {scope}" if scope else ""
    return f"FILE: {chunk['file']} (lines {start_line}-{end_line}){suffix}"


def _trim_syntax_chunk(chunk, remaining):
    selected = []
    start_line = chunk["lines"][0]
    for line in chunk["content"].splitlines(keepends=True):
        candidate = "".join([*selected, line]).rstrip()
        end_line = start_line + len(selected)
        block = f"{_header(chunk, end_line)}\n{candidate}"
        if estimate_tokens(block) > remaining:
            break
        selected.append(line)
    if not selected:
        return ""
    end_line = start_line + len(selected) - 1
    return f"{_header(chunk, end_line)}\n{''.join(selected).rstrip()}"


def build_context(chunks):
    blocks = []
    used_tokens = 0
    seen = set()

    for chunk in chunks:
        key = (chunk["file"], tuple(chunk["lines"]), chunk["content"])
        if key in seen:
            continue
        seen.add(key)

        block = f"{_header(chunk)}\n{chunk['content'].rstrip()}"
        remaining = MAX_CONTEXT_TOKENS - used_tokens
        if estimate_tokens(block) > remaining:
            if chunk.get("kind") != "syntax":
                continue
            block = _trim_syntax_chunk(chunk, remaining)
        if not block:
            continue

        block_tokens = estimate_tokens(block)
        if block_tokens > remaining:
            continue
        blocks.append(block)
        used_tokens += block_tokens

    return "\n\n".join(blocks)
