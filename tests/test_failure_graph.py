import subprocess

from failure_graph import FailureGraph, build_dependency_graph


def test_dependency_graph_extracts_imports_calls_and_test_edges(git_repo):
    (git_repo / "service.py").write_text(
        "def normalize(value):\n    return value.strip()\n", encoding="utf-8"
    )
    (git_repo / "consumer.py").write_text(
        "from service import normalize\n\n"
        "def clean(value):\n"
        "    return normalize(value)\n",
        encoding="utf-8",
    )
    tests = git_repo / "tests"
    tests.mkdir()
    (tests / "test_consumer.py").write_text(
        "from consumer import clean\n\n"
        "def test_clean():\n"
        "    assert clean(' x ') == 'x'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "graph"], check=True)

    graph = build_dependency_graph(git_repo)

    assert "file:consumer.py" in graph.nodes
    assert "function:consumer.py::clean" in graph.nodes
    assert "test_case:tests/test_consumer.py::test_clean" in graph.nodes
    assert "file:service.py" in graph.edges["file:consumer.py"]["imports"]
    assert (
        "function:service.py::normalize"
        in graph.edges["function:consumer.py::clean"]["calls"]
    )
    assert (
        "function:consumer.py::clean"
        in graph.edges["test_case:tests/test_consumer.py::test_clean"]["calls"]
    )


def test_failure_graph_ranks_shared_root_causes_from_cofailures(git_repo):
    (git_repo / "mathlib.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    tests = git_repo / "tests"
    tests.mkdir()
    (tests / "test_math.py").write_text(
        "from mathlib import add\n\n"
        "def test_add_positive():\n"
        "    assert add(2, 3) == 5\n\n"
        "def test_add_zero():\n"
        "    assert add(0, 3) == 3\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "math tests"], check=True)
    graph = FailureGraph.build(git_repo)
    failure_output = (
        "FAILED tests/test_math.py::test_add_positive - AssertionError\n"
        "FAILED tests/test_math.py::test_add_zero - AssertionError\n"
    )

    graph.update_after_test_run(failure_output)
    causes = graph.get_root_causes(
        [
            "tests/test_math.py::test_add_positive",
            "tests/test_math.py::test_add_zero",
        ]
    )

    assert causes[0]["node"] == "function:mathlib.py::add"
    assert causes[0]["score"] >= 2
    assert "test_case:tests/test_math.py::test_add_zero" in graph.get_related_nodes(
        "test_case:tests/test_math.py::test_add_positive"
    )
