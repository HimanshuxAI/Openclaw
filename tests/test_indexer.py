from rag.indexer import get_index, index_repo


def test_index_repo_includes_python_source_and_test_scopes(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text(
        "def charge_invoice():\n    return 'charged'\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_service.py").write_text(
        "def test_charge():\n    assert True\n", encoding="utf-8"
    )
    for directory in (".venv", "venv", "build", "node_modules", "__pycache__"):
        ignored = tmp_path / directory
        ignored.mkdir()
        (ignored / "ignored.py").write_text("ignored = True\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not Python\n", encoding="utf-8")

    chunks = index_repo(tmp_path)

    assert [(chunk["file"], chunk["scope"], chunk["is_test"]) for chunk in chunks] == [
        ("app/service.py", "charge_invoice", False),
        ("tests/test_service.py", "test_charge", True),
    ]


def test_index_repo_keeps_production_modules_named_with_test_prefix(tmp_path):
    (tmp_path / "test_runner.py").write_text(
        "def run_tests():\n    return True\n", encoding="utf-8"
    )

    chunks = index_repo(tmp_path)

    assert chunks[0]["file"] == "test_runner.py"


def test_index_repo_emits_module_function_and_method_slices(tmp_path):
    (tmp_path / "service.py").write_text(
        "import os\n"
        "DEFAULT = 2\n\n"
        "@trace\n"
        "def charge():\n"
        "    return send()\n\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return charge()\n",
        encoding="utf-8",
    )

    chunks = index_repo(tmp_path)

    assert [(chunk["kind"], chunk["scope"], chunk["lines"]) for chunk in chunks] == [
        ("module", "<module>", (1, 2)),
        ("function", "charge", (4, 6)),
        ("method", "Service.run", (9, 10)),
    ]
    assert chunks[0]["imports"] == ("os",)
    assert chunks[1]["calls"] == ("send",)
    assert chunks[2]["calls"] == ("charge",)
    assert chunks[1]["content"].startswith("@trace\n")


def test_index_repo_keeps_nested_functions_in_their_enclosing_slice(tmp_path):
    (tmp_path / "service.py").write_text(
        "def outer():\n"
        "    def inner():\n"
        "        return helper()\n"
        "    return inner()\n",
        encoding="utf-8",
    )

    chunks = index_repo(tmp_path)

    assert [chunk["scope"] for chunk in chunks] == ["outer"]
    assert chunks[0]["calls"] == ("helper", "inner")


def test_index_repo_emits_syntax_fallback_for_unparseable_test(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

    chunks = index_repo(tmp_path)

    assert len(chunks) == 1
    assert chunks[0]["kind"] == "syntax"
    assert chunks[0]["scope"] == "<syntax>"
    assert chunks[0]["is_test"] is True
    assert chunks[0]["lines"] == (1, 2)


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
