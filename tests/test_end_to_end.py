import subprocess

from agent_loop import run_agent
from test_runner import run_tests


def test_agent_fixes_a_repository_and_retests_successfully(git_repo):
    (git_repo / "calculator.py").write_text(
        "def add(left, right):\n    return left - right\n", encoding="utf-8"
    )
    patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def add(left, right):
-    return left - right
+    return left + right
"""
    test_source = f'''from calculator import add


def test_add():
    if add(2, 3) != 5:
        print("OPENCLAW_PATCH_START")
        print({patch!r})
        print("OPENCLAW_PATCH_END")
    assert add(2, 3) == 5
'''
    (git_repo / "test_calculator.py").write_text(test_source, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(git_repo), "add", "calculator.py", "test_calculator.py"],
        check=True,
    )
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "broken calculator"], check=True)

    assert run_agent(git_repo) is True
    assert run_tests(git_repo)["passed"] is True
    assert "return left + right" in (git_repo / "calculator.py").read_text(encoding="utf-8")


def test_agent_fixes_two_defects_in_separate_micro_iterations(git_repo):
    (git_repo / "calculator.py").write_text(
        "def add(left, right):\n"
        "    return left - right\n\n"
        "def multiply(left, right):\n"
        "    return left + right\n",
        encoding="utf-8",
    )
    add_patch = (
        """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,3 +1,3 @@
 def add(left, right):
-    return left - right
+    return left + right
"""
        " \n"
    )
    multiply_patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -4,2 +4,2 @@
 def multiply(left, right):
-    return left + right
+    return left * right
"""
    test_source = f'''from calculator import add, multiply


def test_add():
    if add(2, 3) != 5:
        print("OPENCLAW_PATCH_START")
        print({add_patch!r})
        print("OPENCLAW_PATCH_END")
    assert add(2, 3) == 5


def test_multiply():
    if multiply(2, 3) != 6:
        print("OPENCLAW_PATCH_START")
        print({multiply_patch!r})
        print("OPENCLAW_PATCH_END")
    assert multiply(2, 3) == 6
'''
    (git_repo / "test_calculator.py").write_text(test_source, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(git_repo), "add", "calculator.py", "test_calculator.py"],
        check=True,
    )
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "two defects"], check=True)

    assert run_agent(git_repo) is True
    assert run_tests(git_repo)["passed"] is True
    source = (git_repo / "calculator.py").read_text(encoding="utf-8")
    assert "return left + right" in source
    assert "return left * right" in source
