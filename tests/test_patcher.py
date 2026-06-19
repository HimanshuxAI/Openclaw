import subprocess

import pytest

import patcher
from patcher import apply_patch, generate_patch, mock_llm_fix


VALID_PATCH = """diff --git a/tracked.txt b/tracked.txt
--- a/tracked.txt
+++ b/tracked.txt
@@ -1 +1 @@
-original
+fixed
"""


def test_mock_llm_extracts_explicit_patch_block():
    failure = (
        "test failed\nOPENCLAW_PATCH_START\n"
        + VALID_PATCH
        + "OPENCLAW_PATCH_END\nother output"
    )

    assert mock_llm_fix(failure) == VALID_PATCH
    assert generate_patch(failure, "/unused") == VALID_PATCH


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


def test_apply_patch_modifies_existing_regular_file(git_repo):
    assert apply_patch(git_repo, VALID_PATCH) is True
    assert (git_repo / "tracked.txt").read_text(encoding="utf-8") == "fixed\n"


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
    patch = VALID_PATCH.replace("-original", "-missing")

    assert apply_patch(git_repo, patch) is False
    assert (git_repo / "tracked.txt").read_text(encoding="utf-8") == "original\n"
