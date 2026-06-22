from rag.context_builder import MAX_CONTEXT_TOKENS, build_context, estimate_tokens


def test_build_context_formats_headers_and_removes_duplicates():
    auth = {
        "file": "app/auth.py",
        "content": "def login():\n    return authenticate_user()\n",
        "lines": (10, 11),
        "scope": "login",
        "kind": "function",
    }
    billing = {
        "file": "app/billing.py",
        "content": "def charge():\n    return gateway.charge()\n",
        "lines": (20, 21),
        "scope": "charge",
        "kind": "function",
    }

    context = build_context([auth, auth.copy(), billing])

    assert context.count("FILE: app/auth.py (lines 10-11) SCOPE: login") == 1
    assert "FILE: app/billing.py (lines 20-21) SCOPE: charge" in context
    assert "def login():\n    return authenticate_user()" in context
    assert "\n\nFILE: app/billing.py" in context


def test_build_context_stays_below_two_thousand_tokens():
    chunks = [
        {
            "file": f"app/module_{number}.py",
            "content": "".join("x\n" for _ in range(300)),
            "lines": (1, 300),
            "scope": f"scope_{number}",
            "kind": "function",
        }
        for number in range(5)
    ]

    context = build_context(chunks)

    assert MAX_CONTEXT_TOKENS == 1800
    assert 0 < estimate_tokens(context) <= MAX_CONTEXT_TOKENS


def test_build_context_handles_empty_input():
    assert build_context([]) == ""


def test_build_context_does_not_include_a_single_oversized_dense_line():
    chunk = {
        "file": "app/generated.py",
        "content": "x=" * 5000,
        "lines": (1, 1),
        "scope": "generated",
        "kind": "function",
    }

    assert build_context([chunk]) == ""


def test_build_context_skips_oversized_scope_and_keeps_smaller_scope():
    oversized = {
        "file": "app/large.py",
        "content": "value = 'abcdefghij'\n" * 2000,
        "lines": (1, 2000),
        "scope": "large",
        "kind": "function",
    }
    small = {
        "file": "app/small.py",
        "content": "def small():\n    return 1\n",
        "lines": (1, 2),
        "scope": "small",
        "kind": "function",
    }

    context = build_context([oversized, small])

    assert "app/large.py" not in context
    assert small["content"].strip() in context


def test_build_context_may_trim_syntax_fallback_on_line_boundaries():
    syntax = {
        "file": "broken.py",
        "content": "x = 1\n" * 3000,
        "lines": (1, 3000),
        "scope": "<syntax>",
        "kind": "syntax",
    }

    context = build_context([syntax])

    assert context.startswith("FILE: broken.py (lines 1-")
    assert 0 < estimate_tokens(context) <= MAX_CONTEXT_TOKENS
