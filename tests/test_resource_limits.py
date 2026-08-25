"""Test that runtime worker selection respects configured resource ceilings."""

# SPDX-License-Identifier: MIT

from cardozo_ketamine_hr.resource_manager import ResourceManager


def test_resource_manager_never_selects_above_ceiling(tmp_path):
    manager = ResourceManager(tmp_path / "resources.csv")
    workers = manager.choose_workers(10_000)
    assert 1 <= workers <= manager.cpu_ceiling
    manager.snapshot("TEST", workers)
    report = manager.report()
    assert report["peak_workers"] <= report["cpu_worker_ceiling"]
    assert report["configured_ram_ceiling_bytes"] == int(0.8 * report["total_ram_bytes"])
