from rag.indexer import index_repo
from rag.retriever import retrieve_context


def _write_sources(repo):
    app = repo / "app"
    app.mkdir()
    (app / "auth.py").write_text(
        "def authenticate_user(token):\n    raise InvalidToken(token)\n", encoding="utf-8"
    )
    (app / "billing.py").write_text(
        "def charge_invoice(invoice):\n    return payment_gateway.charge(invoice)\n",
        encoding="utf-8",
    )
    (app / "misc.py").write_text("def health_check():\n    return 'ok'\n", encoding="utf-8")
    index_repo(repo)


def test_retrieve_context_ranks_traceback_path_and_identifiers(tmp_path):
    _write_sources(tmp_path)

    chunks = retrieve_context(
        "FAILED app/auth.py::test_login InvalidToken in authenticate_user", k=5
    )

    assert chunks[0]["file"] == "app/auth.py"
    assert all(
        {"file", "content", "lines", "scope", "kind"} <= set(chunk)
        for chunk in chunks
    )


def test_retrieve_context_honors_configurable_top_k(tmp_path):
    _write_sources(tmp_path)

    chunks = retrieve_context("app payment return", k=1)

    assert len(chunks) == 1


def test_retrieve_context_returns_only_positive_matches(tmp_path):
    _write_sources(tmp_path)

    assert retrieve_context("quasar nebula", k=5) == []


def test_retrieve_context_rejects_negative_k(tmp_path):
    _write_sources(tmp_path)

    assert retrieve_context("authenticate_user", k=-1) == []


def test_retrieve_context_prioritizes_exact_traceback_file(tmp_path):
    (tmp_path / "target.py").write_text(
        "def run_target():\n    return True\n", encoding="utf-8"
    )
    (tmp_path / "caller.py").write_text(
        "\n".join(["target.run_target()"] * 10) + "\n", encoding="utf-8"
    )
    index_repo(tmp_path)

    chunks = retrieve_context("FAILED target.py::run_target", k=5)

    assert chunks[0]["file"] == "target.py"


def test_assertion_route_returns_test_then_directly_called_target(tmp_path):
    app = tmp_path / "app"
    tests = tmp_path / "tests"
    app.mkdir()
    tests.mkdir()
    (app / "service.py").write_text(
        "def calculate_total(items):\n    return sum(items)\n\n"
        "def health_check():\n    return 'ok'\n",
        encoding="utf-8",
    )
    (tests / "test_total.py").write_text(
        "from app.service import calculate_total\n\n"
        "def test_total():\n    assert calculate_total([2, 3]) == 5\n",
        encoding="utf-8",
    )
    index_repo(tmp_path)

    chunks = retrieve_context(
        "FAILED tests/test_total.py::test_total\n"
        "tests/test_total.py:4: AssertionError\nE assert 4 == 5"
    )

    assert [(chunk["file"], chunk["scope"]) for chunk in chunks] == [
        ("tests/test_total.py", "test_total"),
        ("app/service.py", "calculate_total"),
    ]


def test_syntax_route_returns_reported_window_before_module_context(tmp_path):
    (tmp_path / "broken.py").write_text(
        "import os\n\ndef broken(:\n    pass\n", encoding="utf-8"
    )
    index_repo(tmp_path)

    chunks = retrieve_context("broken.py:3: SyntaxError: invalid syntax")

    assert chunks[0]["file"] == "broken.py"
    assert chunks[0]["kind"] == "syntax"
    assert chunks[0]["lines"] == (1, 4)


def test_import_route_returns_importing_scope_and_named_local_definition(tmp_path):
    tests = tmp_path / "tests"
    app = tmp_path / "app"
    tests.mkdir()
    app.mkdir()
    (tests / "test_billing.py").write_text(
        "from app.billing import charge_invoice\n\n"
        "def test_charge():\n    assert charge_invoice()\n",
        encoding="utf-8",
    )
    (app / "billing.py").write_text(
        "def charge_invoice():\n    return True\n", encoding="utf-8"
    )
    index_repo(tmp_path)

    chunks = retrieve_context(
        "FAILED tests/test_billing.py::test_charge\n"
        "tests/test_billing.py:1: ImportError: cannot import name 'charge_invoice'"
    )

    assert chunks[0]["file"] == "tests/test_billing.py"
    assert any(chunk["scope"] == "charge_invoice" for chunk in chunks)


def test_runtime_route_prefers_innermost_traceback_scope(tmp_path):
    (tmp_path / "service.py").write_text(
        "def outer():\n    return inner()\n\n"
        "def inner():\n    raise ValueError('bad')\n",
        encoding="utf-8",
    )
    index_repo(tmp_path)

    chunks = retrieve_context(
        "service.py:2: in outer\nservice.py:5: in inner\nValueError: bad"
    )

    assert chunks[0]["scope"] == "inner"
    assert chunks[1]["scope"] == "outer"


def test_successful_patch_history_breaks_an_otherwise_equal_tie(tmp_path):
    (tmp_path / "alpha.py").write_text("def calculate():\n    return 1\n", encoding="utf-8")
    (tmp_path / "beta.py").write_text("def calculate():\n    return 2\n", encoding="utf-8")
    index_repo(tmp_path)
    memory = [
        {
            "error_type": "NameError",
            "error_message": "name calculate is not defined",
            "file": "tests/test_calc.py",
            "patch": "diff --git a/beta.py b/beta.py\n",
            "success": True,
            "timestamp": "2026-06-22T00:00:00+00:00",
        }
    ]

    chunks = retrieve_context("NameError: calculate", memory=memory)

    assert chunks[0]["file"] == "beta.py"
