import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re


FAILED_NODE_PATTERN = re.compile(r"(?:^|\n)FAILED\s+([^\s]+::[^\s]+)")


@dataclass
class FailureGraph:
    nodes: set = field(default_factory=set)
    edges: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(set)))
    reverse_edges: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(set)))
    function_names: dict = field(default_factory=lambda: defaultdict(set))
    failure_counts: dict = field(default_factory=lambda: defaultdict(int))
    change_counts: dict = field(default_factory=lambda: defaultdict(int))

    @classmethod
    def build(cls, repo_path):
        graph = cls()
        repo = Path(repo_path)
        module_files = {
            path.stem: path.relative_to(repo).as_posix()
            for path in repo.rglob("*.py")
            if ".git" not in path.parts
        }
        for path in sorted(repo.rglob("*.py")):
            if ".git" in path.parts:
                continue
            _index_file(graph, repo, path, module_files)
        graph._rebuild_reverse_edges()
        return graph

    def _add_edge(self, source, edge_type, target):
        self.nodes.add(source)
        self.nodes.add(target)
        self.edges[source][edge_type].add(target)

    def _rebuild_reverse_edges(self):
        self.reverse_edges.clear()
        for source, typed_edges in self.edges.items():
            for edge_type, targets in typed_edges.items():
                for target in targets:
                    self.reverse_edges[target][edge_type].add(source)

    def update_after_test_run(self, failure_output):
        failed = [f"test_case:{node}" for node in FAILED_NODE_PATTERN.findall(failure_output)]
        for node in failed:
            self.nodes.add(node)
            self.failure_counts[node] += 1
            for upstream in self._upstream_nodes(node):
                self.failure_counts[upstream] += 1
                if upstream.startswith("function:") and "::" in upstream:
                    file_path = upstream.removeprefix("function:").split("::", 1)[0]
                    self.failure_counts[f"file:{file_path}"] += 1
        for index, source in enumerate(failed):
            for target in failed[index + 1 :]:
                self._add_edge(source, "co-fails-with", target)
                self._add_edge(target, "co-fails-with", source)
        self._rebuild_reverse_edges()

    def update_after_change(self, change_set):
        for file_path in change_set.get("files", []):
            node = file_path if file_path.startswith("file:") else f"file:{file_path}"
            self.nodes.add(node)
            self.change_counts[node] += 1
        for function in change_set.get("functions", []):
            node = function if function.startswith("function:") else f"function:{function}"
            self.nodes.add(node)
            self.change_counts[node] += 1

    def get_related_nodes(self, node):
        related = set()
        for targets in self.edges.get(node, {}).values():
            related.update(targets)
        for sources in self.reverse_edges.get(node, {}).values():
            related.update(sources)
        return sorted(related)

    def dependents_of(self, node):
        seen = set()
        pending = [node]
        while pending:
            current = pending.pop()
            for sources in self.reverse_edges.get(current, {}).values():
                for source in sources:
                    if source in seen:
                        continue
                    seen.add(source)
                    pending.append(source)
        return seen

    def dependency_centrality(self, node):
        related = set(self.dependents_of(node))
        related.update(self.edges.get(node, {}).get("affects", set()))
        return len(related)

    def get_root_causes(self, failures):
        failed_nodes = [
            failure if failure.startswith("test_case:") else f"test_case:{failure}"
            for failure in failures
        ]
        candidates = defaultdict(float)
        for failed in failed_nodes:
            for candidate in self._upstream_nodes(failed):
                if candidate.startswith("function:") or candidate.startswith("file:"):
                    candidates[candidate] += 1.0
                    candidates[candidate] += min(
                        1.0, len(self.dependents_of(candidate)) / 5
                    )
        ranked = [
            {"node": node, "score": round(score, 6)}
            for node, score in candidates.items()
        ]
        ranked.sort(key=lambda item: (item["score"], item["node"]), reverse=True)
        return ranked

    def _upstream_nodes(self, node):
        seen = set()
        pending = [node]
        while pending:
            current = pending.pop()
            for edge_type in ("calls", "imports"):
                for target in self.edges.get(current, {}).get(edge_type, set()):
                    if target in seen:
                        continue
                    seen.add(target)
                    pending.append(target)
        return seen


def build_dependency_graph(repo_path):
    return FailureGraph.build(repo_path)


def _is_test_path(relative):
    parts = PurePosixPath(relative).parts
    return "tests" in parts or PurePosixPath(relative).name.startswith("test_")


def _index_file(graph, repo, path, module_files):
    relative = path.relative_to(repo).as_posix()
    file_node = f"file:{relative}"
    graph.nodes.add(file_node)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return

    imported_names = _imported_names(tree, module_files)
    for imported_file in sorted(set(imported_names.values())):
        graph._add_edge(file_node, "imports", f"file:{imported_file}")

    local_functions = {
        node.name: f"function:{relative}::{node.name}"
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for function_name, function_node in local_functions.items():
        graph.nodes.add(function_node)
        graph.function_names[function_name].add(function_node)
        graph._add_edge(file_node, "affects", function_node)

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        source = (
            f"test_case:{relative}::{node.name}"
            if _is_test_path(relative) and node.name.startswith("test_")
            else local_functions[node.name]
        )
        graph.nodes.add(source)
        if source.startswith("test_case:"):
            graph._add_edge(file_node, "affects", source)
        for call_name in _called_names(node):
            target = _resolve_call(call_name, local_functions, imported_names)
            if target:
                graph._add_edge(source, "calls", target)


def _imported_names(tree, module_files):
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in module_files:
                    imports[alias.asname or root] = module_files[root]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".", 1)[0]
            if root not in module_files:
                continue
            for alias in node.names:
                imports[alias.asname or alias.name] = module_files[root]
    return imports


def _called_names(function_node):
    names = []
    for node in ast.walk(function_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.append(node.func.attr)
    return names


def _resolve_call(call_name, local_functions, imported_names):
    if call_name in local_functions:
        return local_functions[call_name]
    imported_file = imported_names.get(call_name)
    if imported_file:
        return f"function:{imported_file}::{call_name}"
    return ""
