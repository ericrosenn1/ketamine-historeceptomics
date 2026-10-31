# Code documentation audit

Overall status: `PASS`

- Checks evaluated: `1440`
- Passing checks: `1440`
- Failing checks: `0`

## Category summary

| Category | Passed | Total |
|---|---:|---:|
| `citation_bibtex` | 1 | 1 |
| `citation_cff` | 1 | 1 |
| `class_docstring` | 18 | 18 |
| `configuration_descriptor` | 60 | 60 |
| `development_metadata` | 236 | 236 |
| `function_docstring` | 473 | 473 |
| `markdown_link` | 172 | 172 |
| `module_docstring` | 84 | 84 |
| `notebook_execution` | 8 | 8 |
| `notebook_python` | 8 | 8 |
| `powershell_failure_contract` | 6 | 6 |
| `powershell_help` | 18 | 18 |
| `spdx` | 90 | 90 |
| `test_descriptor` | 29 | 29 |
| `unresolved_marker` | 236 | 236 |

Tiny wrappers, self-explanatory test helpers, and unchanged third-party artifacts are permitted exceptions. All production modules and nontrivial callables remain in scope.

Machine-readable evidence is in `audits/CODE_DOCUMENTATION_AUDIT.tsv`.
