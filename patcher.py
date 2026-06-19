from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess

from rag.context_builder import build_context
from rag.indexer import index_repo
from rag.retriever import retrieve_context
from repo_manager import load_local_repo


MAX_PATCH_BYTES = 100 * 1024
PATCH_START = "OPENCLAW_PATCH_START"
PATCH_END = "OPENCLAW_PATCH_END"


def mock_llm_fix(failure_text, code_context=""):
    del code_context
    pattern = rf"(?:^|\n){PATCH_START}\r?\n(.*?)(?:^|\n){PATCH_END}(?:\r?\n|$)"
    match = re.search(pattern, failure_text, flags=re.DOTALL)
    if not match:
        return ""
    return match.group(1).rstrip("\r\n") + "\n"


def generate_patch(failure_output, repo_path):
    try:
        index_repo(repo_path)
        chunks = retrieve_context(failure_output, k=5)
        code_context = build_context(chunks)
    except (OSError, ValueError):
        code_context = ""
    return mock_llm_fix(failure_output, code_context)


def _safe_relative_path(header_path, prefix):
    if not header_path.startswith(prefix):
        return None
    relative = PurePosixPath(header_path[len(prefix) :])
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        return None
    if ".git" in relative.parts:
        return None
    return relative


def _header_path(line, marker):
    try:
        values = shlex.split(line[len(marker) :].strip())
    except ValueError:
        return None
    return values[0] if values else None


def _target_is_regular_file(repo, relative):
    target = repo.joinpath(*relative.parts)
    current = repo
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    if not target.is_file():
        return False
    try:
        target.resolve().relative_to(repo)
    except ValueError:
        return False
    return True


def _validate_patch(repo, patch):
    if not isinstance(patch, str) or not patch.strip():
        return False
    try:
        encoded = patch.encode("utf-8")
    except UnicodeEncodeError:
        return False
    if len(encoded) > MAX_PATCH_BYTES or "\x00" in patch:
        return False

    forbidden = (
        "GIT binary patch",
        "Binary files ",
        "new file mode ",
        "deleted file mode ",
        "rename from ",
        "rename to ",
        "copy from ",
        "copy to ",
        "diff --cc ",
        "diff --combined ",
    )
    lines = patch.splitlines()
    if any(line.startswith(forbidden) for line in lines):
        return False

    starts = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    if not starts or starts[0] != 0:
        return False

    starts.append(len(lines))
    for start, end in zip(starts, starts[1:]):
        block = lines[start:end]
        try:
            diff_parts = shlex.split(block[0])
        except ValueError:
            return False
        if len(diff_parts) != 4 or diff_parts[:2] != ["diff", "--git"]:
            return False

        old_relative = _safe_relative_path(diff_parts[2], "a/")
        new_relative = _safe_relative_path(diff_parts[3], "b/")
        if old_relative is None or old_relative != new_relative:
            return False

        old_headers = [line for line in block if line.startswith("--- ")]
        new_headers = [line for line in block if line.startswith("+++ ")]
        if len(old_headers) != 1 or len(new_headers) != 1:
            return False
        old_header = _header_path(old_headers[0], "--- ")
        new_header = _header_path(new_headers[0], "+++ ")
        if old_header != f"a/{old_relative.as_posix()}":
            return False
        if new_header != f"b/{new_relative.as_posix()}":
            return False
        if not any(line.startswith("@@ ") for line in block):
            return False
        if not _target_is_regular_file(repo, new_relative):
            return False
    return True


def _git_apply(repo, patch, check):
    args = ["git", "apply"]
    if check:
        args.append("--check")
    args.extend(["--whitespace=error-all", "-"])
    return subprocess.run(
        args,
        cwd=repo,
        input=patch,
        capture_output=True,
        text=True,
        check=False,
    )


def apply_patch(repo_path, patch):
    try:
        repo = load_local_repo(repo_path)
    except (ValueError, RuntimeError):
        return False
    if not _validate_patch(repo, patch):
        return False
    if _git_apply(repo, patch, check=True).returncode != 0:
        return False
    return _git_apply(repo, patch, check=False).returncode == 0
