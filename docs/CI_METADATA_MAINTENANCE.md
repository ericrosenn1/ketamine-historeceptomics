# Dependency updates and checked metadata

Public validation deliberately checks committed audit reports, code hashes,
analysis-authority metadata, and exact staged-blob release manifests. Updating a
dependency can change those records even when the software tests pass. A green
synthetic test lane does not make stale publication evidence acceptable.

## Verified failure and repair

On October 31, 2026, [public-validation run 41191477606](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/runs/41191477606)
for the certifi dependency pull request passed its software/Smoke and secret-scan
jobs. Its documentation-audit job 124508981061 failed because
`PUBLIC_EXPOSURE_AUDIT.md` and `REPOSITORY_CONTENT_AUDIT.md` were stale. These
reports include total scanned bytes. Dependency version edits also require new
`CODE_INVENTORY.csv` hashes and, where applicable, updated authority and release
manifests. This was metadata drift, with no evidence of a scientific test failure
in that run. Later audit steps were skipped, so their success cannot be inferred.

The workflow retains every strict check. After a failure it attempts to build a
reviewable metadata patch from the exact staged commit, under a read-only token.
The patch is uploaded as an Actions artifact. Actual publication or documentation
violations abort patch generation. The job remains failed until a reviewed
refresh is committed; no report is silently accepted and no bot branch is
automatically written to.

## Maintainer sequence

First update/rebase an existing dependency pull request onto the branch containing
this maintenance tool, resolve any conflicts, and inspect the dependency change.
From its checkout and the documented Python environment:

```powershell
git add -- pyproject.toml requirements*.txt .github
if ($LASTEXITCODE -ne 0) { throw 'Staging dependency changes failed' }
.\.venv\Scripts\python.exe scripts/refresh_public_metadata.py --root .
if ($LASTEXITCODE -ne 0) { throw 'Metadata refresh failed; inspect the reported violation' }
git diff -- DATA_MANIFEST.csv CURRENT_ANALYSIS_AUTHORITY_MANIFEST.csv audits PUBLIC_RELEASE_MANIFEST.tsv SHA256SUMS.txt
git add -- DATA_MANIFEST.csv CURRENT_ANALYSIS_AUTHORITY_MANIFEST.csv audits/CODE_INVENTORY.csv audits/CODE_DOCUMENTATION_AUDIT.md audits/CODE_DOCUMENTATION_AUDIT.tsv audits/PUBLIC_EXPOSURE_AUDIT.md audits/PUBLIC_EXPOSURE_FINDINGS.tsv audits/REPOSITORY_CONTENT_AUDIT.md PUBLIC_RELEASE_MANIFEST.tsv SHA256SUMS.txt
if ($LASTEXITCODE -ne 0) { throw 'Staging generated evidence failed' }
.\.venv\Scripts\python.exe scripts/build_repository_metadata.py --root . --check
if ($LASTEXITCODE -ne 0) { throw 'Metadata check failed' }
.\.venv\Scripts\python.exe scripts/audit_code_documentation.py --root . --check
if ($LASTEXITCODE -ne 0) { throw 'Documentation check failed' }
.\.venv\Scripts\python.exe scripts/audit_repository.py --root . --check
if ($LASTEXITCODE -ne 0) { throw 'Publication boundary check failed' }
.\.venv\Scripts\python.exe scripts/build_release_manifests.py --root . --check
if ($LASTEXITCODE -ne 0) { throw 'Release manifest check failed' }
git diff --cached --stat
```

Commit and push only the reviewed diff, then require all checks on that exact
pull-request revision. For a source/documentation change, stage its intended
files before running the refresh. The utility uses the Git index, excludes
untracked files, and never stages changes automatically. Its isolated working
copy preserves regular-file modes and runs every generator twice to verify
stability. Only ten named generated metadata outputs can be copied back; the
60 frozen scientific reference artifacts are never written.

Alternatively, download the matching Actions remediation artifact and inspect
its patch. Apply it only to its exact source revision with `git apply --check`
followed by `git apply`, stage the changed generated records, and run the four
strict checks above. Regenerate after any rebase or source edit.

For a read-only local preview, use
`python scripts/refresh_public_metadata.py --root . --patch ../public-metadata-refresh.patch`.
The patch destination must be outside the source repository. A file hash proves
identity; it does not confer redistribution permission or scientific validity.
