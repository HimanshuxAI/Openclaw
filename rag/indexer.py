import ast
from pathlib import Path


SYNTAX_WINDOW_LINES = 80
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "node_modules",
    "__pycache__",
}

_INDEX = []


def _is_source_file(path, repo):
    relative = path.relative_to(repo)
    return not any(part in IGNORED_DIRS for part in relative.parts[:-1])


def _unique(values):
    return tuple(dict.fromkeys(value for value in values if value))


def _calls(node):
    values = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            values.append((child.lineno, child.col_offset, child.func.id))
        elif isinstance(child.func, ast.Attribute):
            values.append((child.lineno, child.col_offset, child.func.attr))
    values.sort()
    return _unique(name for _, _, name in values)


def _imports(node):
    values = []
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            values.extend(alias.name for alias in child.names)
        elif isinstance(child, ast.ImportFrom):
            if child.module:
                values.append(child.module)
            values.extend(alias.name for alias in child.names if alias.name != "*")
    return _unique(values)


def _is_test_module(relative_path, tree):
    if "tests" in Path(relative_path).parts:
        return True
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            return True
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            return True
    return False


def _source_slice(relative_path, lines, node, scope, kind, is_test, start=None, end=None):
    decorators = getattr(node, "decorator_list", ())
    start_line = start or min(
        [node.lineno, *(decorator.lineno for decorator in decorators)]
    )
    end_line = end or node.end_lineno
    return {
        "file": relative_path,
        "content": "".join(lines[start_line - 1 : end_line]),
        "lines": (start_line, end_line),
        "scope": scope,
        "kind": kind,
        "imports": _imports(node),
        "calls": _calls(node),
        "is_test": is_test,
    }


def _module_groups(tree):
    module_types = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)
    groups = []
    current = []
    previous_end = None
    for node in tree.body:
        if not isinstance(node, module_types):
            if current:
                groups.append(current)
                current = []
            previous_end = None
            continue
        if current and node.lineno > previous_end + 1:
            groups.append(current)
            current = []
        current.append(node)
        previous_end = node.end_lineno
    if current:
        groups.append(current)
    return groups


def _ast_slices(relative_path, content, tree):
    lines = content.splitlines(keepends=True)
    is_test = _is_test_module(relative_path, tree)
    slices = []

    for group in _module_groups(tree):
        start_line = group[0].lineno
        end_line = group[-1].end_lineno
        module = ast.Module(body=group, type_ignores=[])
        slices.append(
            _source_slice(
                relative_path,
                lines,
                module,
                "<module>",
                "module",
                is_test,
                start=start_line,
                end=end_line,
            )
        )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            slices.append(
                _source_slice(relative_path, lines, node, node.name, "function", is_test)
            )
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    slices.append(
                        _source_slice(
                            relative_path,
                            lines,
                            child,
                            f"{node.name}.{child.name}",
                            "method",
                            is_test,
                        )
                    )

    slices.sort(key=lambda item: (item["lines"][0], item["lines"][1], item["scope"]))
    return slices


def _syntax_slices(relative_path, content):
    lines = content.splitlines(keepends=True)
    is_test = "tests" in Path(relative_path).parts or Path(relative_path).name.startswith(
        "test_"
    )
    slices = []
    for offset in range(0, len(lines), SYNTAX_WINDOW_LINES):
        selected = lines[offset : offset + SYNTAX_WINDOW_LINES]
        slices.append(
            {
                "file": relative_path,
                "content": "".join(selected),
                "lines": (offset + 1, offset + len(selected)),
                "scope": "<syntax>",
                "kind": "syntax",
                "imports": (),
                "calls": (),
                "is_test": is_test,
            }
        )
    return slices


def index_repo(repo_path):
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"Repository path is not a directory: {repo}")

    indexed = []
    for path in sorted(repo.rglob("*.py")):
        if not path.is_file() or path.is_symlink() or not _is_source_file(path, repo):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if not content.strip():
            continue
        relative = path.relative_to(repo).as_posix()
        try:
            tree = ast.parse(content, filename=relative)
        except SyntaxError:
            indexed.extend(_syntax_slices(relative, content))
        else:
            indexed.extend(_ast_slices(relative, content, tree))

    global _INDEX
    _INDEX = indexed
    return get_index()


def get_index():
    return [chunk.copy() for chunk in _INDEX]
