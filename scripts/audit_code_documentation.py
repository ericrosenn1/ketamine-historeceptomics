"""Audit every publication documentation contract without changing science.

Stage: deterministic public-tree validation before commits, CI, and release.
Inputs: the explicit repository root and its code, configuration, and documents.
Outputs: deterministic Markdown and TSV reports covering every checked item.
Side effects: report writes occur only in write mode; check mode is read-only.
Invariants: the audit never imports scientific modules or edits numerical files.
Lane: public metadata/documentation QA for local, CI, and clean-clone validation.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import ast
import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import yaml
from cffconvert import Citation
from jsonschema.exceptions import ValidationError as CffSchemaError
from pybtex.database import parse_string
from pybtex.scanner import PybtexError
from pykwalify.errors import SchemaError as CffLegacySchemaError


REPORT_PATHS = {
    "audits/CODE_DOCUMENTATION_AUDIT.md",
    "audits/CODE_DOCUMENTATION_AUDIT.tsv",
}
SKIP_PARTS = {".git", ".venv", "__pycache__", "build", "dist", "local", "runs"}
PYTHON_ROOTS = ("src", "scripts", "tests")
MARKER_SUFFIXES = {
    ".cff",
    ".csv",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}
MARKER_SCANNERS = {
    "scripts/audit_code_documentation.py",
    "scripts/audit_repository.py",
}
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
TODO = re.compile(r"\b(?:TODO|FIXME)\b", re.IGNORECASE)
DEVELOPMENT_META = re.compile(
    r"(?:\b(?:ChatGPT|Claude|Codex conversation|OpenAI conversation|"
    r"system prompt|AI[- ]generated)\b|approved-private-commit|"
    r"github\.com/ericrosenn1/cardozo-ketamine-historeceptomics|"
    r"(?:manuscript|draft)[^\r\n]{0,120}\.(?:docx?|pdf))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Check:
    """One deterministic documentation-audit result."""

    category: str
    path: str
    item: str
    status: str
    detail: str


def parse_args() -> argparse.Namespace:
    """Parse the repository root and checked-report mode."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: parent of scripts/).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Fail if checked reports are stale.")
    mode.add_argument("--write", action="store_true", help="Write reports (default without --check).")
    return parser.parse_args()


def relative(root: Path, path: Path) -> str:
    """Return a forward-slash path relative to the audit root."""

    return path.relative_to(root).as_posix()


def python_files(root: Path) -> list[Path]:
    """Return first-party Python modules and executable metadata scripts."""

    paths: list[Path] = []
    for directory in PYTHON_ROOTS:
        candidate = root / directory
        if candidate.is_dir():
            paths.extend(candidate.rglob("*.py"))
    return sorted(
        path
        for path in paths
        if not any(part in SKIP_PARTS or part.endswith(".egg-info") for part in path.parts)
    )


