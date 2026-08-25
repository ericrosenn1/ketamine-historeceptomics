# Validated environment

## Release-equivalent lane

- Operating system: Windows 11 (`Windows-11-10.0.26200-SP0` in the metadata build)
- Python: `3.12.10`; supported package range `>=3.12,<3.13`
- PowerShell Core: `7.6.4`
- Windows PowerShell observed: `5.1.26100.9168`
- Numerical lane: CPU float64
- BLAS/OpenMP threads: one
- Fixed MDS seed: `20260813`
- R: not used by the portable core
- GPU: not used for release-equivalent execution

The validation workstation used an AMD Ryzen 9 9950X3D with 93.65 GiB RAM. An
RTX 5090 was detected, but CUDA/CuPy was unavailable and no accepted output
depends on GPU execution. Hardware details describe one validation environment;
they are not minimum requirements.

## Exact Python packages

| Package | Version |
|---|---:|
| numpy | 2.5.1 |
| pandas | 3.0.5 |
| scipy | 1.18.0 |
| scikit-learn | 1.8.0 |
| matplotlib | 3.11.1 |
| pyarrow | 24.0.0 |
| joblib | 1.5.3 |
| Pillow | 12.3.0 |
| psutil | 7.2.2 |
| pypdf | 6.16.1 |
| PyYAML | 6.0.3 |
| pytest | 9.1.0 |

[`requirements-lock.txt`](../requirements-lock.txt) is the complete exact
installation record, including transitive dependencies. `pyproject.toml`
records the direct runtime requirements and Python range. Use the lock for
validation and publication work.

## Determinism controls

The supported launchers set `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`,
`MKL_NUM_THREADS`, and `NUMEXPR_NUM_THREADS` to `1`. Numerical sorting and tie
behavior are deterministic under the governed contracts, and methods requiring
a random seed use the fixed value above. Fixed-reference projections and Figure
4 coordinates are never refit during Smoke, Verify, or Full.

GPU support is optional code behind an explicit CPU-equivalence gate; it is not
part of the release contract. A GPU result must agree with CPU float64 within
the implemented tolerance or the CPU route is used.

## Public execution boundary

Environment recreation does not supply scientific data. Smoke is
self-contained with invented fixtures. Verify and Full additionally require a
manifest-valid external input root, and Full requires its stated upstream
inputs. See [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) and
[`FULL_MODE.md`](FULL_MODE.md).
