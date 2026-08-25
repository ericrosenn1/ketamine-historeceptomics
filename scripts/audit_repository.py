"""Audit the publishable tree for accidental exposure and unsafe content.

Stage: public-tree preflight and CI validation before release packaging.
Inputs: an explicit repository root, its public files, and audit mode arguments.
Outputs: deterministic public exposure Markdown and TSV findings reports.
Side effects: writes only those reports unless ``--check`` requests read-only QA.
Invariants: never emit matched secret values or inspect excluded runtime trees.
Lane: public metadata/security audit; no scientific computation or input access.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path


SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "clean_clone_validation",
    "dist",
    "local",
    "release_artifacts",
    "runs",
}
TEXT_SUFFIXES = {
    ".bib",
    ".cff",
    ".csv",
    ".gitattributes",
    ".gitignore",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".svg",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {".gitattributes", ".gitignore", "LICENSE", "Snakefile"}
PROHIBITED_SUFFIXES = {
    ".7z",
    ".db",
    ".doc",
    ".docx",
    ".duckdb",
    ".env",
    ".key",
    ".mbox",
    ".msg",
    ".pem",
    ".pfx",
    ".pst",
    ".sqlite",
    ".sqlite3",
    ".zip",
}
ALLOWED_BINARY_PATHS = {
    "results/reference/figure4/final/FINAL_FIGURE4_CARDOZO_BRIGHT_RIGHTLEGEND.pdf",
    "results/reference/figure4/final/FINAL_FIGURE4_CARDOZO_BRIGHT_RIGHTLEGEND_600dpi.png",
}
SELF_REFERENTIAL_REPORTS = {
    "MANIFEST.tsv",
    "PUBLIC_RELEASE_MANIFEST.tsv",
    "SHA256SUMS.txt",
    "audits/PUBLIC_EXPOSURE_AUDIT.md",
    "audits/PUBLIC_EXPOSURE_FINDINGS.tsv",
    "audits/REPOSITORY_CONTENT_AUDIT.md",
}
SCANNER_IMPLEMENTATIONS = {
    "scripts/audit_code_documentation.py",
    "scripts/audit_repository.py",
}
SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"
    ),
    "openai_token": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private_key": re.compile(
        r"-----BEGIN (?:DSA |EC |OPENSSH |PGP |RSA )?PRIVATE KEY-----"
    ),
}
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
NAMED_USER_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\s]+|"
    r"/(?:Users|home)/[^/\s]+)",
    re.IGNORECASE,
)
WORKSTATION_PATH = re.compile(
    r"(?:\b(?:OneDrive|Downloads|AppData|Temp)\\|(?<![:\w])/tmp/)",
    re.IGNORECASE,
)
PHONE_NUMBER = re.compile(
    r"(?<!\d)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)"
)
PERSONAL_ADDRESS = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.' -]{2,50}\s"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way)\b",
    re.IGNORECASE,
)
CONNECTION_STRING = re.compile(
    r"(?:\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?)://|"
    r"\b(?:Server|Data Source)\s*=\s*[^;\r\n]+;[^\r\n]*(?:Password|Pwd)\s*=)",
    re.IGNORECASE,
)
PRIVATE_USERNAME = re.compile(
    r"\b(?:user(?:name)?|uid)\s*[:=]\s*['\"]?[A-Za-z][A-Za-z0-9._-]{2,}['\"]?",
    re.IGNORECASE,
)
DEVELOPMENT_METADATA = re.compile(
    r"(?:\b(?:ChatGPT|Claude|Codex conversation|OpenAI conversation|system prompt)\b|"
    r"approved-private-commit|"
    r"github\.com/ericrosenn1/cardozo-ketamine-historeceptomics|"
    r"(?:manuscript|draft)[^\r\n]{0,120}\.(?:docx?|pdf))",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class Finding:
    """A value-free publication-boundary finding."""

    category: str
    severity: str
    path: str
    line: int
    status: str
    note: str


def parse_args() -> argparse.Namespace:
    """Parse the repository root and deterministic report mode."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to audit (default: parent of scripts/).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Fail if checked reports differ from freshly generated content.",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="Write checked reports (the default when --check is absent).",
    )
    return parser.parse_args()


