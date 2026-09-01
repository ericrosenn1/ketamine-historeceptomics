# Code documentation audit

Overall status: `PASS`

- Checks evaluated: `1209`
- Passing checks: `1209`
- Failing checks: `0`

## Category summary

| Category | Passed | Total |
|---|---:|---:|
| `citation_bibtex` | 1 | 1 |
| `citation_cff` | 1 | 1 |
| `class_docstring` | 17 | 17 |
| `configuration_descriptor` | 52 | 52 |
| `development_metadata` | 190 | 190 |
| `function_docstring` | 442 | 442 |
| `markdown_link` | 132 | 132 |
| `module_docstring` | 67 | 67 |
| `powershell_failure_contract` | 6 | 6 |
| `powershell_help` | 18 | 18 |
| `spdx` | 73 | 73 |
| `test_descriptor` | 20 | 20 |
| `unresolved_marker` | 190 | 190 |

Tiny wrappers, self-explanatory test helpers, and unchanged third-party artifacts are permitted exceptions. All production modules and nontrivial callables remain in scope.

Machine-readable evidence is in `audits/CODE_DOCUMENTATION_AUDIT.tsv`.
