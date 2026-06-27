import subprocess

import pytest

import patcher
from patcher import (
    apply_patch,
    generate_patch,
    generate_patch_candidates,
    mock_llm_fix,
    rank_patch_candidates,
    revert_patch,
    score_patch,
)


VALID_PATCH = """diff --git a/module.py b/module.py
--- a/module.py
+++ b/module.py
@@ -1 +1 @@
-VALUE = 'original'
+VALUE = 'fixed'
"""


def test_mock_llm_extracts_explicit_patch_block():
    failure = (
        "test failed\nOPENCLAW_PATCH_START\n"
        + VALID_PATCH
        + "OPENCLAW_PATCH_END\nother output"
    )

    assert mock_llm_fix(failure) == VALID_PATCH
    assert generate_patch(failure, "/unused") == VALID_PATCH


def test_generate_patch_candidates_extracts_multiple_mock_patch_blocks():
    second = VALID_PATCH.replace("fixed", "also_fixed")
    failure = (
        "failed\nOPENCLAW_PATCH_START\n"
        + VALID_PATCH
        + "\nOPENCLAW_PATCH_END\nOPENCLAW_PATCH_START\n"
        + second
        + "OPENCLAW_PATCH_END\n"
    )

    assert generate_patch_candidates(failure, "/unused") == [VALID_PATCH, second]


def test_mock_llm_returns_empty_string_for_unknown_failure():
    assert mock_llm_fix("ordinary assertion failure") == ""


def test_generate_patch_passes_failure_and_relevant_context_to_llm(
    git_repo, monkeypatch
):
    (git_repo / "service.py").write_text(
        "def calculate_total(items):\n    return sum(items)\n", encoding="utf-8"
    )
    (git_repo / "health.py").write_text(
        "def health_check():\n    return 'ok'\n", encoding="utf-8"
    )
    received = {}

    def capture_llm(failure_text, code_context):
        received["failure"] = failure_text
        received["context"] = code_context
        return "generated patch"

    monkeypatch.setattr(patcher, "mock_llm_fix", capture_llm)
    failure = "FAILED test_total.py NameError: calculate_total"

    assert generate_patch(failure, git_repo) == "generated patch"
    assert received["failure"] == failure
    assert "FILE: service.py" in received["context"]
    assert "calculate_total" in received["context"]
    assert "health.py" not in received["context"]


def test_generate_patch_prefers_configured_nvidia_model(monkeypatch, git_repo):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(
        patcher, "generate_nvidia_patch", lambda failure, context: VALID_PATCH
    )
    monkeypatch.setattr(
        patcher,
        "mock_llm_fix",
        lambda failure, context: (_ for _ in ()).throw(AssertionError("mock called")),
    )

    assert generate_patch("AssertionError", git_repo) == VALID_PATCH


def test_generate_patch_reports_context_tokens_and_model_calls(monkeypatch, git_repo):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(
        patcher, "generate_nvidia_patch", lambda failure, context: VALID_PATCH
    )
    metrics = {}

    assert generate_patch("AssertionError", git_repo, metrics=metrics) == VALID_PATCH
    assert metrics["model_calls"] == 1
    assert 0 <= metrics["context_tokens"] < 2000


def test_generate_patch_falls_back_to_mock_when_model_returns_no_diff(
    monkeypatch, git_repo
):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(patcher, "generate_nvidia_patch", lambda failure, context: "")
    failure = "OPENCLAW_PATCH_START\n" + VALID_PATCH + "OPENCLAW_PATCH_END\n"

    assert generate_patch(failure, git_repo) == VALID_PATCH


def test_apply_patch_modifies_existing_regular_file(git_repo):
    assert apply_patch(git_repo, VALID_PATCH) is True
    assert (git_repo / "module.py").read_text(encoding="utf-8") == "VALUE = 'fixed'\n"


def test_revert_patch_removes_applied_candidate(git_repo):
    assert apply_patch(git_repo, VALID_PATCH) is True
    assert revert_patch(git_repo, VALID_PATCH) is True

    assert (git_repo / "module.py").read_text(encoding="utf-8") == "VALUE = 'original'\n"


def test_score_patch_rejects_invalid_diff_and_rewards_minimal_valid_patch(git_repo):
    invalid = "not a diff\n"

    invalid_score = score_patch(git_repo, invalid, "AssertionError")
    valid_score = score_patch(git_repo, VALID_PATCH, "AssertionError: VALUE")

    assert invalid_score["confidence"] == 0.0
    assert invalid_score["accepted"] is False
    assert valid_score["confidence"] >= 0.70
    assert valid_score["accepted"] is True
    assert valid_score["target"] == "module.py"


def test_rank_patch_candidates_deduplicates_and_sorts_by_confidence(git_repo):
    noisy = VALID_PATCH.replace("+VALUE = 'fixed'", "+VALUE = 'fixed'\n+EXTRA = 1")

    ranked = rank_patch_candidates(
        git_repo,
        [noisy, "not a diff\n", VALID_PATCH, VALID_PATCH],
        "AssertionError: VALUE",
    )

    assert [candidate["patch"] for candidate in ranked] == [VALID_PATCH, noisy]
    assert all(candidate["score"]["accepted"] for candidate in ranked)


