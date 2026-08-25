"""Record and compare documentation-insensitive Python syntax trees.

This metadata tool protects the publication documentation pass.  It hashes a
normalized abstract syntax tree for every production Python file after removing
module, class, and function docstrings.  Comments and source locations are not
represented by :mod:`ast`, so an unchanged hash demonstrates that executable
syntax was preserved.

Inputs are a repository root and, for comparison, a previously generated JSON
baseline.  Outputs are deterministic JSON and optional TSV reports.  The tool
does not import project modules or execute scientific code.  New or removed
files are reported explicitly and never treated as equivalent silently.

SPDX-License-Identifier: MIT

Publication contract
--------------------
Purpose: Prove whether publication edits changed executable Python syntax.
Stage/lane: Release-metadata QA; it never executes a scientific analysis lane.
Inputs: A repository root, source globs, and a JSON AST baseline.
Outputs: A deterministic baseline JSON, optional comparison TSV, console counts,
and a nonzero comparison status when any file is not equivalent.
Side effects: Reads source text and writes only requested QA evidence; it neither
imports project modules nor modifies scientific inputs or outputs.
Invariants: Docstrings/comments/locations are ignored, paths are stably ordered,
and new, removed, or executable-changed files are always reported.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


DEFAULT_GLOBS = ("src/**/*.py", "scripts/*.py")
SELF_PATH = "scripts/compare_executable_ast.py"


class DocstringStripper(ast.NodeTransformer):
    """Remove leading docstring expression nodes from executable ASTs."""

    @staticmethod
    def _without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
        """Return *body* without its leading string-expression docstring."""

        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            return body[1:]
        return body

    def visit_Module(self, node: ast.Module) -> ast.AST:
        """Strip a module docstring and recurse into its statements."""

        node.body = self._without_docstring(node.body)
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        """Strip a class docstring and recurse into methods and nested classes."""

        node.body = self._without_docstring(node.body)
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        """Strip a synchronous function docstring and recurse into its body."""

        node.body = self._without_docstring(node.body)
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        """Strip an asynchronous function docstring and recurse into its body."""

        node.body = self._without_docstring(node.body)
        return self.generic_visit(node)


def normalized_ast(source: str, filename: str) -> str:
    """Return a stable, documentation-insensitive AST representation.

    Parameters
    ----------
    source:
        UTF-8 Python source text.
    filename:
        Repository-relative path used only in parse errors.

    Returns
    -------
    str
        ``ast.dump`` output without location attributes or docstring nodes.
    """

    tree = ast.parse(source, filename=filename, type_comments=True)
    stripped = DocstringStripper().visit(tree)
    ast.fix_missing_locations(stripped)
    return ast.dump(stripped, annotate_fields=True, include_attributes=False)


def production_paths(root: Path, globs: Iterable[str]) -> list[Path]:
    """Enumerate unique production Python paths in deterministic order."""

    paths = {path for pattern in globs for path in root.glob(pattern) if path.is_file()}
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def build_snapshot(root: Path, globs: Iterable[str], exclude_self: bool) -> dict[str, Any]:
    """Build normalized AST hashes and representations for a repository tree."""

    records: list[dict[str, Any]] = []
    for path in production_paths(root, globs):
        relative = path.relative_to(root).as_posix()
        if exclude_self and relative == SELF_PATH:
            continue
        normalized = normalized_ast(path.read_text(encoding="utf-8-sig"), relative)
        records.append(
            {
                "path": relative,
                "normalized_ast_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper(),
                "normalized_ast": normalized,
            }
        )
    return {
        "schema_version": 1,
        "normalization": "Python ast.dump without attributes after removing leading module/class/function docstrings",
        "files": records,
    }


def compare_snapshots(baseline: dict[str, Any], current: dict[str, Any]) -> list[dict[str, str]]:
    """Compare two snapshots and return one status row per unioned path."""

    before = {record["path"]: record for record in baseline["files"]}
    after = {record["path"]: record for record in current["files"]}
    rows: list[dict[str, str]] = []
    for path in sorted(before.keys() | after.keys()):
        old = before.get(path, {})
        new = after.get(path, {})
        if not old:
            status = "NEW_FILE"
        elif not new:
            status = "REMOVED_FILE"
        elif old["normalized_ast_sha256"] == new["normalized_ast_sha256"]:
            status = "EQUIVALENT"
        else:
            status = "EXECUTABLE_AST_CHANGED"
        rows.append(
            {
                "path": path,
                "status": status,
                "baseline_sha256": old.get("normalized_ast_sha256", ""),
                "current_sha256": new.get("normalized_ast_sha256", ""),
            }
        )
    return rows


def write_json(path: Path, value: Any) -> None:
    """Write deterministic UTF-8 JSON with LF line endings."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write comparison rows as deterministic UTF-8 TSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["path", "status", "baseline_sha256", "current_sha256"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    """Parse the ``baseline`` and ``compare`` command-line interfaces."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("baseline", "compare"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--include-self", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Create a baseline or compare the current tree with an existing baseline."""

    args = parse_args()
    root = args.root.resolve()
    snapshot = build_snapshot(root, DEFAULT_GLOBS, exclude_self=not args.include_self)
    if args.command == "baseline":
        write_json(args.baseline, snapshot)
        print(f"AST_BASELINE_FILES={len(snapshot['files'])}")
        print(f"AST_BASELINE={args.baseline.resolve()}")
        return 0

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    rows = compare_snapshots(baseline, snapshot)
    if args.report:
        write_tsv(args.report, rows)
    counts = {status: sum(row["status"] == status for row in rows) for status in sorted({row["status"] for row in rows})}
    print("AST_COMPARISON=" + ",".join(f"{key}:{value}" for key, value in counts.items()))
    failures = [row for row in rows if row["status"] != "EQUIVALENT"]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
