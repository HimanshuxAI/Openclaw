import os
from pathlib import Path
import subprocess
import sys
import tempfile


def _pytest(repo_path, args):
    with tempfile.TemporaryDirectory(prefix="openclaw-pycache-") as cache_dir:
        environment = os.environ.copy()
        environment["PYTHONPYCACHEPREFIX"] = cache_dir
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *args],
            cwd=Path(repo_path),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    return {
        "passed": result.returncode == 0,
        "output": result.stdout,
        "errors": result.stderr,
        "exit_code": result.returncode,
    }


def run_tests(repo_path):
    return _pytest(repo_path, [])


def collect_tests(repo_path):
    result = _pytest(repo_path, ["--collect-only", "-q"])
    if result["exit_code"] != 0:
        return []
    nodes = []
    for line in result["output"].splitlines():
        value = line.strip()
        if "::" in value and not value.startswith("<"):
            nodes.append(value)
    return nodes


def run_test_subset(repo_path, node_ids):
    selected = [node_id for node_id in node_ids if node_id]
    if not selected:
        return {"passed": True, "output": "", "errors": "", "exit_code": 0}
    return _pytest(repo_path, selected)
