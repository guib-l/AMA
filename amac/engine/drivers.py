"""Optional drivers running some phases of a calculation with a dedicated library.

A software may declare :class:`Driver` subclasses in ``Software.DRIVERS``. A driver
uses a Python library of the program (e.g. OPI for ORCA) for some of the
``prepare``, ``run`` and ``collect`` phases; the other phases follow the AMAC path
of the ``Software``. Libraries are never required: :meth:`Driver.is_available`
looks for them without importing them, and a driver imports its library inside its
phases only, so ``import amac`` works without any of them.

:func:`select_driver` chooses the driver once, when the calculator is created: no
fallback happens during a run.
"""

from __future__ import annotations

import importlib.machinery
import importlib.metadata
import importlib.util
import sys
from abc import ABC
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any, ClassVar

from amac.exceptions import DriverUnavailableError, ValidationError
from amac.parameter.parameters import ExecutionSpec

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

    from amac.engine.context import RunContext
    from amac.engine.software import Software
    from amac.parameter.parameters import CalculationSpec

AMAC_DRIVER = "amac"
AUTO_DRIVER = "auto"
PHASES = frozenset({"prepare", "run", "collect"})
SETTINGS = ("cpu", "ram", "timeout", "env", "executable")

_DEFAULT_CPU = next(f.default for f in fields(ExecutionSpec) if f.name == "cpu")


