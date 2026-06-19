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
    assert all(set(chunk) == {"file", "content", "lines"} for chunk in chunks)


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
