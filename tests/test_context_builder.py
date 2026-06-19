from rag.context_builder import MAX_CONTEXT_TOKENS, build_context


def test_build_context_formats_headers_and_removes_duplicates():
    auth = {
        "file": "app/auth.py",
        "content": "def login():\n    return authenticate_user()\n",
        "lines": (10, 11),
    }
    billing = {
        "file": "app/billing.py",
        "content": "def charge():\n    return gateway.charge()\n",
        "lines": (20, 21),
    }

    context = build_context([auth, auth.copy(), billing])

    assert context.count("FILE: app/auth.py (lines 10-11)") == 1
    assert "FILE: app/billing.py (lines 20-21)" in context
    assert "def login():\n    return authenticate_user()" in context
    assert "\n\nFILE: app/billing.py" in context


def test_build_context_stays_below_two_thousand_tokens():
    chunks = [
        {
            "file": f"app/module_{number}.py",
            "content": "".join(f"token_{number}_{line}\n" for line in range(600)),
            "lines": (1, 600),
        }
        for number in range(5)
    ]

    context = build_context(chunks)

    assert MAX_CONTEXT_TOKENS == 1800
    assert 0 < len(context.split()) <= MAX_CONTEXT_TOKENS
    assert len(context.split()) < 2000


def test_build_context_handles_empty_input():
    assert build_context([]) == ""


def test_build_context_does_not_include_a_single_oversized_dense_line():
    chunk = {
        "file": "app/generated.py",
        "content": "x=" * 5000,
        "lines": (1, 1),
    }

    assert build_context([chunk]) == ""