def function_is_nontrivial(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Classify private helpers while allowing tiny wrappers and test helpers."""

    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    return len(body) >= 3


def module_doc_contract(docstring: str | None) -> tuple[bool, str]:
    """Check explicit stage, I/O, side-effect, invariant, and lane coverage."""

    if not docstring:
        return False, "Missing module docstring"
    required = {
        "stage or lane": r"\b(?:stage|lane)\b",
        "inputs": r"\binputs?\b",
        "outputs": r"\boutputs?\b",
        "side effects": r"\bside effects?\b",
        "invariants": r"\binvariants?\b",
    }
    missing = [label for label, pattern in required.items() if not re.search(pattern, docstring, re.IGNORECASE)]
    if len(docstring.split()) < 30:
        missing.append("substantive detail")
    return not missing, "Complete module contract" if not missing else "Missing: " + ", ".join(missing)


def audit_python(root: Path) -> list[Check]:
    """Check module and callable docstrings plus practical SPDX headers."""

    checks: list[Check] = []
    for path in python_files(root):
        rel = relative(root, path)
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError as exc:
            checks.append(Check("python_syntax", rel, "module", "FAIL", f"Syntax error at line {exc.lineno}"))
            continue
        module_doc = ast.get_docstring(tree, clean=False)
        production = rel.startswith(("src/", "scripts/"))
        complete, module_detail = module_doc_contract(module_doc)
        documented = complete if production else bool(module_doc and len(module_doc.strip()) >= 20)
        checks.append(
            Check(
                "module_docstring",
                rel,
                "module",
                "PASS" if documented else "FAIL",
                module_detail if production else ("Test purpose is documented" if documented else "Missing test-module descriptor"),
            )
        )
        checks.append(
            Check(
                "spdx",
                rel,
                "module",
                "PASS" if "SPDX-License-Identifier: MIT" in "\n".join(text.splitlines()[:150]) else "FAIL",
                "MIT SPDX header present" if "SPDX-License-Identifier: MIT" in "\n".join(text.splitlines()[:150]) else "Missing MIT SPDX header",
            )
        )
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                required = not node.name.startswith("_") or len(node.body) >= 3
                if required:
                    present = bool(ast.get_docstring(node, clean=False))
                    checks.append(
                        Check(
                            "class_docstring",
                            rel,
                            f"{node.name}:{node.lineno}",
                            "PASS" if present else "FAIL",
                            "Documented" if present else "Missing class docstring",
                        )
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                in_test = rel.startswith("tests/")
                is_nested = isinstance(parents.get(node), (ast.FunctionDef, ast.AsyncFunctionDef))
                public = not node.name.startswith("_")
                required = not in_test and (public or function_is_nontrivial(node))
                # Tiny nested stage wrappers and self-explanatory test helpers are
                # explicitly allowed by the publication brief.
                if required and not (is_nested and not function_is_nontrivial(node)):
                    present = bool(ast.get_docstring(node, clean=False))
                    checks.append(
                        Check(
                            "function_docstring",
                            rel,
                            f"{node.name}:{node.lineno}",
                            "PASS" if present else "FAIL",
                            "Documented" if present else "Missing function or method docstring",
                        )
                    )
    return checks


def audit_powershell(root: Path) -> list[Check]:
    """Check public launchers for help, examples, strict failure, and SPDX."""

    checks: list[Check] = []
    for path in sorted((root / "launchers").glob("*.ps1")):
        rel = relative(root, path)
        text = path.read_text(encoding="utf-8")
        required = [".SYNOPSIS", ".DESCRIPTION", ".EXAMPLE"]
        for marker in required:
            checks.append(
                Check(
                    "powershell_help",
                    rel,
                    marker,
                    "PASS" if marker in text else "FAIL",
                    "Present" if marker in text else "Missing comment-based help section",
                )
            )
        checks.append(
            Check(
                "spdx",
                rel,
                "script",
                "PASS" if "SPDX-License-Identifier: MIT" in "\n".join(text.splitlines()[:80]) else "FAIL",
                "MIT SPDX header present" if "SPDX-License-Identifier: MIT" in "\n".join(text.splitlines()[:80]) else "Missing MIT SPDX header",
            )
        )
        checks.append(
            Check(
                "powershell_failure_contract",
                rel,
                "ErrorActionPreference",
                "PASS" if "$ErrorActionPreference = 'Stop'" in text or "$LASTEXITCODE" in text else "FAIL",
                "Native/script failures propagate" if "$ErrorActionPreference = 'Stop'" in text or "$LASTEXITCODE" in text else "Missing explicit failure-propagation policy",
            )
        )
    return checks


def descriptor_paths(root: Path) -> list[Path]:
    """Return configuration and workflow files requiring top-level context."""

    candidates = [root / "pyproject.toml", root / "environment.yml", root / "workflow" / "Snakefile"]
    candidates.extend((root / "configs").glob("*.yaml"))
    candidates.extend((root / "configs").glob("*.yml"))
    candidates.extend((root / ".github" / "workflows").glob("*.yml"))
    candidates.extend((root / ".github" / "workflows").glob("*.yaml"))
    candidates.extend([root / ".github" / "dependabot.yml", root / ".github" / "codeql" / "codeql-config.yml"])
    return sorted(set(path for path in candidates if path.is_file()))


def audit_descriptors(root: Path) -> list[Check]:
    """Check configuration/workflow files for purpose and consumer context."""

    checks: list[Check] = []
    for path in descriptor_paths(root):
        rel = relative(root, path)
        preamble = "\n".join(path.read_text(encoding="utf-8").splitlines()[:20]).lower()
        has_purpose = (
            "purpose:" in preamble
            or "scientific meaning:" in preamble
            or "public package and test configuration" in preamble
            or "reproducibility environment" in preamble
            or "reference_only" in preamble
        )
        has_consumer = (
            "consumer:" in preamble
            or "consumers:" in preamble
            or "lane:" in preamble
            or "supported release execution" in preamble
            or "scientific parameters" in preamble
            or "installs software" in preamble
        )
        checks.extend(
            [
                Check("configuration_descriptor", rel, "purpose", "PASS" if has_purpose else "FAIL", "Purpose documented" if has_purpose else "Missing top-level purpose descriptor"),
                Check("configuration_descriptor", rel, "consumer", "PASS" if has_consumer else "FAIL", "Consumer/change impact documented" if has_consumer else "Missing consumer or change-impact descriptor"),
            ]
        )
        if rel.startswith("configs/"):
            required_config_topics = {
                "units": "units:" in preamble,
                "field constraints": "field/value constraints:" in preamble,
                "scientific-change impact": "scientific-change impact:" in preamble,
                "modification caution": "modification caution:" in preamble,
            }
            checks.extend(
                Check(
                    "configuration_descriptor",
                    rel,
                    topic,
                    "PASS" if present else "FAIL",
                    "Documented" if present else f"Missing top-level {topic} descriptor",
                )
                for topic, present in required_config_topics.items()
            )
    return checks


def audit_test_descriptors(root: Path) -> list[Check]:
    """Check each nontrivial test module for a contract-level module docstring."""

    checks: list[Check] = []
    for path in sorted((root / "tests").glob("test_*.py")):
        rel = relative(root, path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        present = bool(ast.get_docstring(tree, clean=False))
        checks.append(Check("test_descriptor", rel, "module", "PASS" if present else "FAIL", "Protected contract documented" if present else "Missing test contract module docstring"))
    return checks


def audit_markers(root: Path) -> list[Check]:
    """Reject unresolved work markers and unexplained development metadata."""

    checks: list[Check] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in MARKER_SUFFIXES:
            continue
        rel = relative(root, path)
        if rel in REPORT_PATHS or rel in MARKER_SCANNERS or any(
            part in SKIP_PARTS or part.endswith(".egg-info") for part in path.parts
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for category, pattern in (("unresolved_marker", TODO), ("development_metadata", DEVELOPMENT_META)):
            hits = [line for line, value in enumerate(text.splitlines(), 1) if pattern.search(value)]
            checks.append(
                Check(
                    category,
                    rel,
                    "lines" if hits else "file",
                    "FAIL" if hits else "PASS",
                    f"Found at line(s) {','.join(map(str, hits))}" if hits else "No findings",
                )
            )
    return checks


def normalize_link_target(raw: str) -> str:
    """Strip an optional Markdown title and angle-bracket path wrapper."""

    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    if " \"" in target:
        target = target.split(" \"", 1)[0]
    return target


def audit_links(root: Path) -> list[Check]:
    """Check local Markdown links while leaving remote endpoints to endpoint QA."""

    checks: list[Check] = []
    for path in sorted(root.rglob("*.md")):
        rel = relative(root, path)
        if rel in REPORT_PATHS or any(
            part in SKIP_PARTS or part.endswith(".egg-info") for part in path.parts
        ):
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            for match in LINK.finditer(line):
                raw = normalize_link_target(match.group(1))
                if not raw or raw.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                target_text = unquote(raw.split("#", 1)[0].split("?", 1)[0])
                target = (root / target_text.lstrip("/")) if target_text.startswith("/") else (path.parent / target_text)
                present = target.exists()
                checks.append(Check("markdown_link", rel, f"{raw}:{number}", "PASS" if present else "FAIL", "Target exists" if present else "Missing local target"))
    return checks


def valid_orcid(value: object) -> bool:
    """Validate the canonical HTTPS form and ISO 7064 checksum of an ORCID."""

    if not isinstance(value, str) or not re.fullmatch(
        r"https://orcid\.org/\d{4}-\d{4}-\d{4}-\d{3}[\dX]", value
    ):
        return False
    compact = value.rsplit("/", 1)[1].replace("-", "")
    total = 0
    for character in compact[:15]:
        total = (total + int(character)) * 2
    check = (12 - total % 11) % 11
    expected = "X" if check == 10 else str(check)
    return compact[-1] == expected


def audit_citations(root: Path) -> list[Check]:
    """Validate CFF 1.2 schema/ORCID contracts and parse the full BibTeX file."""

    checks: list[Check] = []
    cff_path = root / "CITATION.cff"
    try:
        cff_text = cff_path.read_text(encoding="utf-8")
        cff = yaml.safe_load(cff_text)
        Citation(cff_text, src="CITATION.cff").validate()
        required = {"cff-version", "title", "authors", "version", "date-released", "repository-code", "license"}
        missing = sorted(required - set(cff or {}))
        authors = cff.get("authors", []) if isinstance(cff, dict) else []
        author = authors[0] if len(authors) == 1 and isinstance(authors[0], dict) else {}
        author_valid = (
            author.get("family-names") == "Rosenn"
            and author.get("given-names") == "Eric"
            and valid_orcid(author.get("orcid"))
            and "email" not in author
        )
        valid = (
            isinstance(cff, dict)
            and not missing
            and cff.get("cff-version") == "1.2.0"
            and cff.get("license") == "MIT"
            and cff.get("version") == "0.1.1"
            and author_valid
        )
        detail = (
            "CFF 1.2 schema, v0.1.1 fields, single software author, and ORCID checksum valid"
            if valid
            else "Missing or invalid release/author fields: " + ", ".join(missing)
        )
    except (OSError, UnicodeError, yaml.YAMLError, CffSchemaError, CffLegacySchemaError, ValueError) as exc:
        valid, detail = False, f"CFF parse failure: {type(exc).__name__}"
    checks.append(Check("citation_cff", "CITATION.cff", "document", "PASS" if valid else "FAIL", detail))

    bib_path = root / "CITATION.bib"
    try:
        bib = bib_path.read_text(encoding="utf-8")
        keys = re.findall(r"(?m)^@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,", bib)
        parsed = parse_string(bib, "bibtex")
        valid_bib = len(keys) >= 5 and len(keys) == len(set(keys)) == len(parsed.entries)
        detail_bib = (
            f"{len(parsed.entries)} unique entries parsed by Pybtex"
            if valid_bib
            else "Malformed, duplicate, or insufficient BibTeX entries"
        )
    except (OSError, UnicodeError, PybtexError, ValueError) as exc:
        valid_bib, detail_bib = False, f"BibTeX parse failure: {type(exc).__name__}"
    checks.append(Check("citation_bibtex", "CITATION.bib", "document", "PASS" if valid_bib else "FAIL", detail_bib))
    return checks


def render_tsv(checks: list[Check]) -> str:
    """Render every check as a deterministic tab-separated audit table."""

    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(["category", "path", "item", "status", "detail"])
    for check in checks:
        writer.writerow([check.category, check.path, check.item, check.status, check.detail])
    return stream.getvalue()


def render_markdown(checks: list[Check]) -> str:
    """Summarize audit categories and list only actionable failures."""

    failures = [check for check in checks if check.status == "FAIL"]
    category_counts: dict[str, tuple[int, int]] = {}
    for check in checks:
        passed, total = category_counts.get(check.category, (0, 0))
        category_counts[check.category] = (passed + (check.status == "PASS"), total + 1)
    lines = [
        "# Code documentation audit",
        "",
        f"Overall status: `{'PASS' if not failures else 'FAIL'}`",
        "",
        f"- Checks evaluated: `{len(checks)}`",
        f"- Passing checks: `{len(checks) - len(failures)}`",
        f"- Failing checks: `{len(failures)}`",
        "",
        "## Category summary",
        "",
        "| Category | Passed | Total |",
        "|---|---:|---:|",
    ]
    lines.extend(f"| `{category}` | {passed} | {total} |" for category, (passed, total) in sorted(category_counts.items()))
    lines.extend(["", "Tiny wrappers, self-explanatory test helpers, and unchanged third-party artifacts are permitted exceptions. All production modules and nontrivial callables remain in scope.", ""])
    if failures:
        lines.extend(["## Actionable failures", ""])
        lines.extend(f"- `{item.category}`: `{item.path}` / `{item.item}` — {item.detail}" for item in failures)
        lines.append("")
    lines.extend(["Machine-readable evidence is in `audits/CODE_DOCUMENTATION_AUDIT.tsv`.", ""])
    return "\n".join(lines)


def write_or_check(root: Path, outputs: dict[str, str], check: bool) -> None:
    """Write LF-normalized reports or verify byte-identical checked reports."""

    stale: list[str] = []
    for rel, content in outputs.items():
        path = root / rel
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                stale.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        raise SystemExit("Documentation audit reports are stale: " + ", ".join(stale))


def main() -> None:
    """Run all documentation checks and fail after producing useful evidence."""

    args = parse_args()
    root = args.root.resolve()
    if not (root / "pyproject.toml").is_file():
        raise SystemExit(f"Not a repository root: {root}")
    checks = sorted(
        [
            *audit_python(root),
            *audit_powershell(root),
            *audit_descriptors(root),
            *audit_test_descriptors(root),
            *audit_markers(root),
            *audit_links(root),
            *audit_citations(root),
        ],
        key=lambda item: (item.category, item.path, item.item),
    )
    failures = [check for check in checks if check.status == "FAIL"]
    outputs = {
        "audits/CODE_DOCUMENTATION_AUDIT.md": render_markdown(checks),
        "audits/CODE_DOCUMENTATION_AUDIT.tsv": render_tsv(checks),
    }
    write_or_check(root, outputs, args.check)
    print(
        f"Code documentation audit: {'PASS' if not failures else 'FAIL'}; "
        f"{len(checks)} checks; {len(failures)} failures"
    )
    if failures:
        raise SystemExit("Documentation audit failed; inspect audits/CODE_DOCUMENTATION_AUDIT.md")


if __name__ == "__main__":
    main()
