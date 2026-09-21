# Describing a calculation

[← README](../README.md)

How a calculation is described, and how AMAC checks it against the `doc.json` of the software.

## Calculation spec

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

## Validation

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
