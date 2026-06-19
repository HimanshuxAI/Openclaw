import subprocess

import pytest

from repo_manager import clone_repo, load_local_repo, reset_repo


def test_load_local_repo_returns_resolved_git_repository(git_repo):
    assert load_local_repo(git_repo) == git_repo.resolve()


def test_load_local_repo_rejects_non_git_directory(tmp_path):
    with pytest.raises(ValueError, match="not a Git repository"):
        load_local_repo(tmp_path)


def test_reset_repo_restores_tracked_and_removes_untracked_files(git_repo):
    (git_repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (git_repo / "untracked.txt").write_text("remove me\n", encoding="utf-8")

    reset_repo(git_repo)

    assert (git_repo / "tracked.txt").read_text(encoding="utf-8") == "original\n"
    assert not (git_repo / "untracked.txt").exists()


def test_clone_repo_clones_local_repository(git_repo, tmp_path):
    destination = tmp_path / "clone"

    result = clone_repo(str(git_repo), destination)

    assert result == destination.resolve()
    assert (destination / "tracked.txt").read_text(encoding="utf-8") == "original\n"
    status = subprocess.run(
        ["git", "-C", str(destination), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""
