from test_runner import collect_tests, run_test_subset, run_tests


def test_run_tests_captures_a_passing_pytest_run(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    result = run_tests(tmp_path)

    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert "1 passed" in result["output"]
    assert result["errors"] == ""


def test_run_tests_captures_a_failing_pytest_run(tmp_path):
    (tmp_path / "test_bad.py").write_text(
        "def test_bad():\n    assert 1 == 2\n", encoding="utf-8"
    )

    result = run_tests(tmp_path)

    assert result["passed"] is False
    assert result["exit_code"] != 0
    assert "assert 1 == 2" in result["output"]


def test_run_tests_does_not_reuse_stale_bytecode_after_equal_size_edit(tmp_path):
    module = tmp_path / "subject.py"
    module.write_text("value = False\n", encoding="utf-8")
    (tmp_path / "test_subject.py").write_text(
        "from subject import value\n\ndef test_value():\n    assert value\n",
        encoding="utf-8",
    )
    assert run_tests(tmp_path)["passed"] is False

    module.write_text("value = True \n", encoding="utf-8")

    assert run_tests(tmp_path)["passed"] is True


def test_collect_tests_returns_pytest_node_ids(tmp_path):
    (tmp_path / "test_sample.py").write_text(
        "def test_one():\n    assert True\n\n"
        "def test_two():\n    assert True\n",
        encoding="utf-8",
    )

    assert collect_tests(tmp_path) == [
        "test_sample.py::test_one",
        "test_sample.py::test_two",
    ]


def test_run_test_subset_runs_only_selected_nodes(tmp_path):
    (tmp_path / "test_sample.py").write_text(
        "def test_good():\n    assert True\n\n"
        "def test_bad():\n    assert False\n",
        encoding="utf-8",
    )

    result = run_test_subset(tmp_path, ["test_sample.py::test_good"])

    assert result["passed"] is True
    assert "1 passed" in result["output"]


def test_run_test_subset_empty_selection_is_success(tmp_path):
    assert run_test_subset(tmp_path, [])["passed"] is True
