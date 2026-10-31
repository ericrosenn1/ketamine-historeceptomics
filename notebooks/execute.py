"""Execute the synthetic teaching notebook in the caller's Python environment.

Stage: optional public notebook validation, separate from scientific Verify.
Inputs: the tracked quickstart notebook and invented CSV fixtures.
Outputs: an executed notebook at an explicit destination and a terminal summary.
Side effects: creates the output parent and a temporary kernel specification.
Invariants: uses this interpreter, fails on cell errors, never reads external
scientific authorities, and does not modify the source notebook by default.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager


def main() -> None:
    """Run all cells with an isolated kernel specification and validate outputs."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=root / "results/runs/Historeceptomics_Quickstart.executed.ipynb",
        help="Executed copy; defaults to ignored results/runs/.",
    )
    args = parser.parse_args()
    notebook = nbformat.read(root / "notebooks/Historeceptomics_Quickstart.ipynb", as_version=4)
    nbformat.validate(notebook)
    with TemporaryDirectory(prefix="hr-notebook-") as kernel_directory:
        specification = Path(kernel_directory) / "historeceptomics-demo"
        specification.mkdir()
        (specification / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "Historeceptomics synthetic demo",
            "language": "python",
        }), encoding="utf-8")
        manager = KernelManager(
            kernel_name="historeceptomics-demo",
            kernel_spec_manager=KernelSpecManager(kernel_dirs=[kernel_directory]),
        )
        NotebookClient(
            notebook, km=manager, timeout=120, allow_errors=False,
            resources={"metadata": {"path": str(root)}},
        ).execute(cleanup_kc=True)
    for cell in notebook.cells:
        cell.metadata.pop("execution", None)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if any(cell.execution_count is None for cell in code_cells):
        raise RuntimeError("Notebook contains an unexecuted code cell")
    if not any("image/png" in output.get("data", {})
               for cell in code_cells for output in cell.outputs):
        raise RuntimeError("Notebook did not produce the representative figure")
    nbformat.validate(notebook)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, args.output)
    print(f"PASS: {len(code_cells)} code cells executed; synthetic figure saved in {args.output.name}")


if __name__ == "__main__":
    main()