class Driver(ABC):
    """Base class of the library drivers.

    :func:`select_driver` creates one instance per calculator; its phase methods
    receive the software instance and the run context of each image.

    In ``ctx``, a driver finds the intermediate tree of the spec in
    ``ctx.metadata["input_tree"]`` (when the software has a ``doc.json``) and the
    execution settings through :meth:`execution_settings`. It keeps its files in
    ``ctx.directory``, fills ``ctx.files`` when it collects, and stores the native
    objects of the library in ``ctx.objects``.

    Attributes:
        NAME: Name given to ``driver=``, compared ignoring case; ``"amac"`` and
            ``"auto"`` are reserved.
        REQUIRES: Python modules the driver needs, e.g. ``("opi",)``.
        DISTRIBUTION: pip package providing them, used by :meth:`version` and in
            error messages.
        PHASES: Non-empty subset of ``{"prepare", "run", "collect"}`` done by the
            driver.
        SUPPORTS_RAW: Whether the driver injects ``CalculationSpec.raw`` when it
            prepares the input.
        SUPPORTED_SETTINGS: Subset of :data:`SETTINGS` applied by the driver when
            it runs the program.

    Raises:
        TypeError: When a subclass is defined, if an attribute is invalid or a
            phase of ``PHASES`` is not implemented.
    """

    NAME: ClassVar[str] = ""
    REQUIRES: ClassVar[tuple[str, ...]] = ()
    DISTRIBUTION: ClassVar[str | None] = None
    PHASES: ClassVar[frozenset[str]] = frozenset()
    SUPPORTS_RAW: ClassVar[bool] = False
    SUPPORTED_SETTINGS: ClassVar[frozenset[str]] = frozenset()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        name = cls.__name__
        if (
            not isinstance(cls.NAME, str)
            or not cls.NAME
            or cls.NAME.casefold() in (AMAC_DRIVER, AUTO_DRIVER)
        ):
            raise TypeError(
                f"{name}.NAME must be a non-empty str other than 'amac' and 'auto'"
            )
        if isinstance(cls.REQUIRES, str) or not all(
            isinstance(module, str) and module for module in cls.REQUIRES
        ):
            raise TypeError(f"{name}.REQUIRES must be a tuple of module names")
        cls.REQUIRES = tuple(cls.REQUIRES)
        cls.PHASES = frozenset(cls.PHASES)
        if not cls.PHASES or not cls.PHASES <= PHASES:
            raise TypeError(
                f"{name}.PHASES must be a non-empty subset of {sorted(PHASES)}"
            )
        missing = sorted(p for p in cls.PHASES if getattr(cls, p) is getattr(Driver, p))
        if missing:
            raise TypeError(f"{name} does not implement: {', '.join(missing)}")
        cls.SUPPORTED_SETTINGS = frozenset(cls.SUPPORTED_SETTINGS)
        if not cls.SUPPORTED_SETTINGS <= frozenset(SETTINGS):
            raise TypeError(
                f"{name}.SUPPORTED_SETTINGS must be a subset of {list(SETTINGS)}"
            )

    def is_available(self) -> bool:
        """Return whether every module of ``REQUIRES`` can be found."""
        return not self.missing_modules()

    def missing_modules(self) -> list[str]:
        """Return the modules of ``REQUIRES`` that cannot be found.

        Nothing is imported: a top-level module is looked for with
        ``importlib.util.find_spec``, and a submodule in the locations of its
        parent's spec, with the standard path-based finder, so that its parent
        package is not imported either.
        """
        return [module for module in self.REQUIRES if _find_spec(module) is None]

    def version(self) -> str | None:
        """Return the installed version of ``DISTRIBUTION``, ``None`` if unknown."""
        if self.DISTRIBUTION is None:
            return None
        try:
            return importlib.metadata.version(self.DISTRIBUTION)
        except importlib.metadata.PackageNotFoundError:
            return None

    def check_environment(self, software: Software) -> str | None:
        """Return why the driver cannot be used with ``software``, ``None`` if it can.

        Called by :func:`select_driver` once the modules are found, e.g. to check
        the version of the program. A reason is returned rather than raised so
        that ``"auto"`` can record it and try the next driver. Default: ``None``.
        """
        return None

    def execution_settings(
        self, software: Software, exec_spec: ExecutionSpec
    ) -> dict[str, Any]:
        """Return the settings to give to the library.

        Returns:
            ``cpu``, ``ram``, ``timeout``, ``env`` and ``executable``. ``env`` is
            ``software.configured_env()`` updated with ``exec_spec.env``;
            ``executable`` is resolved by ``software.resolve_executable``.
        """
        return {
            "cpu": exec_spec.cpu,
            "ram": exec_spec.ram,
            "timeout": exec_spec.timeout,
            "env": {**software.configured_env(), **exec_spec.env},
            "executable": software.resolve_executable(exec_spec),
        }

    def ignored_settings(
        self, software: Software, exec_spec: ExecutionSpec
    ) -> list[str]:
        """Return the settings set by the user but absent from ``SUPPORTED_SETTINGS``.

        A setting is set when it differs from its default: ``cpu`` other than 1,
        ``ram``, ``timeout`` or executable not ``None``, ``env`` not empty.
        """
        settings = self.execution_settings(software, exec_spec)
        return [
            name
            for name in SETTINGS
            if name not in self.SUPPORTED_SETTINGS and _is_set(name, settings[name])
        ]

    def prepare(self, software: Software, ctx: RunContext) -> None:
        """Write the input of ``ctx`` with the library."""
        raise NotImplementedError(f"{type(self).__name__} does not implement prepare")

    def run(self, software: Software, ctx: RunContext) -> None:
        """Run the calculation of ``ctx`` with the library."""
        raise NotImplementedError(f"{type(self).__name__} does not implement run")

    def collect(self, software: Software, ctx: RunContext) -> None:
        """Fill ``ctx.files`` and ``ctx.objects`` from the results of the library.

        A driver that collects fills ``ctx.files``, so that ``requires_files``
        still applies, and stores the normalized dataclass of the software in
        ``ctx.objects[OUTPUT_KEY]`` (``amac.engine.context.OUTPUT_KEY``), in the
        units of the program. Native objects of the library go in other keys of
        ``ctx.objects``. Handlers read the dataclass through
        ``amac.engine.context.cached_output``, which rebuilds it from the files
        when the entry is absent (AMAC path, reprocessing).
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement collect")


@dataclass(frozen=True)
class DriverSelection:
    """Outcome of :func:`select_driver`.

    Attributes:
        name: Driver actually used, ``"amac"`` for the AMAC path.
        driver: Driver instance, ``None`` for the AMAC path.
        fallback: Why ``"auto"`` fell back to ``"amac"``, ``None`` otherwise.
    """

    name: str = AMAC_DRIVER
    driver: Driver | None = None
    fallback: str | None = None


def select_driver(
    software_cls: type[Software],
    requested: str,
    spec: CalculationSpec | None = None,
) -> DriverSelection:
    """Select the driver of a calculation.

    - ``"amac"`` selects the AMAC path.
    - ``"auto"`` selects the first driver of ``software_cls.DRIVERS``, in
      declaration order, whose modules are found, whose ``check_environment``
      passes and which accepts the raw keywords of ``spec``. Otherwise it selects
      the AMAC path, without warning, and ``fallback`` gives the reason of each
      discarded driver.
    - Another name selects that driver.

    Names ignore case.

    Args:
        software_cls: Software of the calculation.
        requested: ``"amac"``, ``"auto"`` or the ``NAME`` of a driver.
        spec: Calculation; when given and ``spec.raw`` is set, a driver doing
            ``prepare`` without ``SUPPORTS_RAW`` is refused.

    Returns:
        The selection, holding a new driver instance.

    Raises:
        TypeError: If ``requested`` is not a str.
        ValueError: If ``requested`` names no driver of the software; the message
            lists the accepted names.
        DriverUnavailableError: If the requested driver misses modules (the message
            gives the pip command) or rejects the environment.
        ValidationError: If the requested driver cannot use the raw keywords of
            ``spec``.
    """
    key = _check_name(software_cls, requested)
    if key == AMAC_DRIVER:
        return DriverSelection()
    software = software_cls()
    if key == AUTO_DRIVER:
        reasons = []
        for driver_cls in software_cls.DRIVERS:
            driver = driver_cls()
            reason = _unavailable_reason(driver, software) or _raw_reason(driver, spec)
            if reason is None:
                return DriverSelection(driver.NAME, driver)
            reasons.append(f"{driver.NAME}: {reason}")
        no_driver = f"{software_cls.NAME} declares no library driver"
        return DriverSelection(fallback="; ".join(reasons) or no_driver)
    driver_cls = next(d for d in software_cls.DRIVERS if d.NAME.casefold() == key)
    driver = driver_cls()
    if reason := _unavailable_reason(driver, software):
        raise DriverUnavailableError(
            f"Driver {driver.NAME!r} cannot be used with {software_cls.NAME}: {reason}"
        )
    if reason := _raw_reason(driver, spec):
        raise ValidationError(
            f"Driver {driver.NAME!r} {reason}; use driver='amac' to write them"
        )
    return DriverSelection(driver.NAME, driver)


def validate_driver_name(software_cls: type[Software], requested: str) -> None:
    """Check that ``requested`` names a driver of the software, without selecting it.

    Raises:
        TypeError: If ``requested`` is not a str.
        ValueError: If ``requested`` is not ``"amac"``, ``"auto"`` or the ``NAME`` of
            a driver of ``software_cls.DRIVERS``.
    """
    _check_name(software_cls, requested)


def _check_name(software_cls: type[Software], requested: Any) -> str:
    if not isinstance(requested, str):
        raise TypeError(f"driver must be a str, got {type(requested).__name__}")
    key = requested.casefold()
    names = [driver.NAME for driver in software_cls.DRIVERS]
    if key in (AMAC_DRIVER, AUTO_DRIVER) or key in {n.casefold() for n in names}:
        return key
    available = ", ".join([AMAC_DRIVER, AUTO_DRIVER, *names])
    raise ValueError(
        f"Unknown driver {requested!r} for {software_cls.NAME}. Available: {available}"
    )


def _unavailable_reason(driver: Driver, software: Software) -> str | None:
    if missing := driver.missing_modules():
        install = f" (pip install {driver.DISTRIBUTION})" if driver.DISTRIBUTION else ""
        return f"missing Python module {', '.join(missing)}{install}"
    return driver.check_environment(software)


def _raw_reason(driver: Driver, spec: CalculationSpec | None) -> str | None:
    if (
        spec is not None
        and spec.raw is not None
        and "prepare" in driver.PHASES
        and not driver.SUPPORTS_RAW
    ):
        return "does not support raw keywords"
    return None


def _is_set(name: str, value: Any) -> bool:
    if name == "cpu":
        return value != _DEFAULT_CPU
    if name == "env":
        return bool(value)
    return value is not None


def _find_spec(name: str) -> ModuleSpec | None:
    """Return the spec of ``name`` without importing it or its parent packages."""
    if name in sys.modules:
        module = sys.modules[name]
        if module is None:
            return None
        return module.__spec__ or importlib.machinery.ModuleSpec(name, None)
    parent = name.rpartition(".")[0]
    if not parent:
        return importlib.util.find_spec(name)
    parent_spec = _find_spec(parent)
    if parent_spec is None or parent_spec.submodule_search_locations is None:
        return None
    locations = list(parent_spec.submodule_search_locations)
    return importlib.machinery.PathFinder.find_spec(name, locations)
