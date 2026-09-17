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
| [`08_cclib_driver.py`](08_cclib_driver.py) | ORCA with `driver="cclib"` and `"auto"`, `driver_fallback` in the provenance, the same handlers whichever driver collects |
| [`09_reproducibility_hpc.py`](09_reproducibility_hpc.py) | `to_dict` (masked `env`, stored handlers) / `from_dict` saved as JSON, `workdir`, `outdir`, `keep_files`, `timeout`, `cpu`, `ram`, `env`, rerun elsewhere with overrides, `calc.reprocess` |
| [`10_pyscf_inprocess.py`](10_pyscf_inprocess.py) | PySCF in process: native objects in `ctx.objects`, captured logs |

## Assumed names

`amac/assets/dftbplus/doc.json` and `amac/assets/orca/doc.json` exist for real
programs: the DFTB+ names of example 03 and the ORCA names of examples 01, 06 and
08 come from them and pass their validation (DFTB+: `TIGHT_BINDING` / `DFTB2`,
`MaxAngularMomentum`, `SLATER_KOSTER_FILES` / `Type2FileNames`, `KPOINTS` /
`SupercellFolding`, `FILLING` / `Fermi` / `Temperature`, `MIXER`, `OPTIONS`,
`ANALYSIS`, `SINGLE_POINT`, `NEGF`). Everything else is assumed.

### Software names

| Name in the examples | Status |
|---|---|
| `ORCA`, `DFTB+` (alias of `DFTBP`), `deMonNano` (alias of `DEMON`) | Registered, with a `doc.json`: `validate="strict"` checks the calculation |
| `GAUSSIAN` | Registered without `doc.json`: `validate="strict"` refuses it until its own exists |
| `PYSCF` | Assumed, not registered |

### Handler packages and handlers

`amac.assets.dftbplus`, `amac.assets.orca` and `amac.assets.demonnano` expose their
handlers; `gaussian` exists but exposes none yet, and `amac.assets.pyscf` does not
exist. The handler names follow the common names
listed in the main README ("Adding a software").

| Package | Handlers | Notes |
|---|---|---|
| `from amac.assets import orca` | `energy`, `forces`, `charges`, `mulliken_charges`, `loewdin_charges`, `dipole`, `orbital_energies`, `frequencies`, `hessian`, `excitations`, `final_geometry` | Read `orca.out`, `orca.engrad` and `orca.hess`; `forces` with `requires_files=("orca.engrad",)`, `hessian` with `requires_files=("orca.hess",)`, `final_geometry` with `modules=("GEOMETRY_OPTIMISATION", …)`; `frequencies` returned as energies in eV |
| `from amac.assets import gaussian` | `energy`, `dipole`, `final_geometry` | |
| `from amac.assets import dftbplus` | `energy`, `forces`, `charges`, `dipole`, `orbital_energies`, `final_geometry` | Read `results.tag` and `detailed.out`; `final_geometry` with `modules=("GEOMETRY_OPTIMISATION", …)` |
| `from amac.assets import demonnano` | `energy`, `forces`, `charges`, `dipole`, `final_geometry` | Read `deMon.out` and `deMon.mol`; `forces` needs the `PRINT GRAD` directive, `final_geometry` with `modules=("GEOMETRY_OPTIMISATION", "MOLECULAR_DYNAMICS")` |
| `from amac.assets import pyscf` | `energy`, `mo_energies` | The mean-field object in `ctx.objects["mf"]` |

The DFTB+ and ORCA handlers return ASE units (eV, eV/Å, e·Å), while their parsers
keep the units of the program (Hartree, Bohr). The other packages, still to be
written, follow the same rule.

### Methods, modules and parameters

ORCA (from its `doc.json`):

- Methods: `DFT` with `method_args={"variant": ...}`, among `PBE0`, `B3LYP`
  (VWN3, written `B3LYP/G`), `B3LYP5` (VWN5, written `B3LYP`), `r2SCAN`, `M06-2X`;
  also `HF`, `MOLLER_PLESSET`, `COUPLED_CLUSTER`, `MULTIREFERENCE`, `XTB`.
- Modules: `SINGLE_POINT`, `GRADIENT`, `OPT` (alias of `GEOMETRY_OPTIMISATION`),
  `FREQ`, `IRC`, `NEB`, `PES_SCAN`, `MOLECULAR_DYNAMICS`.
- Parameters: `CHARGE` and `MULTIPLICITY` (written on the `* xyz` line, not as a
  block), `BASIS`, `DISPERSION` (`"D3BJ"`), `REFERENCE`, `INTEGRAL_APPROXIMATION`,
  `SOLVATION` (`{"variant": "SMD", "SMDsolvent": "water"}`), `EXCITED_STATES`,
  `SCF` (`Convergence`, `MaxIter`).
- Output files: `orca.out`, `orca.engrad`, `orca.hess`, `orca.xyz`.
- Driver: `cclib` (distribution `cclib`), `collect` only.

deMonNano (from its `doc.json`):

- Method: `DFTB` (alias `TIGHT_BINDING`) with `method_args={"variant": ...}`, among
  `DFTB1`, `DFTB2` and `CI-DFTB` (alias `DFTB-CI`, whose `SIZECI`, `NOSLAT` and
  `CONST` are its arguments).
- Modules: `SINGLE_POINT`, `OPT` (alias of `GEOMETRY_OPTIMISATION`) and `MD`, run
  through the modules of the `deMonPy` library.
- Parameters: `SLATER_KOSTER_FILES` (`PTYPE`, `SKFILE`; mandatory), `CHARGE`,
  `MULTIPLICITY`, `REFERENCE` (`RESTRICTED` only), `OUTPUT_CONTROL` (`GRAD`, `MOE`),
  and the common DFTB options (`SCC`, `TOL`, `MAX`, `MIX`, `FERMI`).
- Output files: `deMon.out`, `deMon.mol`, `forces.out`.
- No driver: the library is the software itself, run in process (`EXECUTION`
  `INPROCESS`); it still needs the `deMon.x` executable, which AMAC resolves and
  hands over.

Gaussian and PySCF have no `doc.json` yet: their names in the examples are
modelled on the sample schema of the tests (`test/fixtures/schema.json`).
