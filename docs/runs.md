# Runs, results and reprocessing

[← README](../README.md)

Where the files go, what happens when a run fails, and how a calculator and its results are saved and reloaded.

## Runs, directories and failures

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

## Reprocessing

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

## Saving a calculator

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

## Storing results

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
