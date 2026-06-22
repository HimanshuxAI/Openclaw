import importlib
import os
import re


DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
DEFAULT_TIMEOUT = 120.0
MAX_TOKENS = 16384


def _build_prompt(failure_text, code_context):
    return f"""Create one safe unified diff that fixes the pytest failure.

Rules:
- Return only a textual unified diff beginning with `diff --git`.
- Modify exactly one existing non-test Python file.
- Include exactly one diff hunk.
- Do not create, delete, rename, or copy files.
- Do not include binary changes, Markdown fences, or explanations.
- Keep the patch focused on the failure and supplied code.

PYTEST FAILURE:
{failure_text}

RELEVANT CODE:
{code_context or "No relevant code context was retrieved."}
"""


def _extract_unified_diff(response_text):
    if not isinstance(response_text, str):
        return ""
    fenced = re.search(
        r"```(?:diff)?\s*(diff --git .*?)\s*```",
        response_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        candidate = fenced.group(1)
    else:
        start = response_text.find("diff --git ")
        if start < 0:
            return ""
        candidate = response_text[start:]
    return candidate.strip() + "\n"


def _timeout_from_environment():
    try:
        value = float(os.environ.get("NVIDIA_API_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def generate_nvidia_patch(failure_text, code_context):
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not api_key:
        return ""

    try:
        openai = importlib.import_module("openai")
        client = openai.OpenAI(
            base_url=os.environ.get("NVIDIA_BASE_URL", DEFAULT_BASE_URL),
            api_key=api_key,
            timeout=_timeout_from_environment(),
        )
        stream = client.chat.completions.create(
            model=os.environ.get("NVIDIA_MODEL", DEFAULT_MODEL),
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise software repair tool. Output only unified diffs.",
                },
                {"role": "user", "content": _build_prompt(failure_text, code_context)},
            ],
            temperature=1,
            top_p=0.95,
            max_tokens=MAX_TOKENS,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": True,
                    "force_nonempty_content": True,
                },
                "reasoning_budget": MAX_TOKENS,
            },
            stream=True,
        )

        content = []
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            value = getattr(delta, "content", None)
            if value:
                content.append(value)
        return _extract_unified_diff("".join(content))
    except Exception:
        return ""
