from pathlib import Path


CHUNK_TOKENS = 400
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "node_modules",
    "__pycache__",
    "tests",
}

_INDEX = []


def _is_source_file(path, repo):
    relative = path.relative_to(repo)
    return not any(part in IGNORED_DIRS for part in relative.parts[:-1])


def _chunk_file(relative_path, content):
    if not content.strip():
        return []

    chunks = []
    current_lines = []
    current_tokens = 0
    start_line = 1

    for line_number, line in enumerate(content.splitlines(keepends=True), start=1):
        line_tokens = len(line.split())
        if current_lines and current_tokens + line_tokens > CHUNK_TOKENS:
            chunks.append(
                {
                    "file": relative_path,
                    "content": "".join(current_lines),
                    "lines": (start_line, line_number - 1),
                }
            )
            current_lines = []
            current_tokens = 0
            start_line = line_number
        current_lines.append(line)
        current_tokens += line_tokens

    if current_lines:
        chunks.append(
            {
                "file": relative_path,
                "content": "".join(current_lines),
                "lines": (start_line, len(content.splitlines())),
            }
        )
    return chunks


def index_repo(repo_path):
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"Repository path is not a directory: {repo}")

    indexed = []
    for path in sorted(repo.rglob("*.py")):
        if not path.is_file() or path.is_symlink() or not _is_source_file(path, repo):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        relative = path.relative_to(repo).as_posix()
        indexed.extend(_chunk_file(relative, content))

    global _INDEX
    _INDEX = indexed
    return get_index()


def get_index():
    return [chunk.copy() for chunk in _INDEX]
