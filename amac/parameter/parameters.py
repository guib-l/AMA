"""Software-independent calculation and execution specifications."""

import copy
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Self

DEFAULT_MODULE = "SINGLE_POINT"
HANDLER_ERRORS = ("collect", "raise")

type RawKeywords = str | list[str] | dict[str, Any] | None


def _check_keys(cls: type, data: dict[str, Any]) -> None:
    if unknown := data.keys() - {f.name for f in fields(cls)}:
        raise ValueError(f"Unknown {cls.__name__} keys: {sorted(unknown)}")


def _upper_keys(mapping: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise TypeError(f"Parameter keys must be str, got {key!r}")
        if key.upper() in result:
            raise ValueError(f"Duplicate parameter after normalisation: {key!r}")
        result[key.upper()] = value
    return result


@dataclass(frozen=True)
class CalculationSpec:
    """Canonical description of a calculation.

    ``method``, ``module`` and the top-level keys of ``parameters`` are upper-cased.
    Nested keys, ``method_args``, ``module_args`` and ``raw`` are kept as given;
    aliases are not resolved here.

    Attributes:
        method: Method family, e.g. ``"DFT"``.
        method_args: Options of the method.
        module: Run type, e.g. ``"SINGLE_POINT"``.
        module_args: Options of the module.
        parameters: General options.
        raw: Software keywords passed unchanged to the composer.

    Raises:
        TypeError: If a field has the wrong type.
        ValueError: If two ``parameters`` keys only differ by case.
    """

    method: str
    method_args: dict[str, Any] = field(default_factory=dict)
    module: str = DEFAULT_MODULE
    module_args: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    raw: RawKeywords = None

    def __post_init__(self) -> None:
        for name in ("method", "module"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a str, got {type(value).__name__}")
            object.__setattr__(self, name, value.upper())
        for name in ("method_args", "module_args", "parameters"):
            value = getattr(self, name)
            if not isinstance(value, dict):
                raise TypeError(f"{name} must be a dict, got {type(value).__name__}")
            object.__setattr__(self, name, copy.deepcopy(value))
        object.__setattr__(self, "parameters", _upper_keys(self.parameters))
        object.__setattr__(self, "raw", copy.deepcopy(self.raw))

    @classmethod
    def from_kwargs(
        cls,
        method: str,
        method_args: dict[str, Any] | None = None,
        module: str = DEFAULT_MODULE,
        module_args: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
        raw: RawKeywords = None,
    ) -> Self:
        """Build a spec from keyword arguments, ``None`` meaning an empty dict."""
        return cls(
            method=method,
            method_args={} if method_args is None else method_args,
            module=module,
            module_args={} if module_args is None else module_args,
            parameters={} if parameters is None else parameters,
            raw=raw,
        )

    @classmethod
    def from_dict(cls, parameters: dict[str, Any]) -> Self:
        """Build a spec from a dict with the same keys as :meth:`from_kwargs`.

        Raises:
            ValueError: If ``parameters`` contains unknown keys.
        """
        _check_keys(cls, parameters)
        return cls.from_kwargs(**parameters)

    def to_dict(self) -> dict[str, Any]:
        """Return the spec as a plain dict accepted by :meth:`from_dict`."""
        return asdict(self)


@dataclass(frozen=True)
class ExecutionSpec:
    """How and where a calculation is run.

    Attributes:
        cpu: Number of cores.
        ram: Memory in MB.
        workdir: Root working directory.
        outdir: Directory where results are copied.
        timeout: Maximum duration in seconds.
        label: Name of the calculation, used for its directory.
        executable: Software executable.
        env: Additional environment variables.
        raise_on_error: Whether a failed calculation raises.
        keep_files: Whether produced files are kept.
        overwrite: Whether a non-empty run directory may be reused.
        handler_errors: ``"collect"`` records handler failures and runs the
            other handlers, ``"raise"`` raises the first failure.
        driver: Requested driver, e.g. ``"amac"`` or ``"auto"``.

    Raises:
        TypeError: If ``driver`` is not a str.
        ValueError: If ``handler_errors`` is not in ``HANDLER_ERRORS``.
    """

    cpu: int = 1
    ram: int | None = None
    workdir: Path = Path(".")
    outdir: Path | None = None
    timeout: float | None = None
    label: str | None = None
    executable: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    raise_on_error: bool = True
    keep_files: bool = True
    overwrite: bool = False
    handler_errors: str = "collect"
    driver: str = "amac"

    def __post_init__(self) -> None:
        object.__setattr__(self, "workdir", Path(self.workdir))
        if self.outdir is not None:
            object.__setattr__(self, "outdir", Path(self.outdir))
        object.__setattr__(self, "env", dict(self.env))
        if not isinstance(self.driver, str):
            raise TypeError(f"driver must be a str, got {type(self.driver).__name__}")
        if self.handler_errors not in HANDLER_ERRORS:
            raise ValueError(
                f"handler_errors must be one of {', '.join(HANDLER_ERRORS)}, "
                f"got {self.handler_errors!r}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build a spec from the output of :meth:`to_dict`.

        Raises:
            ValueError: If ``data`` contains unknown keys.
        """
        _check_keys(cls, data)
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Return the spec as a plain dict, paths converted to str."""
        data = asdict(self)
        data["workdir"] = str(self.workdir)
        if self.outdir is not None:
            data["outdir"] = str(self.outdir)
        return data
