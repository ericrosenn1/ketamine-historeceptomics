"""Expose package identity for the public historeceptomics implementation.

Stage: package initialization before any scientific or metadata lane.
Inputs: Python import state only; no scientific files or configuration.
Outputs: the public ``__version__`` metadata constant.
Side effects: creates no files, network requests, or numerical results.
Invariants: importing the package must not resolve inputs or execute a lane.
Lane: shared by Smoke, externally supplied Verify/Full, tests, and tooling.
"""

# SPDX-License-Identifier: MIT

__version__ = "0.1.1"