def included(root: Path, path: Path) -> bool:
    """Return whether *path* belongs to the publishable audit surface."""

    rel = path.relative_to(root)
    return (
        path.is_file()
        and rel.as_posix() not in SELF_REFERENTIAL_REPORTS
        and not any(part in SKIP_PARTS or part.endswith(".egg-info") for part in rel.parts)
    )


def line_numbers(pattern: re.Pattern[str], text: str) -> list[int]:
    """Return one-based line numbers containing at least one pattern match."""

    return [number for number, line in enumerate(text.splitlines(), 1) if pattern.search(line)]


def scan(root: Path) -> tuple[list[Path], list[Finding], int]:
    """Scan the tree and return files, value-free findings, and total bytes."""

    files = sorted(path for path in root.rglob("*") if included(root, path))
    findings: list[Finding] = []
    total_bytes = 0
    for path in files:
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        total_bytes += size
        suffix = path.suffix.lower()
        is_text = suffix in TEXT_SUFFIXES or path.name in TEXT_FILENAMES
        if suffix in PROHIBITED_SUFFIXES or path.name.lower().startswith(".env"):
            findings.append(
                Finding(
                    "prohibited_file_type",
                    "ERROR",
                    rel,
                    0,
                    "OPEN",
                    "Non-publication file type",
                )
            )
        if size >= 50 * 1024 * 1024:
            findings.append(
                Finding("large_file", "ERROR", rel, 0, "OPEN", "File is at least 50 MiB")
            )
        if not is_text and rel not in ALLOWED_BINARY_PATHS and suffix not in PROHIBITED_SUFFIXES:
            findings.append(
                Finding(
                    "unapproved_binary_or_unknown_type",
                    "ERROR",
                    rel,
                    0,
                    "OPEN",
                    "File is not text and is absent from the cleared binary allowlist",
                )
            )
        if not is_text:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            findings.append(
                Finding(
                    "text_decode",
                    "ERROR",
                    rel,
                    0,
                    "OPEN",
                    "Declared text file is not strict UTF-8",
                )
            )
            continue

        # The scanner source necessarily contains signature expressions; its own
        # patterns are excluded from content matching, but not from file/type QA.
        if rel in SCANNER_IMPLEMENTATIONS:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            for line in line_numbers(pattern, text):
                findings.append(
                    Finding(name, "ERROR", rel, line, "OPEN", "Potential credential signature")
                )
        for line in line_numbers(EMAIL, text):
            findings.append(
                Finding(
                    "email_address",
                    "ERROR",
                    rel,
                    line,
                    "OPEN",
                    "Email address is outside the public release policy",
                )
            )
        for line in line_numbers(NAMED_USER_PATH, text):
            findings.append(
                Finding(
                    "named_user_path",
                    "ERROR",
                    rel,
                    line,
                    "OPEN",
                    "Local user path exposes workstation provenance",
                )
            )
        for category, pattern, note in (
            ("workstation_path", WORKSTATION_PATH, "OneDrive, Downloads, AppData, or temporary path marker"),
            ("phone_number", PHONE_NUMBER, "Potential personal phone number"),
            ("personal_address", PERSONAL_ADDRESS, "Potential personal street address"),
            ("connection_string", CONNECTION_STRING, "Potential database or broker connection string"),
            ("private_username", PRIVATE_USERNAME, "Potential embedded account username"),
        ):
            for line in line_numbers(pattern, text):
                findings.append(Finding(category, "ERROR", rel, line, "OPEN", note))
        for line in line_numbers(DEVELOPMENT_METADATA, text):
            findings.append(
                Finding(
                    "development_metadata",
                    "ERROR",
                    rel,
                    line,
                    "OPEN",
                    "Development-session metadata is not release content",
                )
            )
    return files, sorted(set(findings)), total_bytes


def render_findings(findings: list[Finding]) -> str:
    """Render the machine-readable findings table without sensitive values."""

    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(["category", "severity", "path", "line", "status", "note"])
    for item in findings:
        writer.writerow(
            [item.category, item.severity, item.path, item.line, item.status, item.note]
        )
    return stream.getvalue()


