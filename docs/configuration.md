# Configuration and executables

[← README](../README.md)

AMAC reads no environment variable: the machine configuration is the JSON file given to the calculator or to the process.

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
