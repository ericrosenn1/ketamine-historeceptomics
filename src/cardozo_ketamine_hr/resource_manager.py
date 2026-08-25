# SPDX-License-Identifier: MIT
"""Bound CPU, RAM, BLAS threads, and optional GPU resource observations.

Stage
-----
The resource manager is initialized before computational stages and sampled at
stage boundaries throughout a run.

Inputs
------
Host CPU/RAM state, optional ``nvidia-smi`` output, task counts, memory
estimates, and an output-log path are consumed.

Outputs
-------
The manager appends resource snapshots to CSV and returns worker counts and a
compact final resource report.

Side Effects
------------
Sets thread-limit environment variables, probes system resources, invokes
``nvidia-smi`` when present, and creates/appends a CSV log.

Invariants
----------
CPU and RAM ceilings are capped at 80 percent, at least one worker is retained,
and GPU detection never implies that scientific GPU acceleration was used.

Lane
----
Portable execution-control and provenance lane.
"""

from __future__ import annotations

import csv
import math
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


THREAD_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}


def configure_thread_limits() -> None:
    """Set single-thread limits for supported numerical libraries.

    Returns
    -------
    None

    Side Effects
    ------------
    Updates process environment variables listed in ``THREAD_ENVIRONMENT``.
    """
    for key, value in THREAD_ENVIRONMENT.items():
        os.environ[key] = value


