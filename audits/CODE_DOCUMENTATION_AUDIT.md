# Code documentation audit

Overall status: `PASS`

- Checks evaluated: `1249`
- Passing checks: `1249`
- Failing checks: `0`

## Category summary

| Category | Passed | Total |
|---|---:|---:|
| `citation_bibtex` | 1 | 1 |
| `citation_cff` | 1 | 1 |
| `class_docstring` | 17 | 17 |
| `configuration_descriptor` | 60 | 60 |
| `development_metadata` | 200 | 200 |
| `function_docstring` | 450 | 450 |
| `markdown_link` | 132 | 132 |
| `module_docstring` | 69 | 69 |
| `powershell_failure_contract` | 6 | 6 |
| `powershell_help` | 18 | 18 |
| `spdx` | 75 | 75 |
| `test_descriptor` | 20 | 20 |
| `unresolved_marker` | 200 | 200 |

Tiny wrappers, self-explanatory test helpers, and unchanged third-party artifacts are permitted exceptions. All production modules and nontrivial callables remain in scope.

Machine-readable evidence is in `audits/CODE_DOCUMENTATION_AUDIT.tsv`.
