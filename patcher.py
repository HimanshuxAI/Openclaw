import ast
import json
from pathlib import Path, PurePosixPath
import os
import re
import shlex
import subprocess
import sys
import tempfile

from rag.context_builder import build_context, estimate_tokens
from rag.indexer import index_repo
from rag.retriever import retrieve_context
from llm_client import generate_nvidia_patch
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


def generate_patch(failure_output, repo_path, metrics=None, memory=None):
    generation_metrics = metrics if metrics is not None else {}
    generation_metrics["model_calls"] = 0
    generation_metrics["context_tokens"] = 0
    try:
        index_repo(repo_path)
        chunks = retrieve_context(failure_output, k=5, memory=memory)
        code_context = build_context(chunks)
    except (OSError, ValueError):
        code_context = ""
    generation_metrics["context_tokens"] = estimate_tokens(code_context)
    if os.environ.get("NVIDIA_API_KEY", "").strip():
        generation_metrics["model_calls"] = 1
        model_patch = generate_nvidia_patch(failure_output, code_context)
        if model_patch:
            return model_patch
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


def _is_test_target(repo, relative):
    if "tests" in relative.parts or relative.name == "conftest.py":
        return True
    if not (relative.name.startswith("test_") or relative.name.endswith("_test.py")):
        return False
    try:
        tree = ast.parse(repo.joinpath(*relative.parts).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return True
    return any(
        (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
        or (isinstance(node, ast.ClassDef) and node.name.startswith("Test"))
        for node in tree.body
    )


def _validated_target(repo, patch):
    if not isinstance(patch, str) or not patch.strip():
        return None
    try:
        encoded = patch.encode("utf-8")
    except UnicodeEncodeError:
        return None
    if len(encoded) > MAX_PATCH_BYTES or "\x00" in patch:
        return None

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
        return None

    starts = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    if len(starts) != 1 or starts[0] != 0:
        return None

    starts.append(len(lines))
    target = None
    for start, end in zip(starts, starts[1:]):
        block = lines[start:end]
        try:
            diff_parts = shlex.split(block[0])
        except ValueError:
            return None
        if len(diff_parts) != 4 or diff_parts[:2] != ["diff", "--git"]:
            return None

        old_relative = _safe_relative_path(diff_parts[2], "a/")
        new_relative = _safe_relative_path(diff_parts[3], "b/")
        if old_relative is None or old_relative != new_relative:
            return None

        old_headers = [line for line in block if line.startswith("--- ")]
        new_headers = [line for line in block if line.startswith("+++ ")]
        if len(old_headers) != 1 or len(new_headers) != 1:
            return None
        old_header = _header_path(old_headers[0], "--- ")
        new_header = _header_path(new_headers[0], "+++ ")
        if old_header != f"a/{old_relative.as_posix()}":
            return None
        if new_header != f"b/{new_relative.as_posix()}":
            return None
        if sum(line.startswith("@@ ") for line in block) != 1:
            return None
        if not _target_is_regular_file(repo, new_relative):
            return None
        if new_relative.suffix != ".py" or _is_test_target(repo, new_relative):
            return None
        target = new_relative
    return target


def _validate_patch(repo, patch):
    return _validated_target(repo, patch) is not None


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


def _absolute_imports(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return None
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module.split(".", 1)[0])
    return imports


def _imports_resolve(worktree, imports):
    if not imports:
        return True
    script = (
        "import importlib.util,json,sys;"
        "names=json.loads(sys.argv[1]);"
        "sys.exit(0 if all(importlib.util.find_spec(name) is not None for name in names) else 1)"
    )
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(worktree) + (os.pathsep + existing if existing else "")
    result = subprocess.run(
        [sys.executable, "-c", script, json.dumps(sorted(imports))],
        cwd=worktree,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _preflight_patch(repo, patch, target):
    current_imports = _absolute_imports(repo.joinpath(*target.parts))
    if current_imports is None:
        return False

    with tempfile.TemporaryDirectory(prefix="openclaw-preflight-") as temporary:
        worktree = Path(temporary) / "worktree"
        add_result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if add_result.returncode != 0:
            return False

        safe = False
        cleanup_ok = False
        try:
            baseline = subprocess.run(
                ["git", "diff", "--binary", "HEAD", "--"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            if baseline.returncode != 0:
                return False
            if baseline.stdout and _git_apply(worktree, baseline.stdout, check=False).returncode:
                return False
            if _git_apply(worktree, patch, check=False).returncode != 0:
                return False

            changed = worktree.joinpath(*target.parts)
            environment = os.environ.copy()
            environment["PYTHONPYCACHEPREFIX"] = str(Path(temporary) / "pycache")
            compile_result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(changed)],
                cwd=worktree,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if compile_result.returncode != 0:
                return False

            changed_imports = _absolute_imports(changed)
            if changed_imports is None or not _imports_resolve(
                worktree, changed_imports - current_imports
            ):
                return False
            safe = True
        finally:
            remove_result = subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            cleanup_ok = remove_result.returncode == 0
        return safe and cleanup_ok


def apply_patch(repo_path, patch):
    try:
        repo = load_local_repo(repo_path)
    except (ValueError, RuntimeError):
        return False
    target = _validated_target(repo, patch)
    if target is None:
        return False
    if _git_apply(repo, patch, check=True).returncode != 0:
        return False
    if not _preflight_patch(repo, patch, target):
        return False
    return _git_apply(repo, patch, check=False).returncode == 0
