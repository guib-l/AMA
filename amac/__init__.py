"""AMAC: one syntax to run quantum chemistry calculations with any software.

Two ways to run a calculation:

- :class:`AMAC` is fully explicit: it ignores the defaults of :func:`configure`;
- the facade (:func:`configure`, :func:`calculator`, :func:`run`) keeps module-level
  state: the configured defaults and a *current calculator*. This state is global to
  the process and not thread-safe.

AMAC reads no environment variable. The machine configuration file
(``amac.config``) is given explicitly, to one calculator with
``AMAC(config=...)`` or to the whole process with :func:`set_config`, which
:func:`configure` also accepts as ``config=``; without any of them AMAC has no
configuration at all.

Executable resolution, first source set wins:

1. explicit ``executable=``, then :func:`configure` (facade only);
2. ``executable`` of ``[software.<NAME>]`` in the configuration file.

AMAC never searches ``PATH``: the executable must be an absolute path (``~`` is
expanded). Source 2 is only read by ``Software.locate_executable``, when the
command is built, so both paths share the same rule. The ``env`` of the
configuration file is added to the runs of the software, below ``exec_spec.env``.
:func:`which` shows which executable the configuration file gives.

Where the files are written is always ``workdir``, given to :class:`AMAC`, to
:func:`configure`, to one ``execute()`` call, or as the ``workdir`` of the
configuration file; it is never taken from the environment. ``AMAC.workdir``
gives the root as an absolute path,
``AMAC.directories`` the run directories of the last call, and each run logs its
directory on the ``"amac.amac"`` logger at ``INFO``. As a library AMAC installs no
handler, so that line appears once the program calls ``logging.basicConfig()``.
"""

from __future__ import annotations

import difflib
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

from amac.amac import AMAC, _check_names, reprocess
from amac.config import clear_config_cache, set_config
from amac.engine.drivers import validate_driver_name
from amac.engine.registry import get_software
from amac.exceptions import (
    AMACError,
    ConfigurationError,
    DriverUnavailableError,
    ExecutableNotFoundError,
    HandlerError,
    RunError,
    SoftwareNotFoundError,
    ValidationError,
)
from amac.ios.store import load_results as load
from amac.parameter.parameters import CalculationSpec, ExecutionSpec
from amac.parameter.validator import MODES

if TYPE_CHECKING:
    from ase import Atoms

    from amac.engine.context import Result
    from amac.engine.software import ExecutableLocation

__version__ = "0.1.1"

# A library never writes on its own: the runs are logged, printing is the caller's.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "AMAC",
    "AMACError",
    "ConfigurationError",
    "DriverUnavailableError",
    "ExecutableNotFoundError",
    "HandlerError",
    "RunError",
    "SoftwareNotFoundError",
    "ValidationError",
    "__version__",
    "calculator",
    "configure",
    "load",
    "reprocess",
    "reset_configuration",
    "run",
    "set_config",
    "which",
]

_CALC_KEYS = frozenset(f.name for f in fields(CalculationSpec))
_EXEC_FIELDS = frozenset(f.name for f in fields(ExecutionSpec))
_PER_SOFTWARE = frozenset({"executable", "driver"})


@dataclass
class _FacadeState:
    """Global state of the facade.

    Attributes:
        defaults: Execution defaults and ``validate`` of every software.
        software: Execution defaults, ``validate``, executable and driver per
            canonical name.
        current: Calculator used by :func:`run` when ``calc`` is not given.
    """

    defaults: dict[str, Any] = field(default_factory=dict)
    software: dict[str, dict[str, Any]] = field(default_factory=dict)
    current: AMAC | None = None


_STATE = _FacadeState()


def configure(
    software: str | None = None,
    executable: str | None = None,
    driver: str | None = None,
    validate: str | None = None,
    config: str | Path | None = None,
    **defaults: Any,
) -> None:
    """Set defaults used by :func:`calculator`; successive calls add up.

    Without ``software``, ``validate`` and ``defaults`` apply to every software.
    With it, ``executable``, ``driver``, ``validate`` and ``defaults`` apply to this
    software only and win over the global defaults. Keyword arguments of
    :func:`calculator` win over both. :class:`AMAC` created directly ignores this
    configuration, and existing calculators are not changed.

    ``config`` is the exception: it calls :func:`set_config`, which every
    calculator of the process uses, including :class:`AMAC` created directly and
    the existing ones, unless they were given their own ``config=``.

    Args:
        software: Name or alias of a registered software.
        executable: Executable of ``software``.
        driver: Driver of ``software``, e.g. ``"auto"``. Only its name is
            checked here; its availability is checked by :func:`calculator`.
        validate: Validation mode given to the calculators: ``"strict"``,
            ``"warn"`` or ``"off"``.
        config: Configuration file of the process (see :func:`set_config`);
            ``None`` leaves it unchanged.
        **defaults: ``ExecutionSpec`` fields, e.g. ``cpu``, ``ram``, ``workdir``.

    Raises:
        ValueError: If ``executable`` or ``driver`` is given without ``software``,
            or if ``validate``, a value or the driver is invalid.
        TypeError: If a default is not an ``ExecutionSpec`` field; the message
            suggests a close name.
        SoftwareNotFoundError: If ``software`` is not registered.
    """
    if software is None and (executable is not None or driver is not None):
        raise ValueError("executable and driver are set per software: give software=")
    if validate is not None and validate not in MODES:
        raise ValueError(
            f"Unknown validation mode {validate!r}; expected one of {', '.join(MODES)}"
        )
    if config is not None:
        set_config(config)
    _check_names(defaults, _EXEC_FIELDS - _PER_SOFTWARE, _EXEC_FIELDS)
    ExecutionSpec(**defaults)  # Fails early on the values ExecutionSpec checks.
    settings = dict(defaults)
    if validate is not None:
        settings["validate"] = validate
    if software is None:
        _STATE.defaults.update(settings)
        return
    software_cls = get_software(software)
    if executable is not None:
        settings["executable"] = executable
    if driver is not None:
        validate_driver_name(software_cls, driver)
        settings["driver"] = driver
    _STATE.software.setdefault(software_cls.NAME, {}).update(settings)


