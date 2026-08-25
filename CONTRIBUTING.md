# Contributing

Contributions are welcome through focused pull requests. Open an issue first
when a change may alter scientific behavior, frozen inputs, reference outputs,
computation-affecting configuration, data licensing, or interpretation.

## Required with every pull request

1. Keep the change focused and explain its purpose.
2. Add or update tests for executable behavior.
3. Update user and developer documentation.
4. Update citations when sources or methods change.
5. Re-run the data-license review when any data or derived output changes.
6. State explicitly whether scientific outputs changed; never hide a numerical
   change inside a documentation or maintenance pull request.
7. Run the complete public validation appropriate to the change: tests, Smoke,
   Verify where public inputs support it, the documentation audit, metadata
   generation, and protected-tree review.

Do not commit credentials, private paths, raw licensed databases, literature
PDFs, manuscripts, correspondence, or generated local environments. Do not
zero-fill missing observations, collapse compound identities, weaken a
regression tolerance, refit a fixed reference, or reinterpret a tested non-call
without explicit scientific review.

See [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) for setup, conventions,
and the release procedure. By participating, you agree to follow the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
