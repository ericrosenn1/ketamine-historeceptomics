"""Dispatch ``python -m cardozo_ketamine_hr`` to the portable workflow.

Stage: command-line entry immediately before portable lane orchestration.
Inputs: process arguments, environment, and explicit paths parsed by ``main``.
Outputs: delegated run artifacts plus the portable process exit status.
Side effects: executes the requested lane and may write its derivative tree.
Invariants: this wrapper adds no routing defaults or scientific computation.
Lane: public Smoke, externally supplied Verify, or externally supplied Full.
"""

# SPDX-License-Identifier: MIT

from .portable import main


raise SystemExit(main())
