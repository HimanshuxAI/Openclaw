import pytest

import main


def test_main_loads_resets_and_runs_local_repository(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(main, "load_local_repo", lambda path: tmp_path)
    monkeypatch.setattr(main, "reset_repo", lambda path: calls.append(("reset", path)))
    monkeypatch.setattr(main, "run_agent", lambda path: calls.append(("run", path)) or True)

    assert main.main(["--repo", str(tmp_path)]) == 0
    assert calls == [("reset", tmp_path), ("run", tmp_path)]


def test_main_clones_url_to_requested_path(monkeypatch, tmp_path):
    destination = tmp_path / "clone"
    calls = []
    monkeypatch.setattr(
        main,
        "clone_repo",
        lambda url, path: calls.append((url, path)) or destination,
    )
    monkeypatch.setattr(main, "reset_repo", lambda path: None)
    monkeypatch.setattr(main, "run_agent", lambda path: True)

    assert main.main(["--url", "https://example.test/repo.git", "--clone-path", str(destination)]) == 0
    assert calls == [("https://example.test/repo.git", destination)]


def test_main_returns_failure_when_agent_does_not_fix_tests(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "load_local_repo", lambda path: tmp_path)
    monkeypatch.setattr(main, "reset_repo", lambda path: None)
    monkeypatch.setattr(main, "run_agent", lambda path: False)

    assert main.main(["--repo", str(tmp_path)]) == 1


def test_parser_requires_exactly_one_repository_source():
    parser = main.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--repo", "one", "--url", "two"])