def render_report(files: list[Path], findings: list[Finding], total_bytes: int) -> str:
    """Render the human-readable public-exposure audit."""

    categories: dict[str, int] = {}
    for finding in findings:
        categories[finding.category] = categories.get(finding.category, 0) + 1
    status = "PASS" if not findings else "FAIL"
    lines = [
        "# Public exposure audit",
        "",
        f"Overall status: `{status}`",
        "",
        f"- Publishable files scanned: `{len(files)}`",
        f"- Publishable bytes scanned: `{total_bytes}`",
        f"- Open findings: `{len(findings)}`",
        f"- Secret-pattern findings: `{sum(categories.get(name, 0) for name in SECRET_PATTERNS)}`",
        f"- Email-address findings: `{categories.get('email_address', 0)}`",
        f"- Named local-user-path findings: `{categories.get('named_user_path', 0)}`",
        f"- Workstation-path findings: `{categories.get('workstation_path', 0)}`",
        f"- Phone-number findings: `{categories.get('phone_number', 0)}`",
        f"- Personal-address findings: `{categories.get('personal_address', 0)}`",
        f"- Connection-string findings: `{categories.get('connection_string', 0)}`",
        f"- Private-username findings: `{categories.get('private_username', 0)}`",
        f"- Development-session metadata findings: `{categories.get('development_metadata', 0)}`",
        f"- Prohibited or unapproved file findings: `{categories.get('prohibited_file_type', 0) + categories.get('unapproved_binary_or_unknown_type', 0)}`",
        f"- Files at least 50 MiB: `{categories.get('large_file', 0)}`",
        f"- Cleared binary files: `{len(ALLOWED_BINARY_PATHS)}` fixed-coordinate Figure 4 exports.",
        "",
        "## Scope and interpretation",
        "",
        "The scan covers the public working tree while excluding Git internals and explicitly ignored runtime/build directories. It checks credential signatures, connection strings, email addresses, phone numbers, personal-address patterns, private usernames, named and generic workstation paths, development-session metadata, strict UTF-8 text decoding, large files, and every non-text file against an exact allowlist.",
        "",
        "The only allowed binary files are `results/reference/figure4/final/FINAL_FIGURE4_CARDOZO_BRIGHT_RIGHTLEGEND.pdf` and `results/reference/figure4/final/FINAL_FIGURE4_CARDOZO_BRIGHT_RIGHTLEGEND_600dpi.png`. Any other binary or unknown file type fails the audit.",
        "",
        "The scanner emits categories, paths, and line numbers only; it never copies a matched credential or personal-data value into the report. This repository check supplements GitHub secret scanning and the documented human redistribution review.",
        "",
        "Machine-readable findings are in `audits/PUBLIC_EXPOSURE_FINDINGS.tsv`.",
        "",
    ]
    if findings:
        lines.extend(["## Open findings", ""])
        lines.extend(
            f"- `{item.category}` in `{item.path}` at line `{item.line or 'N/A'}`: {item.note}"
            for item in findings
        )
        lines.append("")
    return "\n".join(lines)


def write_or_check(root: Path, outputs: dict[str, str], check: bool) -> None:
    """Write reports or require byte-identical checked versions."""

    stale: list[str] = []
    for relative, rendered in outputs.items():
        path = root / relative
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
                stale.append(relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8", newline="\n")
    if stale:
        raise SystemExit("Repository audit reports are stale: " + ", ".join(stale))


def main() -> None:
    """Run the audit, update or check reports, and fail on open findings."""

    args = parse_args()
    root = args.root.resolve()
    if not (root / "pyproject.toml").is_file():
        raise SystemExit(f"Not a repository root: {root}")
    files, findings, total_bytes = scan(root)
    report = render_report(files, findings, total_bytes)
    outputs = {
        "audits/PUBLIC_EXPOSURE_AUDIT.md": report,
        "audits/PUBLIC_EXPOSURE_FINDINGS.tsv": render_findings(findings),
        "audits/REPOSITORY_CONTENT_AUDIT.md": report.replace(
            "# Public exposure audit", "# Repository content audit", 1
        ),
    }
    write_or_check(root, outputs, args.check)
    print(
        f"Public exposure audit: {'PASS' if not findings else 'FAIL'}; "
        f"{len(files)} files; {len(findings)} findings"
    )
    if findings:
        raise SystemExit(
            "Repository content audit failed; inspect audits/PUBLIC_EXPOSURE_AUDIT.md"
        )


if __name__ == "__main__":
    main()