def reset_configuration() -> None:
    """Forget everything set by :func:`configure` and the configuration file.

    The file of :func:`set_config` is forgotten too, so the process is left
    without any configuration; the current calculator is kept.
    """
    _STATE.defaults.clear()
    _STATE.software.clear()
    set_config(None)
    clear_config_cache()


def which(
    software: str, config: str | Path | None = None
) -> ExecutableLocation | None:
    """Locate the executable of a software, to check an installation.

    The ``executable`` of :func:`configure` is ignored: the only source is the
    configuration file; ``PATH`` is never searched (see
    ``Software.locate_executable``).

    Args:
        software: Name or alias of a registered software.
        config: Configuration file to read; ``None`` uses the one of
            :func:`set_config`.

    Returns:
        The executable and its source, ``None`` when no source gives one. The
        path is not checked.

    Raises:
        SoftwareNotFoundError: If ``software`` is not registered.
        ConfigurationError: If the configuration file is missing or invalid.
    """
    return get_software(software)(config).locate_executable(ExecutionSpec())


def calculator(
    parameters: Mapping[str, Any],
    platform: str,
    handlers: Iterable[Any] | None = None,
    skip_incompatible: bool = False,
    **kwargs: Any,
) -> AMAC:
    """Create a calculator with the configured defaults and make it current.

    Args:
        parameters: Calculation keys only: ``method``, ``method_args``, ``module``,
            ``module_args``, ``parameters``, ``raw``.
        platform: Name or alias of the software.
        handlers: Handlers given to :meth:`AMAC.handler_properties`, if any.
        skip_incompatible: Passed to :meth:`AMAC.handler_properties`.
        **kwargs: ``config``, ``validate`` and ``ExecutionSpec`` fields (``cpu``,
            ``workdir``, ``executable``, ``driver``, ...); they win over
            :func:`configure`.

    Returns:
        The calculator, now current.

    Raises:
        TypeError: If ``parameters`` is not a mapping, if a calculation key is
            given in ``kwargs``, or if ``AMAC`` rejects an argument.
        ValueError: If a key of ``parameters`` is not a calculation key; an
            execution setting is pointed to ``kwargs``, another key gets a
            suggestion.
        SoftwareNotFoundError: If ``platform`` is not registered.
        DriverUnavailableError: If the requested driver cannot be used.
    """
    if not isinstance(parameters, Mapping):
        raise TypeError(
            f"parameters must be a mapping, got {type(parameters).__name__}"
        )
    _check_parameters(parameters)
    if misplaced := sorted(kwargs.keys() & _CALC_KEYS):
        raise TypeError(
            "Calculation keys go in parameters, not in keyword arguments: "
            f"{', '.join(misplaced)}"
        )
    software_cls = get_software(platform)
    settings = {
        **_STATE.defaults,
        **_STATE.software.get(software_cls.NAME, {}),
        **kwargs,
    }
    calc = AMAC(platform=platform, **parameters, **settings)
    if handlers is not None:
        calc.handler_properties(*handlers, skip_incompatible=skip_incompatible)
    _STATE.current = calc
    return calc


def run(
    image: Atoms | Iterable[Any],
    calc: AMAC | None = None,
    handlers: Iterable[Any] | None = None,
    skip_incompatible: bool = False,
    **kwargs: Any,
) -> Result | list[Result]:
    """Run a calculator on one or several images.

    Args:
        image: Images accepted by :meth:`AMAC.execute`.
        calc: Calculator to use, the current one by default.
        handlers: Handlers for this call only; the handlers of the calculator are
            restored afterwards, even if the call raises. ``None`` keeps them.
        skip_incompatible: Passed to :meth:`AMAC.handler_properties` with
            ``handlers``.
        **kwargs: Overrides of :meth:`AMAC.execute`.

    Returns:
        The result of :meth:`AMAC.execute`.

    Raises:
        AMACError: If ``calc`` is not given and there is no current calculator.
    """
    target = _STATE.current if calc is None else calc
    if target is None:
        raise AMACError(
            "No current calculator: create one with amac.calculator() or pass calc="
        )
    if handlers is None:
        return target.execute(image, **kwargs)
    previous = target.handlers
    try:
        target.handler_properties(*handlers, skip_incompatible=skip_incompatible)
        return target.execute(image, **kwargs)
    finally:
        target.handlers = previous


def _check_parameters(parameters: Mapping[str, Any]) -> None:
    for key in parameters:
        if key in _CALC_KEYS:
            continue
        if key in _EXEC_FIELDS or key == "validate":
            raise ValueError(
                f"{key!r} is not a calculation key: pass it as a keyword argument "
                "of calculator()"
            )
        close = difflib.get_close_matches(str(key), sorted(_CALC_KEYS), n=1)
        if close:
            hint = f"did you mean {close[0]!r}?"
        else:
            hint = f"accepted: {', '.join(sorted(_CALC_KEYS))}"
        raise ValueError(f"Unknown calculation key {key!r}; {hint}")
