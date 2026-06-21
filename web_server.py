import argparse
from contextlib import redirect_stdout
import hashlib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from io import StringIO
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from agent_loop import run_agent
from repo_manager import clone_repo, load_local_repo, reset_repo
from utils import log


WEB_ROOT = Path(__file__).resolve().parent / "web"
MAX_REQUEST_BYTES = 64 * 1024


def _clone_destination(url):
    parsed = urlparse(url)
    repo_name = Path(parsed.path.rstrip("/")).name
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    repo_name = re.sub(r"[^A-Za-z0-9._-]+", "-", repo_name).strip("-")
    repo_name = repo_name or "repository"

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    clone_root = Path(
        os.environ.get("OPENCLAW_CLONE_ROOT", Path.home() / ".openclaw" / "repos")
    ).expanduser().resolve()
    return clone_root / f"{repo_name}-{digest}"


def _resolve_repository(source):
    parsed = urlparse(source)
    if parsed.scheme:
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Only HTTPS Git URLs are supported")
        if parsed.username or parsed.password:
            raise ValueError("Git URLs with embedded credentials are not allowed")

        destination = _clone_destination(source)
        if destination.exists():
            return load_local_repo(destination)
        return clone_repo(source, destination)

    return load_local_repo(source)


def execute_agent(repo_path):
    if not isinstance(repo_path, str) or not repo_path.strip():
        raise ValueError("Repository path is required")

    output = StringIO()
    with redirect_stdout(output):
        repo = _resolve_repository(repo_path.strip())
        log(f"Resetting repository before run: {repo}")
        reset_repo(repo)
        success = run_agent(repo)
    return {
        "success": success,
        "repo": str(repo),
        "output": output.getvalue(),
    }


class OpenClawHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/run":
            self._send_json(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "Invalid content length"})
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send_json(400, {"error": "Request body must be between 1 byte and 64 KiB"})
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(415, {"error": "Content-Type must be application/json"})
            return

        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            result = execute_agent(payload.get("repo"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Request body must be valid JSON"})
            return
        except (OSError, RuntimeError, ValueError) as error:
            self._send_json(400, {"error": str(error)})
            return
        self._send_json(200, result)


def serve(host="127.0.0.1", port=8000):
    server = HTTPServer((host, port), OpenClawHandler)
    print(f"OpenClaw UI: http://{host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the local OpenClaw web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