@dataclass
class ResourceManager:
    """Monitor host resources and choose bounded parallel worker counts.

    Attributes
    ----------
    output_csv : pathlib.Path
        Resource snapshot log created during initialization.
    logical_cpu, physical_cpu : int
        Detected processor counts.
    cpu_ceiling : int
        Maximum workers permitted by the 80-percent CPU policy.
    total_ram, configured_ram_ceiling : int
        Detected RAM and governed byte ceiling.
    gpu : dict
        Latest optional NVIDIA telemetry.
    peak_workers, peak_ram_used, peak_vram_used_mb : int or float
        Peak observations accumulated across the run.
    """

    output_csv: Path
    logical_cpu: int = field(init=False)
    physical_cpu: int = field(init=False)
    cpu_ceiling: int = field(init=False)
    total_ram: int = field(init=False)
    configured_ram_ceiling: int = field(init=False)
    gpu: dict[str, Any] = field(init=False)
    peak_workers: int = 1
    peak_ram_used: int = 0
    peak_vram_used_mb: float = 0.0

    def __post_init__(self) -> None:
        """Detect resources, configure limits, and initialize the CSV log.

        Returns
        -------
        None

        Side Effects
        ------------
        Sets thread environment variables and overwrites ``output_csv`` with a
        fresh header.
        """
        configure_thread_limits()
        self.logical_cpu = int(psutil.cpu_count(logical=True) or 1)
        self.physical_cpu = int(psutil.cpu_count(logical=False) or self.logical_cpu)
        self.cpu_ceiling = max(1, int(math.floor(0.80 * self.logical_cpu)))
        self.total_ram = int(psutil.virtual_memory().total)
        self.configured_ram_ceiling = int(0.80 * self.total_ram)
        self.gpu = self._detect_gpu()
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.output_csv.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow([
                "timestamp", "stage", "cpu_percent", "worker_count", "ram_used_bytes",
                "ram_available_bytes", "gpu_name", "gpu_utilization_percent", "vram_used_mb",
                "vram_available_mb", "cpu_ceiling", "ram_ceiling_bytes", "vram_ceiling_mb",
            ])

    @staticmethod
    def _detect_gpu() -> dict[str, Any]:
        """Read first-device NVIDIA telemetry when ``nvidia-smi`` is usable.

        Returns
        -------
        dict of str to Any
            Availability, device name, memory, and utilization fields. Failures
            return an unavailable record rather than raising.

        Side Effects
        ------------
        May invoke ``nvidia-smi`` with a ten-second timeout.
        """
        executable = shutil.which("nvidia-smi")
        if not executable:
            return {"available": False, "name": "", "total_mb": 0.0, "free_mb": 0.0, "used_mb": 0.0, "util": 0.0}
        command = [
            executable,
            "--query-gpu=name,memory.total,memory.free,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
        try:
            line = subprocess.check_output(command, text=True, timeout=10).splitlines()[0]
            name, total, free, used, util = [part.strip() for part in line.split(",")]
            return {
                "available": True,
                "name": name,
                "total_mb": float(total),
                "free_mb": float(free),
                "used_mb": float(used),
                "util": float(util),
            }
        except Exception:
            return {"available": False, "name": "", "total_mb": 0.0, "free_mb": 0.0, "used_mb": 0.0, "util": 0.0}

    def choose_workers(self, task_count: int, memory_per_worker_bytes: int = 256 * 1024 * 1024) -> int:
        """Choose a worker count from task, CPU-load, and RAM headroom.

        Parameters
        ----------
        task_count : int
            Number of independent tasks available.
        memory_per_worker_bytes : int, default=268435456
            Conservative memory estimate per worker.

        Returns
        -------
        int
            Bounded worker count of at least one.

        Side Effects
        ------------
        Samples CPU/RAM and updates ``peak_workers``.
        """
        vm = psutil.virtual_memory()
        load = psutil.cpu_percent(interval=0.2)
        load_headroom = max(1, int(math.floor(self.logical_cpu * max(0.05, 0.80 - load / 100.0))))
        memory_headroom = max(1, int((0.80 * vm.available) // max(memory_per_worker_bytes, 1)))
        # The minimum across independent ceilings prevents one favorable
        # resource dimension from overruling another constrained dimension.
        workers = max(1, min(self.cpu_ceiling, load_headroom, memory_headroom, max(1, task_count)))
        self.peak_workers = max(self.peak_workers, workers)
        return workers

    def snapshot(self, stage: str, workers: int = 1) -> None:
        """Append one timestamped resource snapshot.

        Parameters
        ----------
        stage : str
            Stable pipeline-stage label.
        workers : int, default=1
            Active worker count to record.

        Returns
        -------
        None

        Side Effects
        ------------
        Samples CPU, RAM, and GPU telemetry; updates peaks; appends one CSV row.
        """
        vm = psutil.virtual_memory()
        self.gpu = self._detect_gpu()
        ram_used = int(vm.total - vm.available)
        self.peak_ram_used = max(self.peak_ram_used, ram_used)
        self.peak_vram_used_mb = max(self.peak_vram_used_mb, float(self.gpu.get("used_mb", 0.0)))
        vram_ceiling = 0.80 * float(self.gpu.get("total_mb", 0.0))
        row = [
            datetime.now(timezone.utc).isoformat(), stage, psutil.cpu_percent(interval=0.1), workers,
            ram_used, int(vm.available), self.gpu.get("name", ""), self.gpu.get("util", 0.0),
            self.gpu.get("used_mb", 0.0), self.gpu.get("free_mb", 0.0), self.cpu_ceiling,
            self.configured_ram_ceiling, vram_ceiling,
        ]
        with self.output_csv.open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(row)

    def report(self) -> dict[str, Any]:
        """Return the final resource-policy and peak-usage summary.

        Returns
        -------
        dict of str to Any
            CPU/RAM ceilings, observed peaks, GPU telemetry, acceleration
            status, and BLAS thread limits.
        """
        gpu_total = float(self.gpu.get("total_mb", 0.0))
        return {
            "logical_cpu": self.logical_cpu,
            "physical_cpu": self.physical_cpu,
            "cpu_worker_ceiling": self.cpu_ceiling,
            "peak_workers": self.peak_workers,
            "total_ram_bytes": self.total_ram,
            "configured_ram_ceiling_bytes": self.configured_ram_ceiling,
            "peak_ram_used_bytes": self.peak_ram_used,
            "gpu_detected": bool(self.gpu.get("available")),
            "gpu_name": self.gpu.get("name", ""),
            "gpu_total_vram_mb": gpu_total,
            "gpu_vram_ceiling_mb": 0.80 * gpu_total,
            "peak_vram_used_mb": self.peak_vram_used_mb,
            "gpu_acceleration_used": False,
            "gpu_acceleration_status": "GPU_ACCELERATION_NOT_AVAILABLE_FOR_INSTALLED_SCIENTIFIC_STACK_OR_NOT_BENEFICIAL_FOR_SMALL_MATRICES",
            "blas_thread_limits": THREAD_ENVIRONMENT,
        }
