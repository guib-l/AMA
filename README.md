# AMAC

**A**toms – **M**olecules – **A**ggregates **C**alculator: one Python syntax to
describe and run quantum chemistry calculations, whatever the software behind them.

A calculation is described once, in a software-independent form (method, module,
parameters). AMAC validates it against the `doc.json` of the chosen software,
writes the input, runs the program, extracts the requested properties with
*handlers*, and stores the results with their provenance.

> **Status:** two software are registered, `DFTBP` (DFTB+, file based) and
> `DEMON` (deMonNano, in process). See [Project status](#project-status).

## Installation

AMAC requires Python ≥ 3.12. It is not published on PyPI (no `pip install amac`):
install it from a checkout of the repository.

```bash
python -m pip install -e .              # numpy, ase
python -m pip install -e ".[test]"      # the above, plus pytest
python -m pip install -e ".[dftbplus]"  # the above, plus the hsd library of DFTB+
```

Run your scripts from the repository root with `python -m ...`, or add the root to
`PYTHONPATH`. `examples/quickstart.py` does it by itself when needed.

## Running the tests

```bash
python -m pytest                                        # no program needed
pytest -m real                                          # runs DFTB+ and deMonNano
pytest -m real --amac-config=/path/to/config-amac.json  # another configuration
ruff check amac test examples
```

The suite needs no quantum chemistry program: the generic chain is exercised on
the DFTB+ asset driven by a stub program written by the tests (`test/conftest.py`).
The tests marked `real` run the programs of the configuration file
(`--amac-config=PATH`, else the `config-amac.json` of the repository) and are
skipped when it gives none.


## Quickstart

With the `AMAC` class:

```python
from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import dftbplus

water = molecule("H2O")

# Machine configuration of every calculator of this process; AMAC(config=...)
# gives one calculator its own file.
amac.set_config("config-amac.json")

calc = AMAC(
    software="DFTB+",
    method="TIGHT_BINDING",
    method_args={
        "variant": "DFTB2",  # SCC-DFTB; the variant sets SCC = Yes by itself
        "SCCTolerance": 1e-6,
        "MaxAngularMomentum": {"O": "p", "H": "s"},
    },
    module="SINGLE_POINT",
    parameters={
        # Prefix is written from BASIS in the configuration file, never here.
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
        "OPTIONS": {"WriteResultsTag": True},
    },
    cpu=2,
    workdir="runs",
    label="water",
)
calc.handler_properties(
    dftbplus.energy,
    dftbplus.forces,
    ("atom_count", lambda ctx: len(ctx.atoms)),  # custom handler
)
result = calc.execute(water)  # runs in runs/water
print(result.success, result.properties)

path = calc.store("water-results")  # writes water-results.json
[reloaded] = amac.load(path)
```

The executable and `BASIS` come from the configuration file (see
[Configuration and executables](docs/configuration.md)); AMAC reads no
environment variable and never searches `PATH`.

With the module facade:

```python
amac.configure(cpu=2, workdir="runs")
amac.calculator(
    parameters={
        "method": "TIGHT_BINDING",
        "method_args": {"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
        "parameters": {"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
    },
    platform="DFTB+",
    label="facade",
    handlers=[dftbplus.energy],
)
results = amac.run([water, water])  # runs/facade/image_000 and image_001
```

A complete script: `python examples/quickstart.py [WORKDIR]` (a temporary
directory is used when `WORKDIR` is omitted).

Examples with the real programs (DFTB+, deMonNano): [`examples/`](examples/). They
take their configuration file from `--config=PATH`, and from the
`config-amac.json` of this repository without it; AMAC itself reads no
environment variable:

```bash
python examples/quickstart.py
python examples/dftbplus_02_molecular_optimisation.py ~/runs --config=/etc/amac.json
```

Without a file giving the program they stop and print the command to run;
nothing is guessed.

## Documentation

| Document | Content |
|---|---|
| [Describing a calculation](docs/calculations.md) | Spec (`method`, `module`, `parameters`, `raw`) and validation |
| [Handlers](docs/handlers.md) | Extracting properties from a run |
| [Runs, results and reprocessing](docs/runs.md) | Directories, failures, reprocessing, saving a calculator, stored results |
| [Configuration and executables](docs/configuration.md) | `config-amac.json`, executables, `BASIS`, default `workdir` |
| [Adding a software](docs/adding-a-software.md) | Writing a new `amac/assets/<software>/` package |
| [Using a dedicated library](docs/drivers.md) | Drivers (`driver="auto"`, `Software.DRIVERS`) |
| [Running the tests](docs/testing.md) | `pytest`, the `real` marker, `ruff` |
| [`DOC_SCHEMA.md`](docs/DOC_SCHEMA.md) | Format of the `doc.json` of a software |
| [`CATALOG_SCHEMA.md`](docs/CATALOG_SCHEMA.md) | Format of the canonical catalog |

### Canonical catalog

`catalog/`, at the repository root, names methods, modules and options independently
of any software (`B3LYP`, `DFTB2`, `GEOMETRY_OPTIMISATION`, `D3(BJ)`, ...), with their
aliases. Each top-level entry has its own directory,
`catalog/<methods|modules|options>/<slug>/`, holding `entry.json` and a `README.md`
(summary and references). Each `doc.json` links its nodes to these names with
`CANONICAL`. Formats are described in [`docs/CATALOG_SCHEMA.md`](docs/CATALOG_SCHEMA.md)
and in the `CANONICAL` section of [`docs/DOC_SCHEMA.md`](docs/DOC_SCHEMA.md); the
`catalog-curator` agent (`.claude/agents/`) adds new entries.

## Project status

Implemented: canonical specs, `doc.json` loading and validation (variants, `SETS`,
`COMPANION`, `COMMON_ARGUMENTS`), the intermediate tree, the local executor,
handlers, the `AMAC` class with per-image overrides and reprocessing, the facade,
JSON storage with provenance, optional library drivers (interface and selection),
the canonical catalog and its equivalence tables.

Not implemented yet:

- concrete composers for the `NAMELIST` and `FLAT` syntaxes (`KEYWORD_BLOCK` and
  `TREE` are implemented);
- real software: DFTB+ and deMonNano are complete, with their `doc.json`;
  deMonNano runs in process through the `deMonPy` library (`DeMonNanoPy`, installed
  from its repository, not from PyPI); ORCA, Gaussian, PySCF and GPAW are not
  started;
- library drivers beyond DFTB+: it has its API and `hsd` drivers, the AbiPy one is
  not started;
- parallel images, HPC schedulers, restarts and chained calculations (chaining is
  left to a workflow layer outside the core), so the external post-processing
  programs (`modes`, `waveplot`, ...) are not run;
- the free-text `CONDITION` fields of the `doc.json`.
