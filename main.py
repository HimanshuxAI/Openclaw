import argparse
from pathlib import Path

from agent_loop import run_agent
from repo_manager import clone_repo, load_local_repo, reset_repo
from utils import log


def build_parser():
    parser = argparse.ArgumentParser(description="Run the minimal test-fixing agent")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", type=Path, help="path to an existing local Git repository")
    source.add_argument("--url", help="Git repository URL or local clone source")
    parser.add_argument(
        "--clone-path",
        type=Path,
        default=Path("openclaw-target"),
        help="destination used with --url (default: ./openclaw-target)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.repo is not None:
            repo = load_local_repo(args.repo)
        else:
            repo = clone_repo(args.url, args.clone_path)
        log(f"Resetting repository before run: {repo}")
        reset_repo(repo)
        return 0 if run_agent(repo) else 1
    except (OSError, RuntimeError, ValueError) as error:
        log(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
