from pathlib import Path
import subprocess


def _run_git(args, *, cwd=None):
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise RuntimeError(message)
    return result


def clone_repo(url, path):
    destination = Path(path).expanduser().resolve()
    if destination.exists():
        raise ValueError(f"Clone destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", "--", str(url), str(destination)])
    return load_local_repo(destination)


def load_local_repo(path):
    repo = Path(path).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"Repository path is not a directory: {repo}")
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise ValueError(f"Path is not a Git repository: {repo}")
    return repo


def reset_repo(path):
    repo = load_local_repo(path)
    _run_git(["reset", "--hard", "HEAD"], cwd=repo)
    _run_git(["clean", "-fd"], cwd=repo)
