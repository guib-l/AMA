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
[Configuration and executables](#configuration-and-executables)); AMAC reads no
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

## Concepts

### Calculation spec

| Argument | Meaning |
|---|---|
| `method`, `method_args` | Which calculation is done, e.g. `"DFT"` with `{"variant": "PBE"}` |
| `module`, `module_args` | How it is used: `"SINGLE_POINT"` (default), `"GEOMETRY_OPTIMISATION"`, ... |
| `parameters` | General options: basis, SCF, solvation, output, ... |
| `raw` | Software keywords passed unchanged to the composer, never validated |

Names and aliases are resolved case-insensitively against the `doc.json` of the
software, whose format is described in
[`DOC_SCHEMA.md`](DOC_SCHEMA.md): variants of methods,
modules and options, values imposed by a variant (`SETS`), companion parameters
(`COMPANION`) and arguments shared by every choice (`COMMON_ARGUMENTS`). The spec is
translated into a software-independent intermediate tree
(`amac.parameter.composer.translate`), which each syntax family renders as input
files.

### Validation

`validate="strict"` (default) raises a `ValidationError` listing every issue,
`"warn"` emits one warning per issue, `"off"` skips the checks. The checks that
depend on the geometry (`PERIODIC` against `atoms.pbc`) run in `execute()`.

A software without `doc.json` cannot be validated: `"strict"` refuses it with a
`ValidationError`, `"warn"` accepts it with a warning, `"off"` accepts it silently.
`provenance["validated"]` tells whether a result was validated.

The exceptions are exported by the package: `amac.AMACError` (base class),
`amac.ValidationError`, `amac.SoftwareNotFoundError`, `amac.RunError`,
`amac.HandlerError`, `amac.DriverUnavailableError`.

```python
try:
    AMAC(
        software="DFTB+",
        method="TIGHT_BINDING",
        method_args={"variant": "DFTB9"},  # no such variant: refused in "strict"
        parameters={"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
    )
except amac.ValidationError as error:
    print(error)
```

### Handlers

A handler is any callable `f(ctx)` receiving the `RunContext` of a run; the key of
its result is the handler name.

- Handlers of a software are declared with
  `@handler(software=..., requires_files=(), modules=None, drivers=None)` and
  exposed by the package of the software, e.g. `dftbplus.energy`.
- A custom handler is a function (named after its `__name__`) or a
  `(name, callable)` tuple; a lambda needs a tuple. `@handler(software=None, ...)`
  gives a custom handler metadata such as `requires_files` without attaching it to
  a software: it is accepted by every software.
- `handler_properties()` replaces the previous handlers and refuses handlers of
  another software, incompatible modules or drivers, and duplicate result names.
  With `skip_incompatible=True`, the handlers incompatible with the module or the
  selected driver are discarded with one warning giving the reasons (including an
  `"auto"` fallback); `amac.calculator()` and `amac.run()` accept the same option.
- A failing handler, or one whose `requires_files` match no produced file, has no
  entry in `result.properties` and adds a `HandlerError` to `result.errors`. With
  `handler_errors="raise"` the first failure is raised instead. `result.success`
  only reflects the run.

```python
calc = AMAC(
    software="DFTB+",
    method="TIGHT_BINDING",
    method_args={"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
    parameters={"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
    workdir="runs",
    label="concepts",
    raise_on_error=False,
)
calc.handler_properties(dftbplus.energy, ("broken", lambda ctx: 1 / 0))
result = calc.execute(water, cpu=4)  # overrides for this call only
assert result.success and "broken" not in result.properties
print(result.errors[0])  # Handler 'broken' failed: ZeroDivisionError(...)
```

### Runs, directories and failures

- A single image runs in `workdir/<label>`, an iterable of images in
  `workdir/<label>/image_XXX`; `label` defaults to `amac`. A non-empty directory is
  refused unless `overwrite=True`.
- An image is an `Atoms`, or an `(Atoms, image_overrides)` tuple overriding
  `method_args`, `module_args`, `parameters` and `raw` for this image only
  (mappings merged in depth, `method` and `module` fixed). A tuple of exactly an
  `Atoms` and a mapping is one image; any other iterable is a sequence of images.
  An image with overrides is fully validated again, and its effective spec is
  `provenance["spec"]`.
- `outdir` receives a copy of each run directory; `keep_files=False` removes the run
  directory once the handlers have run.
- Where the files go is always `workdir`, given to `AMAC(...)`, to
  `amac.configure()`, to one `execute()` call, or as the `workdir` of the
  configuration file; AMAC reads no environment variable for it. `calc.workdir`
  gives the root as an absolute path,
  `calc.directories` the run directories of the last call, and each run logs its
  own on the `amac.amac` logger at `INFO`:

  ```python
  import logging

  logging.basicConfig(level=logging.INFO)   # AMAC installs no handler itself
  calc = AMAC(software="DFTB+", workdir="~/amac-runs", label="water", **CALCULATION)
  calc.execute([water, water])
  # INFO:amac.amac:DFTBP: run directory /home/me/amac-runs/water/image_000 (image 0)
  # INFO:amac.amac:DFTBP: run directory /home/me/amac-runs/water/image_001 (image 1)
  print(calc.workdir, calc.directories)
  ```

  Without any of them, the runs go to the current directory. The examples follow
  the same convention: they take their root from their first argument, then
  `~/amac-runs`, and print it before running
  (`python examples/dftbplus_02_molecular_optimisation.py /data/runs`).
- `timeout` kills the whole process group. `OMP_NUM_THREADS` is set to `cpu` unless
  `env` overrides it.
- `raise_on_error=True` (default) raises a `RunError` at the first failing image,
  the previous results staying in `calc.results`. With `raise_on_error=False` the
  image gets a `Result(success=False)` holding the error, including timeouts and
  missing programs, and the next images run.
- `execute(geometry, **overrides)` accepts `ExecutionSpec` fields (`cpu`,
  `timeout`, `label`, `overwrite`, ...) for one call; `driver` cannot be
  overridden. Each call replaces `calc.results`.
- Chaining calculations (e.g. frequencies on an optimised geometry) is left to the
  caller: extract the geometry with a handler and run a second calculator.

```python
scan = AMAC(
    software="DFTB+",
    method="TIGHT_BINDING",
    method_args={"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
    parameters={"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
    workdir="runs",
    label="scan",
)
scan.handler_properties(dftbplus.energy)
images = [water, (water, {"method_args": {"SCCTolerance": 1e-8}})]
results = scan.execute(images)
assert results[1].provenance["spec"]["method_args"]["SCCTolerance"] == 1e-8
```

### Reprocessing

Handlers can run again on the files of a finished calculation, without running it:
`calc.reprocess(directory, handlers=None, atoms=None)` runs `collect` (through the
driver when it collects) and the handlers on an existing run directory, and
`amac.reprocess(result, handlers)` rebuilds the calculator of a stored result from
its provenance (`directory`, or the `outdir` copy when the directory is gone).
Handlers reading native objects of a library fail with a `HandlerError` unless the
driver rebuilds them when collecting.

```python
again = scan.reprocess(results[0].context.directory, handlers=[dftbplus.charges])
print(again.properties)  # {'charges': array([-0.59, 0.29, 0.29])}
```

### Configuration and executables

`amac.configure()` only affects the facade (`amac.calculator()` / `amac.run()`); an
`AMAC` object created directly never reads it. It sets execution defaults,
`validate`, and per software the executable and the driver. Defaults apply in this
order: global `configure()` < `configure(software=...)` < keyword arguments of
`calculator()`. The facade state is global to the process and not thread-safe. Its
only process-wide setting is `configure(config=...)`, which calls
`amac.set_config()` and therefore reaches every calculator.

The executable is resolved by `Software.locate_executable` when the command is
built. It only comes from an explicit source, the first one set wins; **AMAC never
searches `PATH`**, and the executable must be an absolute path (`~` is expanded):

| # | Source | Provenance `source` |
|---|---|---|
| 1 | `executable=`, then `amac.configure(software=..., executable=...)` (facade only) | `executable=` |
| 2 | `executable` of `[software.<NAME>]` in the machine configuration file | `file:<path>` |

**AMAC reads no environment variable.** The configuration file is always given
explicitly, as a JSON file:

| Given to | How | Wins over |
|---|---|---|
| One calculator | `AMAC(config=...)`, `amac.calculator(..., config=...)`, `amac.which(name, config=...)` | the file of the process |
| The process | `amac.set_config(path)`, `amac.configure(config=...)` | nothing |

Without either there is simply no configuration: no executable and no `env` are
found, and `execute()` raises `ExecutableNotFoundError` when it needs one.
`amac.set_config(None)` and `amac.reset_configuration()` forget the file again. A
file that is given but does not exist raises `ConfigurationError`.

The objects of `software` are named after a software or one of its aliases; only
`executable` and `env` are accepted, and the top level also takes `workdir`:

```json
{
    "workdir": "~/amac-runs",
    "software": {
        "DFTB+": {
            "executable": "~/opt/dftbplus/bin/dftb+",
            "env": {"BASIS": "/data/slako/3ob-3-1/"}
        },
        "deMonNano": {
            "executable": "~/opt/demonnano/deMon.x",
            "env": {"BASIS": "/data/demonnano/basis/"}
        }
    }
}
```

- `workdir` is the default root of the run directories, used when no `workdir=`
  is given; `~` is expanded and the result must be an absolute path.
- A bare name such as `dftb+` or a relative path is rejected, whatever its source.
- `BASIS` in the `env` of DFTB+ and deMonNano is the directory of the Slater-Koster
  files, and its only source: DFTB+ gets it as `Prefix`, deMonNano as `SKFILE`.
  Giving them in the spec is refused; a missing `BASIS` raises
  `ConfigurationError`.
- The `env` of the file is added to the runs: `os.environ` < `OMP_NUM_THREADS` <
  file `env` < `exec_spec.env`. Drivers get it in `execution_settings()["env"]`. It
  is never stored in `exec_spec`, `to_dict()` or the results.
- Invalid JSON, a top level that is not an object, an unknown section, key or
  software, a wrong type, a relative `workdir`, two sections for the same
  software, or a file that does not exist raise `ConfigurationError`. The file is
  read once per path; `amac.reset_configuration()` reads it again.
- For a software with `REQUIRES_EXECUTABLE` (every `FileIOSoftware` by default)
  running through the AMAC path, `execute()` raises `ExecutableNotFoundError`
  before creating any directory when no source gives an executable (the message
  lists the sources to set), when it is not an absolute path, or when it is not an
  executable file. The executable used is recorded in `ctx.metadata["executable"]`
  (`{"path": ..., "source": ...}`).
- `amac.which("DFTB+")` shows which executable the configuration file gives;
  `amac.which("DFTB+", config=path)` reads the file of your choice.

```python
amac.configure(timeout=600, validate="warn")  # every software
amac.configure(software="DFTB+", driver="auto")  # this software only
configured = amac.calculator(
    parameters={
        "method": "TIGHT_BINDING",
        "method_args": {"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
        "parameters": {"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
    },
    platform="DFTB+",
    timeout=60,  # wins over configure()
)
assert configured.exec_spec.timeout == 60
assert configured.validate == "warn"
amac.reset_configuration()
```

### Saving a calculator

`calc.to_dict()` returns the software, the spec, the execution settings (with the
requested driver) and the handlers; `AMAC.from_dict(data)` rebuilds the calculator.

- The values of `exec_spec.env` are replaced by `"***"` unless
  `to_dict(mask_secrets=False)`; `from_dict` drops masked variables with a warning,
  to be passed again with `execute(env=...)`.
- Handlers are stored as `"module:qualname"` references when their function can be
  imported again (software handlers and module-level custom functions, with the
  name of a `(name, callable)` tuple). Lambdas, local functions and functions of
  `__main__` are left out with a warning. `from_dict` imports them again and sets
  them with `skip_incompatible=True`, since the driver selected on another machine
  may differ.
- **Security:** `from_dict` imports the modules named in the data. Only load files
  you trust.

### Storing results

`calc.store(filename)` writes a JSON file (`.json` is appended when missing) and
`amac.load(filename)` reads it back as a list of `Result`:

```json
{
    "format": "amac-results",
    "format_version": 1,
    "results": [
        {
            "success": true,
            "properties": {
                "energy": -110.960395,
                "forces": {"__ndarray__": [[0.0, 0.0, 0.1]], "dtype": "float64", "shape": [1, 3]}
            },
            "provenance": {"software": "DFTBP", "driver": "amac", "directory": "runs/water", "start": "2026-09-13T12:00:00+00:00", "...": "..."},
            "errors": [{"type": "HandlerError", "message": "...", "handler": "broken"}]
        }
    ]
}
```

- numpy arrays keep their dtype and shape; numpy scalars become Python numbers;
  `Path` becomes a string; `ase.Atoms` is restored; complex numbers and unknown
  types raise `TypeError`.
- The provenance of each image holds `amac_version`, `software`,
  `software_version`, `driver`, `driver_version`, `driver_fallback`, `image`,
  `spec`, `exec_spec`, `validated`, `reprocessed`, `directory`, `outdir` (the copy,
  or `null`), `hostname`, `start`, `end` (ISO 8601, UTC), `duration` and `atoms`
  (symbols, positions, cell, pbc, initial charges and magnetic moments; `info`,
  constraints and calculators are not stored). Files written before `directory` and
  `outdir` existed still load.
- The values of `exec_spec.env` are replaced by `"***"`; other fields, such as
  `executable` or `workdir`, are stored as they are.
- Errors are reloaded as dicts (`type`, `message`, plus `handler` and
  `missing_files` for handler errors) and contexts as `None`.

```python
path = calc.store("concepts-results")
[reloaded] = amac.load(path)
assert reloaded.errors[0]["handler"] == "broken"
print(amac.reprocess(reloaded, [dftbplus.forces]).properties)  # {'forces': array(...)}
```

### Canonical catalog

`catalog/`, at the repository root, names methods, modules and options independently
of any software (`B3LYP`, `DFTB2`, `GEOMETRY_OPTIMISATION`, `D3(BJ)`, ...), with their
aliases. Each top-level entry has its own directory,
`catalog/<methods|modules|options>/<slug>/`, holding `entry.json` and a `README.md`
(summary and references). Each `doc.json` links its nodes to these names with
`CANONICAL`. Formats are described in `CATALOG_SCHEMA.md` and in the `CANONICAL`
section of `DOC_SCHEMA.md`; the `catalog-curator` agent (`.claude/agents/`) adds new
entries.

## Adding a software

1. **Create its package** `amac/assets/<software>/`, named after the software in
   lowercase (`dftbplus`, `demonnano`), and **describe it** in
   its `doc.json`, following [`DOC_SCHEMA.md`](DOC_SCHEMA.md): syntax
   family, modules, methods, parameters, output files. A future PySCF package keeps
   the name `amac.assets.pyscf`: imports are absolute, so `import pyscf` inside it
   still designates the library, which is only imported by the software module.

2. **Write the input.** The composer is `composer_cls` when set, otherwise the one of
   the `SYNTAX` of the `doc.json`. The concrete `KEYWORD_BLOCK`, `TREE`, `NAMELIST`
   and `FLAT` composers are not implemented yet, so a new software currently brings
   its own composer, rendering the intermediate tree:

   ```python
   from amac.parameter.composer import Composer


   class MySoftComposer(Composer):
       def compose(self, spec, schema, atoms, exec_spec, tree=None):
           # tree is the one AMAC already built for this image; build_tree() only
           # translates the spec when it is None (composer called outside a run).
           tree = self.build_tree(spec, schema, exec_spec, tree)
           return {schema.input["FILENAME"]: render(tree, atoms)}
   ```

   The composer works on that tree in place: what it completes, such as the
   options the software needs for its results to be read back, ends up in
   `ctx.metadata["input_tree"]` and therefore in the provenance.

3. **Subclass `FileIOSoftware`** and register it:

   ```python
   from pathlib import Path

   from amac.engine.registry import register_software
   from amac.engine.software import FileIOSoftware


   @register_software
   class MySoft(FileIOSoftware):
       NAME = "MYSOFT"  # canonical name, looked up case-insensitively
       ALIASES = ("my-soft",)
       DOC = Path(__file__).with_name("doc.json")
       composer_cls = MySoftComposer  # None: dispatch on the doc.json SYNTAX

       def command(self, ctx):
           executable = self.require_executable(ctx.exec_spec).path
           return [executable, "input.inp"]

       def stdout_file(self, ctx):
           return Path("output.log")  # for programs writing on stdout
   ```

   A software driven through a Python API subclasses `InProcessSoftware` instead:
   `build(ctx)` creates the native objects in `ctx.objects`, `compute(ctx)` runs
   them, `collect(ctx)` stores what the handlers need. See
   `amac/assets/demonnano/demonnano.py`.

4. **Declare its handlers** in a module imported *after* the software, since
   `@handler` resolves the software through the registry at import time, and expose
   them in the `__init__.py` of the package (`from amac.assets import mysoft`, then
   `mysoft.energy`):

   ```python
   from amac.assets.mysoft.mysoft import MySoft  # registers MYSOFT first
   from amac.engine.handlers import handler


   @handler(software="MYSOFT", requires_files=("output.log",))
   def energy(ctx):
       return parse_energy(ctx.files["output.log"].read_text())
   ```

   Produced files are listed in `ctx.files` from the glob patterns of
   `OUTPUT.FILES` in the `doc.json`. Use the common result names, so that the same
   property has the same key whatever the software:

   | Handler | Result |
   |---|---|
   | `energy` | Total energy |
   | `forces` | Forces on the atoms, shape `(n, 3)` |
   | `dipole` | Dipole moment, shape `(3,)` |
   | `charges` | Atomic charges, shape `(n,)` |
   | `final_geometry` | Last geometry of an optimisation, as `ase.Atoms` |
   | `frequencies` | Vibrational frequencies |
   | `hessian` | Hessian matrix |

   Handlers return ASE units (eV, Å): the normalized dataclass of a software keeps
   the units of the program, and the handlers convert them. DFTB+ and deMonNano
   follow this rule today; the other packages will as they are written.

5. **Import the software module** explicitly in `amac/assets/__init__.py` (there is
   no filesystem scan).

Two software are registered today. DFTB+ (`amac/assets/dftbplus/`) is the complete
example of a file-based software (`composer.py`, `parser.py`, `handlers.py`,
`drivers.py`), and deMonNano (`amac/assets/demonnano/`) that of an in-process
software (`demonnano.py`, `parser.py`, `handlers.py`), driven by the `deMonPy`
library.

## Using a dedicated library

Some programs have a Python library: the DFTB+ API, `deMonPy` for deMonNano,
AbiPy for Abinit. A software may declare *drivers* (`Software.DRIVERS`) that use such a
library for some phases, while the AMAC path (composer, local executor, handlers)
stays available everywhere.

| `driver=` | Behaviour |
|---|---|
| `"amac"` (default) | AMAC path only, reproducible from one machine to another |
| `"auto"` | First driver of `Software.DRIVERS` whose library is installed, whose environment is compatible and which accepts `raw`; otherwise `"amac"`, with the reason of each discarded driver in `provenance["driver_fallback"]` |
| `"<name>"` | That driver: `DriverUnavailableError`, with the `pip install` command, when its library is missing or its environment incompatible; `ValueError` for an unknown name |

- Libraries are never required. The known ones are declared as optional
  dependencies in `pyproject.toml` (`dftbplus`); a driver imports its library
  inside its phases only, so `import amac` works without them.
- `amac.configure(software=..., driver=...)` only checks the name; availability is
  checked when the calculator is created.
- The driver is chosen once, when the calculator is created. There is no fallback
  during a run: an exception in a driver phase is a `RunError` (the original
  exception chained), or a `Result(success=False)` with `raise_on_error=False`.
- Each phase (`prepare`, `run`, `collect`) goes through the driver when it is in
  `Driver.PHASES`, otherwise through the software. A driver finds the intermediate
  tree of the spec in `ctx.metadata["input_tree"]` (when the software has a
  `doc.json`), keeps its files in `ctx.directory`, fills `ctx.files` when it
  collects, and stores native objects in `ctx.objects`.
- `raw` keywords need `SUPPORTS_RAW` from a driver that prepares the input: an
  explicit driver raises `ValidationError`, `"auto"` discards it.
- A driver running the program gets `cpu`, `ram`, `timeout`, `env` and the resolved
  executable from `execution_settings()`; every setting set by the user but absent
  from `SUPPORTED_SETTINGS` emits one warning per `execute()`.
- Handlers reading native objects declare `@handler(..., drivers=("<name>",))`.
  They are checked against the selected driver, and refused after an `"auto"`
  fallback, with its reason; `skip_incompatible=True` discards them instead.
- The provenance records `driver`, `driver_version` and `driver_fallback`;
  `to_dict()` keeps the requested driver.

Sketch of a driver, modelled on `HsdDriver` in
`amac/assets/dftbplus/drivers.py`:

```python
from amac.engine.drivers import Driver


class MyLibDriver(Driver):
    NAME = "mylib"
    REQUIRES = ("mylib",)  # found with importlib, never imported at selection
    DISTRIBUTION = "mylib"  # pip package, for version() and error messages
    PHASES = frozenset({"run", "collect"})  # prepare stays on the AMAC path
    SUPPORTED_SETTINGS = frozenset({"cpu", "executable"})

    def check_environment(self, software):
        return None  # or the reason why this environment cannot be used

    def run(self, software, ctx):
        import mylib  # imported here only

        settings = self.execution_settings(software, ctx.exec_spec)
        ctx.objects["mylib"] = mylib.run(ctx.directory, settings["cpu"])

    def collect(self, software, ctx):
        output = ctx.directory / "output.log"
        ctx.files["output.log"] = output


class MySoft(FileIOSoftware):
    DRIVERS = (MyLibDriver,)  # order of preference for driver="auto"
```

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
