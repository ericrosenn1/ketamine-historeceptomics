# Public exposure audit

Overall status: `PASS`

- Publishable files scanned: `249`
- Publishable bytes scanned: `11676990`
- Open findings: `0`
- Secret-pattern findings: `0`
- Email-address findings: `0`
- Named local-user-path findings: `0`
- Workstation-path findings: `0`
- Phone-number findings: `0`
- Personal-address findings: `0`
- Connection-string findings: `0`
- Private-username findings: `0`
- Development-session metadata findings: `0`
- Prohibited or unapproved file findings: `0`
- Files at least 50 MiB: `0`
- Cleared binary files: `7` approved public binary assets.

## Scope and interpretation

The scan covers the public working tree while excluding Git internals and explicitly ignored runtime/build directories. It checks credential signatures, connection strings, email addresses, phone numbers, personal-address patterns, private usernames, named and generic workstation paths, development-session metadata, strict UTF-8 text decoding, large files, and every non-text file against an exact allowlist.

Allowed binary files are listed individually in `ALLOWED_BINARY_PATHS` in `scripts/audit_repository.py`; directory-wide binary exceptions are not permitted. Any other binary or unknown file type fails the audit.

The scanner emits categories, paths, and line numbers only; it never copies a matched credential or personal-data value into the report. This repository check supplements GitHub secret scanning and the documented human redistribution review.

Machine-readable findings are in `audits/PUBLIC_EXPOSURE_FINDINGS.tsv`.
