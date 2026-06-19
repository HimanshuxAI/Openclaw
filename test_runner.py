import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run_tests(repo_path):
    with tempfile.TemporaryDirectory(prefix="openclaw-pycache-") as cache_dir:
        environment = os.environ.copy()
        environment["PYTHONPYCACHEPREFIX"] = cache_dir
        result = subprocess.run(
            [sys.executable, "-m", "pytest"],
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
