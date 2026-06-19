from test_runner import run_tests


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
