import subprocess

import pytest


@pytest.fixture(autouse=True)
def memory_path(tmp_path, monkeypatch):
    path = tmp_path / "openclaw-memory.json"
    monkeypatch.setenv("OPENCLAW_MEMORY_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def disable_live_nvidia_api(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "tests@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "OpenClaw Tests"],
        check=True,
    )
    (repo / "tracked.txt").write_text("original\n", encoding="utf-8")
    (repo / "module.py").write_text("VALUE = 'original'\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "tracked.txt", "module.py"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
    return repo
