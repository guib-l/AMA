# Using a dedicated library

[← README](../README.md)

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
