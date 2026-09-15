# AMAC usage examples

> **Illustrative: requires the real software, their handlers and composers, not
> implemented yet.** These scripts show the target usage of the current AMAC API
> with real programs. Today only the dummy programs run: see
> [`examples/quickstart.py`](../quickstart.py) for a runnable script.

Every script has a `main()` and does nothing when imported. The test suite only
checks that they compile.

| Script | Shows |
|---|---|
| [`01_single_point_orca_gaussian.py`](01_single_point_orca_gaussian.py) | The same DFT single point on ORCA and Gaussian, changing only `software`; energy comparison |
| [`02_optimisation_then_frequencies.py`](02_optimisation_then_frequencies.py) | Optimisation, then frequencies on the optimised geometry extracted by a handler (chaining is left outside the core); both results in one file |
| [`03_dftbplus_periodic.py`](03_dftbplus_periodic.py) | DFTB+ on a periodic crystal: `SETS` of `DFTB2`, parameters with variants, common arguments of a choice, charges and forces, `PERIODIC` check |
| [`04_dissociation_scan.py`](04_dissociation_scan.py) | Bond scan with per-image overrides, `raise_on_error=False`, failed images, `store`, `amac.load`, numpy analysis, `amac.reprocess` |
| [`05_facade_workstation.py`](05_facade_workstation.py) | `configure` (global and per software, executables, `driver="auto"`, `validate`), `calculator`, `run`, handlers for one call, `reset_configuration` |
| [`06_validation_and_raw.py`](06_validation_and_raw.py) | `strict` errors, `warn` mode and `calc.issues`, raw ORCA keywords, periodicity check |
| [`07_handlers.py`](07_handlers.py) | Custom handlers reading `ctx.files`, `@handler(requires_files=...)` without software, `handler_errors="collect"` then `"raise"`, `modules=` refusal |
| [`08_opi_driver.py`](08_opi_driver.py) | ORCA with `driver="opi"` and `"auto"`, `driver_fallback` in the provenance, handler `drivers=("opi",)` with `skip_incompatible=True` |
| [`09_reproducibility_hpc.py`](09_reproducibility_hpc.py) | `to_dict` (masked `env`, stored handlers) / `from_dict` saved as JSON, `workdir`, `outdir`, `keep_files`, `timeout`, `cpu`, `ram`, `env`, rerun elsewhere with overrides, `calc.reprocess` |
| [`10_pyscf_inprocess.py`](10_pyscf_inprocess.py) | PySCF in process: native objects in `ctx.objects`, captured logs |

## Assumed names

Only `amac/assets/dftbplus/doc.json` exists for a real program: the DFTB+ names of
example 03 come from it and pass its validation (`TIGHT_BINDING` / `DFTB2`,
`MaxAngularMomentum`, `SLATER_KOSTER_FILES` / `Type2FileNames`, `KPOINTS` /
`SupercellFolding`, `FILLING` / `Fermi` / `Temperature`, `MIXER`, `OPTIONS`,
`ANALYSIS`, `SINGLE_POINT`, `NEGF`). Everything else is assumed.

### Software names

| Name in the examples | Status |
|---|---|
| `ORCA`, `GAUSSIAN`, `DFTB+` (alias of `DFTBP`), `deMonNano` (alias of `DEMON`) | Registered today, without `doc.json` except DFTB+: `validate="strict"` refuses the others until their `doc.json` exists |
| `PYSCF` | Assumed, not registered |

### Handler packages and handlers

The packages exist (`amac.assets.orca`, `gaussian`, `dftbplus`, `demonnano`) but
expose no handler yet; `amac.assets.pyscf` does not exist. The handler names follow
the common names listed in the main README ("Adding a software").

| Package | Handlers | Notes |
|---|---|---|
| `from amac.assets import orca` | `energy`, `forces`, `dipole`, `charges`, `final_geometry`, `frequencies`, `hessian`, `opi_output` | `final_geometry` with `modules=("GEOMETRY_OPTIMISATION",)`, `frequencies` with `modules=("FREQ",)`, `hessian` with `requires_files=("*.hess",)`, `opi_output` with `drivers=("opi",)` |
| `from amac.assets import gaussian` | `energy`, `dipole`, `final_geometry` | |
| `from amac.assets import dftbplus` | `energy`, `forces`, `charges` | Read `results.tag` / `detailed.out` |
| `from amac.assets import demonnano` | `energy`, `forces` | |
| `from amac.assets import pyscf` | `energy`, `mo_energies` | The mean-field object in `ctx.objects["mf"]` |

Handlers return the values in the units of each program (Hartree for ORCA,
Gaussian, DFTB+; cm-1 for frequencies): unit conversion is not decided yet.

### Methods, modules and parameters (ORCA, Gaussian, deMonNano, PySCF)

- Methods: `DFT` with `method_args={"variant": "PBE0" | "B3LYP" | "wB97X-D" | "r2SCAN-3c", "Charge": ..., "Multiplicity": ...}`,
  modelled on the dummy `doc.json`; `TIGHT_BINDING` / `DFTB2` for deMonNano.
- Modules: `SINGLE_POINT`, `OPT` (alias of `GEOMETRY_OPTIMISATION`) with
  `module_args={"Convergence": "Tight"}`, `FREQ` (alias used by DFTB+ for
  `SECOND_DERIVATIVES`).
- Parameters: `BASIS`, `DISPERSION` (`"D3BJ"`), `SCF` (`Convergence`, `MaxIter`).
- Output files: `orca.out` (ORCA standard output).
- Driver: `opi` for ORCA, distribution `orca-pi`.
