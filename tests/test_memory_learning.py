import subprocess

import agent_loop
from memory.store import load_memory
from repo_manager import reset_repo
from test_runner import run_tests


def test_second_run_reuses_learned_fix_when_generation_is_unavailable(
    git_repo, monkeypatch
):
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

    assert agent_loop.run_agent(git_repo) is True
    assert load_memory()[-1]["success"] is True

    reset_repo(git_repo)
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch",
        lambda failure, path: (_ for _ in ()).throw(AssertionError("generator called")),
    )

    assert agent_loop.run_agent(git_repo) is True
    assert run_tests(git_repo)["passed"] is True
