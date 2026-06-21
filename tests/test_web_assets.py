from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


def _read(name):
    return (WEB_ROOT / name).read_text(encoding="utf-8")


def test_index_has_semantic_repository_form_and_safety_warning():
    html = _read("index.html")

    assert '<form id="run-form"' in html
    assert '<label for="repo-path"' in html
    assert 'id="repo-path"' in html
    assert 'type="submit"' in html
    assert 'id="run-status"' in html
    assert 'aria-live="polite"' in html
    assert 'id="run-output"' in html
    assert "git reset --hard HEAD" in html
    assert "git clean -fd" in html
    assert "Local path or HTTPS Git URL" in html
    assert "https://github.com/owner/repository" in html


def test_index_references_local_assets_and_capability_notes():
    html = _read("index.html")

    assert 'href="/styles.css"' in html
    assert 'src="/app.js"' in html
    assert "Validated patches" in html
    assert "Five attempts" in html
    assert "Local memory" in html


def test_styles_define_whitish_responsive_accessible_visual_system():
    css = _read("styles.css")

    assert "--canvas: #f7f7f3" in css
    assert "--ink:" in css
    assert ":focus-visible" in css
    assert "@media (max-width: 700px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "overflow-wrap: anywhere" in css


def test_client_posts_json_and_renders_server_output_as_text():
    script = _read("app.js")

    assert 'fetch("/api/run"' in script
    assert '"Content-Type": "application/json"' in script
    assert "JSON.stringify({ repo })" in script
    assert "runButton.disabled = true" in script
    assert "runButton.disabled = false" in script
    assert "output.textContent" in script
    assert "innerHTML" not in script
    assert "status.focus()" in script
    assert "Enter a local path or HTTPS Git URL" in script
