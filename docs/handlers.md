# Handlers

[← README](../README.md)

Handlers turn the files of a run into the properties of a result.

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