def test_score_patch_includes_intent_signals_and_learned_weights(git_repo):
    failure = """FAILED tests/test_module.py::test_value
>       assert VALUE == 'fixed'
E       AssertionError: assert 'original' == 'fixed'
"""
    memory = [
        {
            "error_type": "AssertionError",
            "error_message": "assert original == fixed",
            "file": "tests/test_module.py",
            "patch": "old",
            "success": True,
            "timestamp": "2026-06-21T00:00:00+00:00",
            "cluster": "assertion",
            "intent_vector": ["value", "fixed"],
            "score": 0.82,
            "confidence": 0.82,
            "score_signals": {"intent": 0.90, "minimality": 0.10},
            "outcome": "passed",
        },
        {
            "error_type": "AssertionError",
            "error_message": "assert original == fixed",
            "file": "tests/test_module.py",
            "patch": "old",
            "success": False,
            "timestamp": "2026-06-21T00:01:00+00:00",
            "cluster": "assertion",
            "intent_vector": ["value", "fixed"],
            "score": 0.74,
            "confidence": 0.74,
            "score_signals": {"intent": 0.10, "minimality": 0.90},
            "outcome": "failed",
        },
    ]

    score = score_patch(git_repo, VALID_PATCH, failure, memory=memory)

    assert score["cluster"] == "assertion"
    assert "fixed" in score["intent"]["vector"]
    assert score["signals"]["intent"] > 0
    assert score["weights"]["intent"] > score["weights"]["minimality"]
    assert score["accepted"] is True


@pytest.mark.parametrize(
    "unsafe_patch",
    [
        """diff --git a/../outside.txt b/../outside.txt
--- a/../outside.txt
+++ b/../outside.txt
@@ -1 +1 @@
-outside
+damaged
""",
        """diff --git a/tracked.txt b/tracked.txt
similarity index 100%
rename from tracked.txt
rename to renamed.txt
""",
        """diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+new
""",
        """diff --git a/tracked.txt b/tracked.txt
deleted file mode 100644
--- a/tracked.txt
+++ /dev/null
@@ -1 +0,0 @@
-original
""",
        """diff --git a/tracked.txt b/tracked.txt
GIT binary patch
literal 1
Ac${Nk00000001f3
""",
        "not a unified diff\n",
    ],
)
def test_apply_patch_rejects_unsafe_or_malformed_input(git_repo, unsafe_patch):
    assert apply_patch(git_repo, unsafe_patch) is False
    assert (git_repo / "tracked.txt").read_text(encoding="utf-8") == "original\n"


def test_apply_patch_rejects_symlink_target(git_repo):
    target = git_repo / "real.txt"
    target.write_text("real\n", encoding="utf-8")
    link = git_repo / "link.txt"
    link.symlink_to(target)
    subprocess.run(["git", "-C", str(git_repo), "add", "real.txt", "link.txt"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "add link"], check=True)
    patch = """diff --git a/link.txt b/link.txt
--- a/link.txt
+++ b/link.txt
@@ -1 +1 @@
-real.txt
+other.txt
"""

    assert apply_patch(git_repo, patch) is False
    assert link.resolve() == target


def test_apply_patch_rejects_inapplicable_patch_without_changes(git_repo):
    patch = VALID_PATCH.replace("-VALUE = 'original'", "-VALUE = 'missing'")

    assert apply_patch(git_repo, patch) is False
    assert (git_repo / "module.py").read_text(encoding="utf-8") == "VALUE = 'original'\n"


def test_apply_patch_rejects_multiple_hunks(git_repo):
    (git_repo / "multi.py").write_text(
        "FIRST = 1\nMIDDLE = 2\nLAST = 3\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(git_repo), "add", "multi.py"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "add multi"], check=True)
    patch = """diff --git a/multi.py b/multi.py
--- a/multi.py
+++ b/multi.py
@@ -1 +1 @@
-FIRST = 1
+FIRST = 10
@@ -3 +3 @@
-LAST = 3
+LAST = 30
"""

    assert apply_patch(git_repo, patch) is False
    assert (git_repo / "multi.py").read_text(encoding="utf-8") == (
        "FIRST = 1\nMIDDLE = 2\nLAST = 3\n"
    )


def test_apply_patch_rejects_test_file_changes(git_repo):
    tests = git_repo / "tests"
    tests.mkdir()
    target = tests / "test_module.py"
    target.write_text("def test_value():\n    assert False\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "add", str(target)], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "add test"], check=True)
    patch = """diff --git a/tests/test_module.py b/tests/test_module.py
--- a/tests/test_module.py
+++ b/tests/test_module.py
@@ -1,2 +1,2 @@
 def test_value():
-    assert False
+    assert True
"""

    assert apply_patch(git_repo, patch) is False
    assert "assert False" in target.read_text(encoding="utf-8")


def test_apply_patch_rejects_syntax_error_without_changing_checkout(git_repo):
    patch = """diff --git a/module.py b/module.py
--- a/module.py
+++ b/module.py
@@ -1 +1 @@
-VALUE = 'original'
+VALUE =
"""

    assert apply_patch(git_repo, patch) is False
    assert (git_repo / "module.py").read_text(encoding="utf-8") == "VALUE = 'original'\n"


def test_apply_patch_rejects_new_unresolved_import(git_repo):
    patch = """diff --git a/module.py b/module.py
--- a/module.py
+++ b/module.py
@@ -1 +1,2 @@
+import openclaw_package_that_does_not_exist
 VALUE = 'original'
"""

    assert apply_patch(git_repo, patch) is False
    assert (git_repo / "module.py").read_text(encoding="utf-8") == "VALUE = 'original'\n"


def test_apply_patch_cleans_up_temporary_worktree(git_repo):
    before = subprocess.run(
        ["git", "-C", str(git_repo), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert apply_patch(git_repo, VALID_PATCH) is True

    after = subprocess.run(
        ["git", "-C", str(git_repo), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert after == before
