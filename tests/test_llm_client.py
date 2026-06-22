import sys
from types import ModuleType, SimpleNamespace

import pytest

import llm_client


VALID_PATCH = """diff --git a/module.py b/module.py
--- a/module.py
+++ b/module.py
@@ -1 +1 @@
-old()
+fixed()
"""


@pytest.fixture(autouse=True)
def clean_nvidia_environment(monkeypatch):
    for name in (
        "NVIDIA_API_KEY",
        "NVIDIA_BASE_URL",
        "NVIDIA_MODEL",
        "NVIDIA_API_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)


def _install_fake_openai(monkeypatch, chunks=None, error=None):
    calls = {}

    class Completions:
        def create(self, **kwargs):
            calls["request"] = kwargs
            if error:
                raise error
            return chunks or []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.chat = SimpleNamespace(completions=Completions())

    module = ModuleType("openai")
    module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)
    return calls


def _chunk(content=None, reasoning=None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def test_generate_nvidia_patch_returns_empty_without_api_key():
    assert llm_client.generate_nvidia_patch("failure", "context") == ""


def test_generate_nvidia_patch_configures_stream_and_ignores_reasoning(
    monkeypatch,
):
    calls = _install_fake_openai(
        monkeypatch,
        chunks=[
            _chunk(reasoning="private reasoning"),
            _chunk(content=VALID_PATCH[:45]),
            _chunk(content=VALID_PATCH[45:]),
        ],
    )
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    result = llm_client.generate_nvidia_patch(
        "FAILED test_module.py::test_value\nAssertionError",
        "FILE: module.py (lines 1-1)\nold()",
    )

    assert result == VALID_PATCH
    assert calls["client"] == {
        "base_url": llm_client.DEFAULT_BASE_URL,
        "api_key": "test-key",
        "timeout": 120.0,
    }
    request = calls["request"]
    assert request["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert request["temperature"] == 1
    assert request["top_p"] == 0.95
    assert request["max_tokens"] == 16384
    assert request["stream"] is True
    assert request["extra_body"] == {
        "chat_template_kwargs": {
            "enable_thinking": True,
            "force_nonempty_content": True,
        },
        "reasoning_budget": 16384,
    }
    prompt = request["messages"][-1]["content"]
    assert "FAILED test_module.py" in prompt
    assert "FILE: module.py" in prompt
    assert "exactly one existing non-test Python file" in prompt
    assert "exactly one diff hunk" in prompt
    assert "private reasoning" not in result


def test_generate_nvidia_patch_uses_environment_overrides(monkeypatch):
    calls = _install_fake_openai(monkeypatch, chunks=[_chunk(content=VALID_PATCH)])
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("NVIDIA_BASE_URL", "http://127.0.0.1:9000/v1")
    monkeypatch.setenv("NVIDIA_MODEL", "local/model")
    monkeypatch.setenv("NVIDIA_API_TIMEOUT", "9.5")

    assert llm_client.generate_nvidia_patch("failure", "context") == VALID_PATCH
    assert calls["client"]["base_url"] == "http://127.0.0.1:9000/v1"
    assert calls["client"]["timeout"] == 9.5
    assert calls["request"]["model"] == "local/model"


def test_extract_unified_diff_accepts_fenced_and_plain_output():
    assert llm_client._extract_unified_diff(VALID_PATCH) == VALID_PATCH
    assert llm_client._extract_unified_diff(f"```diff\n{VALID_PATCH}```") == VALID_PATCH
    assert llm_client._extract_unified_diff("explanation only") == ""


def test_generate_nvidia_patch_returns_empty_when_sdk_is_missing(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(
        llm_client.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("missing")),
    )

    assert llm_client.generate_nvidia_patch("failure", "context") == ""


def test_generate_nvidia_patch_returns_empty_on_request_error(monkeypatch):
    _install_fake_openai(monkeypatch, error=RuntimeError("service unavailable"))
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    assert llm_client.generate_nvidia_patch("failure", "context") == ""
