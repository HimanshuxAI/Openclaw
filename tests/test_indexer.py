from rag.indexer import CHUNK_TOKENS, get_index, index_repo


def test_index_repo_includes_only_non_test_python_source(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text(
        "def charge_invoice():\n    return 'charged'\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_service.py").write_text("ignored = True\n", encoding="utf-8")
    for directory in (".venv", "venv", "build", "node_modules", "__pycache__"):
        ignored = tmp_path / directory
        ignored.mkdir()
        (ignored / "ignored.py").write_text("ignored = True\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not Python\n", encoding="utf-8")

    chunks = index_repo(tmp_path)

    assert chunks == [
        {
            "file": "app/service.py",
            "content": "def charge_invoice():\n    return 'charged'\n",
            "lines": (1, 2),
        }
    ]


def test_index_repo_keeps_production_modules_named_with_test_prefix(tmp_path):
    (tmp_path / "test_runner.py").write_text(
        "def run_tests():\n    return True\n", encoding="utf-8"
    )

    chunks = index_repo(tmp_path)

    assert chunks[0]["file"] == "test_runner.py"


def test_index_repo_chunks_large_files_on_line_boundaries(tmp_path):
    source = tmp_path / "large.py"
    source.write_text("".join(f"token_{line}\n" for line in range(1, 402)), encoding="utf-8")

    chunks = index_repo(tmp_path)

    assert CHUNK_TOKENS == 400
    assert [chunk["lines"] for chunk in chunks] == [(1, 400), (401, 401)]
    assert len(chunks[0]["content"].split()) == 400
    assert chunks[1]["content"] == "token_401\n"


def test_index_repo_replaces_previous_transient_index(tmp_path):
    first = tmp_path / "first"
    first.mkdir()
    (first / "first.py").write_text("first_value = 1\n", encoding="utf-8")
    second = tmp_path / "second"
    second.mkdir()
    (second / "second.py").write_text("second_value = 2\n", encoding="utf-8")

    original = index_repo(first)
    replacement = index_repo(second)

    assert original[0]["file"] == "first.py"
    assert replacement[0]["file"] == "second.py"
    assert get_index() == replacement
    assert get_index() is not replacement


def test_index_repo_skips_empty_python_files(tmp_path):
    (tmp_path / "empty.py").write_text("", encoding="utf-8")

    assert index_repo(tmp_path) == []
