import inspect

import pytest

import web_server


def test_execute_agent_rejects_blank_repository_path():
    with pytest.raises(ValueError, match="Repository path is required"):
        web_server.execute_agent("   ")


def test_execute_agent_loads_resets_and_runs_in_order(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    calls = []
    monkeypatch.setattr(
        web_server,
        "load_local_repo",
        lambda path: calls.append(("load", path)) or repo,
    )
    monkeypatch.setattr(
        web_server,
        "reset_repo",
        lambda path: calls.append(("reset", path)),
    )

    def run(path):
        calls.append(("run", path))
        print("[openclaw] SUCCESS: tests pass")
        return True

    monkeypatch.setattr(web_server, "run_agent", run)

    result = web_server.execute_agent("/target/repo")

    assert calls == [
        ("load", "/target/repo"),
        ("reset", repo),
        ("run", repo),
    ]
    assert result == {
        "success": True,
        "repo": str(repo),
        "output": (
            f"[openclaw] Resetting repository before run: {repo}\n"
            "[openclaw] SUCCESS: tests pass\n"
        ),
    }


def test_execute_agent_preserves_stopped_result(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    monkeypatch.setattr(web_server, "load_local_repo", lambda path: repo)
    monkeypatch.setattr(web_server, "reset_repo", lambda path: None)
    monkeypatch.setattr(web_server, "run_agent", lambda path: False)

    result = web_server.execute_agent(str(repo))

    assert result["success"] is False
    assert result["repo"] == str(repo)


def test_execute_agent_propagates_repository_validation_errors(monkeypatch):
    monkeypatch.setattr(
        web_server,
        "load_local_repo",
        lambda path: (_ for _ in ()).throw(ValueError("not a Git repository")),
    )

    with pytest.raises(ValueError, match="not a Git repository"):
        web_server.execute_agent("/missing")


def test_execute_agent_clones_https_git_url_before_running(monkeypatch, tmp_path):
    url = "https://github.com/HimanshuAI/Openclaw"
    clone_root = tmp_path / "clones"
    repo = tmp_path / "checked-out-repo"
    calls = []
    monkeypatch.setenv("OPENCLAW_CLONE_ROOT", str(clone_root))
    monkeypatch.setattr(
        web_server,
        "clone_repo",
        lambda source, destination: calls.append(("clone", source, destination)) or repo,
    )
    monkeypatch.setattr(
        web_server, "load_local_repo", lambda path: (_ for _ in ()).throw(AssertionError())
    )
    monkeypatch.setattr(web_server, "reset_repo", lambda path: calls.append(("reset", path)))
    monkeypatch.setattr(web_server, "run_agent", lambda path: calls.append(("run", path)) or True)

    result = web_server.execute_agent(url)

    clone_call = calls[0]
    assert clone_call[0:2] == ("clone", url)
    assert clone_call[2].parent == clone_root
    assert clone_call[2].name.startswith("Openclaw-")
    assert calls[1:] == [("reset", repo), ("run", repo)]
    assert result["repo"] == str(repo)


def test_execute_agent_reuses_existing_url_clone(monkeypatch, tmp_path):
    url = "https://github.com/HimanshuAI/Openclaw"
    monkeypatch.setenv("OPENCLAW_CLONE_ROOT", str(tmp_path / "clones"))
    destination = web_server._clone_destination(url)
    destination.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(
        web_server,
        "clone_repo",
        lambda source, path: (_ for _ in ()).throw(AssertionError("clone called")),
    )
    monkeypatch.setattr(
        web_server,
        "load_local_repo",
        lambda path: calls.append(("load", path)) or destination,
    )
    monkeypatch.setattr(web_server, "reset_repo", lambda path: None)
    monkeypatch.setattr(web_server, "run_agent", lambda path: True)

    assert web_server.execute_agent(url)["repo"] == str(destination)
    assert calls == [("load", destination)]


def test_execute_agent_rejects_credentials_embedded_in_git_url():
    with pytest.raises(ValueError, match="embedded credentials"):
        web_server.execute_agent("https://token@github.com/owner/repo.git")


def test_serve_defaults_to_loopback_only():
    signature = inspect.signature(web_server.serve)

    assert signature.parameters["host"].default == "127.0.0.1"
    assert signature.parameters["port"].default == 8000
    assert web_server.MAX_REQUEST_BYTES == 64 * 1024
