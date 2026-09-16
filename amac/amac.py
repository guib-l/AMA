"""AMAC calculator: one calculation run on one or several geometries.

The class only orchestrates the software-independent chain ``spec → validation →
prepare → run → collect → handlers → results``. Everything specific to a software
lives in its ``Software`` class, its ``doc.json``, its drivers and its handlers.
"""

from __future__ import annotations

import copy
import difflib
import importlib
import socket
import time
import warnings
from collections.abc import Collection, Iterable, Mapping
from dataclasses import asdict, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from ase import Atoms

from amac.engine.context import Result, RunContext
from amac.engine.drivers import select_driver
from amac.engine.execute import finalize_run_directory, make_run_directory
from amac.engine.handlers import resolve_handlers, run_handlers
from amac.engine.registry import get_software
from amac.exceptions import RunError, ValidationError
from amac.ios.store import store_results
from amac.parameter.composer import inject_resources, translate
from amac.parameter.parameters import DEFAULT_MODULE, CalculationSpec, ExecutionSpec
from amac.parameter.schema import load as load_schema
from amac.parameter.validator import MODES
from amac.parameter.validator import validate as validate_spec

if TYPE_CHECKING:
    from amac.engine.drivers import Driver, DriverSelection
    from amac.engine.handlers import HandlerSpec
    from amac.engine.software import ExecutableLocation, Software
    from amac.parameter.parameters import RawKeywords
    from amac.parameter.schema import Schema
    from amac.parameter.validator import Issue

ENV_MASK = "***"
INPUT_TREE_KEY = "input_tree"
EXECUTABLE_KEY = "executable"
IMAGE_OVERRIDE_KEYS = ("method_args", "module_args", "parameters", "raw")

_EXEC_FIELDS = frozenset(f.name for f in fields(ExecutionSpec))
_INIT_NAMES = (
    "software",
    "platform",
    "method",
    "module",
    "method_args",
    "module_args",
    "parameters",
    "raw",
    "validate",
)
_DICT_KEYS = frozenset({"software", "validate", "spec", "exec_spec"})
_OPTIONAL_DICT_KEYS = frozenset({"handlers"})

type _Image = tuple[Atoms, Mapping[str, Any] | None]


class AMAC:
    """Calculator running one calculation with one software.

    Args:
        method: Method family, e.g. ``"DFT"``.
        software: Name or alias of a registered software.
        module: Run type; ``None`` means ``"SINGLE_POINT"``.
        method_args: Options of the method.
        module_args: Options of the module.
        parameters: General options.
        raw: Software keywords passed unchanged to the composer.
        validate: ``"strict"``, ``"warn"`` or ``"off"`` (see the validator). A
            software without ``doc.json`` cannot be validated: ``"strict"`` raises,
            ``"warn"`` warns, ``"off"`` accepts it silently.
        platform: Alias of ``software``.
        **exec_kwargs: Fields of ``ExecutionSpec`` (``cpu``, ``workdir``, ``driver``,
            ...).

    Attributes:
        spec: Calculation specification.
        exec_spec: Default execution specification.
        software: Software instance.
        driver: Driver selected once from ``exec_spec.driver`` (see
            ``amac.engine.drivers.select_driver``); ``exec_spec`` keeps the
            requested name.
        schema: Schema of the software, ``None`` when it has no ``doc.json``.
        validate: Validation mode.
        validated: Whether the calculations are validated (a ``doc.json`` exists
            and ``validate`` is not ``"off"``).
        issues: Issues found by the validation of the spec (``"warn"`` mode).
        handlers: Handlers set by :meth:`handler_properties`.
        results: Results of the last :meth:`execute`.

    Raises:
        TypeError: If both or none of ``software`` and ``platform`` are given, or if
            an argument is unknown (the message suggests a close name).
        ValueError: If ``validate`` or the driver is unknown, or if an execution
            field is invalid.
        SoftwareNotFoundError: If the software is not registered.
        ConfigurationError: If the environment cannot run the software (see
            ``Software.check_environment``, called before the validation and the
            selection of the driver).
        DriverUnavailableError: If the requested driver cannot be used.
        ValidationError: In ``"strict"`` mode, if the spec is invalid or the
            software has no ``doc.json``; also if the requested driver cannot use
            ``raw``.
    """

    def __init__(
        self,
        *,
        method: str,
        software: str | None = None,
        module: str | None = DEFAULT_MODULE,
        method_args: dict[str, Any] | None = None,
        module_args: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
        raw: RawKeywords = None,
        validate: str = "strict",
        platform: str | None = None,
        **exec_kwargs: Any,
    ) -> None:
        if (software is None) == (platform is None):
            raise TypeError("Give exactly one of software= and platform=")
        _check_names(exec_kwargs, _EXEC_FIELDS, [*_EXEC_FIELDS, *_INIT_NAMES])
        if validate not in MODES:
            raise ValueError(
                f"Unknown validation mode {validate!r}; expected one of "
                f"{', '.join(MODES)}"
            )
        self.spec = CalculationSpec.from_kwargs(
            method, method_args, module or DEFAULT_MODULE, module_args, parameters, raw
        )
        self.exec_spec = ExecutionSpec(**exec_kwargs)
        self.validate = validate
        software_cls = get_software(platform if software is None else software)
        self.software = software_cls()
        self.software.check_environment()
        self.schema: Schema | None = None
        self.issues: list[Issue] = []
        if software_cls.DOC is not None:
            self.schema = load_schema(software_cls.DOC)
            self.issues = validate_spec(self.spec, self.schema, mode=validate)
        elif validate != "off":
            message = (
                f"{software_cls.NAME} has no doc.json: its calculations cannot be "
                "validated; pass validate='off' to run it without validation"
            )
            if validate == "strict":
                raise ValidationError(message)
            warnings.warn(message, stacklevel=2)
        self.validated = self.schema is not None and validate != "off"
        self.driver: DriverSelection = select_driver(
            software_cls, self.exec_spec.driver, self.spec
        )
        self.handlers: list[HandlerSpec] = []
        self.results: list[Result] = []

    def __repr__(self) -> str:
        return (
            f"AMAC(software={self.software.name!r}, method={self.spec.method!r}, "
            f"module={self.spec.module!r}, driver={self.driver.name!r}, "
            f"validate={self.validate!r})"
        )

    def handler_properties(
        self, *handlers: Any, skip_incompatible: bool = False
    ) -> None:
        """Set the handlers computing the properties, replacing the previous ones.

        Compatibility with the module (``modules=``) and the driver (``drivers=``)
        is checked against the calculator; after an ``"auto"`` fallback, the
        message gives its reason.

        Args:
            *handlers: Decorated handlers, custom callables or ``(name, callable)``
                tuples (see ``amac.engine.handlers.resolve_handlers``).
            skip_incompatible: Discard the handlers incompatible with the module or
                the selected driver, with one warning listing them, instead of
                raising. Other errors still raise.

        Raises:
            TypeError: If an item is not a handler.
            ValueError: If a handler belongs to another software or if two results
                share a name; also if a handler is incompatible with the module or
                the driver, unless ``skip_incompatible``.
        """
        self.handlers = self._resolve_handlers(handlers, skip_incompatible)

    def execute(
        self, geometry: Atoms | Iterable[Any] | tuple[Atoms, Mapping], **overrides: Any
    ) -> Result | list[Result]:
        """Run the calculation on each image, sequentially.

        ``geometry`` is one image or an iterable of images. An image is an ``Atoms``,
        or a ``(Atoms, image_overrides)`` tuple whose mapping overrides
        ``method_args``, ``module_args``, ``parameters`` and ``raw`` for this image
        only: mappings are merged in depth with the spec of the calculator (the
        image wins), a non-mapping ``raw`` replaces it; ``method`` and ``module``
        cannot change. A tuple of exactly an ``Atoms`` and a mapping is one image;
        any other iterable is a sequence of images.

        One image runs in ``workdir/<label>``; the images of an iterable run in
        ``workdir/<label>/image_XXX``, even when there is only one. Each call
        replaces :attr:`results`, calls ``version()`` of the software and of the
        driver once for the provenance (a failure gives ``None``), and warns once
        per setting that a driver running the program ignores.

        For each image: validation (the geometry only, or the whole effective spec
        for an image with overrides, in the mode of the calculator), ``prepare``,
        ``run``, ``collect``, handlers, then ``finalize_run_directory`` (copy to
        ``outdir``, removal unless ``keep_files``). A phase in ``PHASES`` of the
        selected driver goes through the driver; the other phases go through the
        software. When the software has a ``doc.json``, the intermediate tree of
        the spec is in ``ctx.metadata["input_tree"]``, whatever the driver. The
        effective spec is ``ctx.spec`` and ``provenance["spec"]``.

        When a ``FILEIO`` software runs through the AMAC path, its executable is
        located once per call, before any directory is created (see
        ``Software.locate_executable``; ``PATH`` is never searched): with
        ``REQUIRES_EXECUTABLE``, it must be an absolute path to an executable file.
        The executable found is recorded in ``ctx.metadata["executable"]`` as
        ``{"path", "source"}``.

        When the run fails (non-zero exit code, timeout, program not found, any
        exception of a driver phase), the next phases and the handlers are
        skipped; nothing is run again with another driver. With
        ``raise_on_error`` the ``RunError`` is raised and the results of the
        previous images stay in :attr:`results`; otherwise the image gets a
        ``Result(success=False)`` holding the error, and the next images run.

        Args:
            geometry: An image, or an iterable of images.
            **overrides: ``ExecutionSpec`` fields applied to this call only, e.g.
                ``cpu``, ``timeout``, ``label``, ``overwrite``. ``driver`` cannot
                be overridden: it is selected when the calculator is created.

        Returns:
            A ``Result`` for one image, a list of ``Result`` for an iterable.

        Warns:
            UserWarning: For each execution setting ignored by the driver.

        Raises:
            TypeError: If ``geometry`` is not made of images, or if an override is
                unknown.
            ValueError: If ``geometry`` is empty, if ``driver`` is overridden, or
                if image overrides have unknown keys or change ``method`` or
                ``module``.
            ValidationError: If an image is invalid in ``"strict"`` mode.
            ExecutableNotFoundError: If the software has ``REQUIRES_EXECUTABLE``
                and no explicit source gives an absolute path to an executable
                file, whatever ``raise_on_error``.
            ConfigurationError: If the configuration file is invalid.
            FileExistsError: If a run directory is not empty and ``overwrite`` is
                false.
            RunError: If a run fails and ``raise_on_error`` is true.
            HandlerError: If a handler fails with ``handler_errors="raise"``.
        """
        exec_spec = self._exec_spec_for(overrides)
        images, single = _images(geometry)
        executable = self._locate_executable(exec_spec)
        versions = (_safe_version(self.software), _safe_version(self.driver.driver))
        self._warn_ignored_settings(exec_spec)
        self.results = []
        for index, (atoms, image_overrides) in enumerate(images):
            image = None if single else index
            result = self._run_image(
                atoms, image_overrides, image, exec_spec, versions, executable
            )
            self.results.append(result)
        return self.results[0] if single else list(self.results)

    def reprocess(
        self,
        directory: str | Path,
        handlers: Iterable[Any] | None = None,
        atoms: Atoms | None = None,
    ) -> Result:
        """Run ``collect`` and the handlers again on an existing run directory.

        Nothing is prepared nor run: the files already in ``directory`` are read.
        ``collect`` goes through the driver when it collects, otherwise through the
        software. Handlers reading native objects of a library (``drivers=``) only
        succeed if the ``collect`` of the driver rebuilds them; otherwise they fail
        like any handler, with a ``HandlerError`` recorded or raised according to
        ``handler_errors``. The directory is neither copied nor removed.

        Args:
            directory: Run directory of a previous calculation.
            handlers: Handlers for this call, resolved like
                :meth:`handler_properties`; ``None`` uses :attr:`handlers`.
            atoms: Geometry given to the handlers as ``ctx.atoms``; ``None`` if
                not given.

        Returns:
            The result, with ``provenance["reprocessed"]`` set to true; its success
            is false when ``collect`` fails and ``raise_on_error`` is false.

        Raises:
            FileNotFoundError: If ``directory`` is not a directory.
            TypeError: If an item is not a handler.
            ValueError: If the handlers are invalid for this calculator.
            RunError: If ``collect`` fails and ``raise_on_error`` is true.
            HandlerError: If a handler fails with ``handler_errors="raise"``.
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise FileNotFoundError(f"Run directory {directory} does not exist")
        metas = (
            self.handlers
            if handlers is None
            else self._resolve_handlers(handlers, skip_incompatible=False)
        )
        start, clock = datetime.now(UTC), time.perf_counter()
        ctx = self._context(atoms, self.spec, self.exec_spec, directory)
        properties: dict[str, Any] = {}
        errors: list[Any] = []
        failure = None
        try:
            self._phase(ctx, "collect")
        except RunError as err:
            if self.exec_spec.raise_on_error:
                raise
            failure = err
        if failure is None:
            properties, errors = self._run_handlers(ctx, metas)
        else:
            errors.append(failure)
        versions = (_safe_version(self.software), _safe_version(self.driver.driver))
        provenance = self._provenance(ctx, None, versions, start, clock, True)
        return Result(failure is None, properties, provenance, errors, ctx)

    def store(self, filename: str | Path, format: str = "json") -> Path:
        """Write :attr:`results` to a file (see ``amac.ios.store.store_results``).

        Args:
            filename: Path of the file; ``.json`` is appended unless present.
            format: Only ``"json"`` is supported.

        Returns:
            The path written.

        Raises:
            NotImplementedError: If ``format`` is not ``"json"``.
            TypeError: If a property cannot be stored.
        """
        return store_results(self.results, filename, format)

    def to_dict(self, mask_secrets: bool = True) -> dict[str, Any]:
        """Return the data rebuilding this calculator.

        ``exec_spec`` holds the requested driver, not the selected one. Handlers are
        stored as ``{"name": ..., "handler": "module:qualname"}`` when their function
        can be imported again; lambdas, local functions and functions of
        ``__main__`` are left out with a warning.

        Args:
            mask_secrets: Replace every value of ``exec_spec.env`` by ``"***"``.

        Returns:
            A JSON-compatible dict.

        Warns:
            UserWarning: If some handlers cannot be stored.
        """
        exec_spec = (
            _masked_exec_spec(self.exec_spec)
            if mask_secrets
            else self.exec_spec.to_dict()
        )
        return {
            "software": self.software.name,
            "validate": self.validate,
            "spec": self.spec.to_dict(),
            "exec_spec": exec_spec,
            "handlers": _handler_references(self.handlers),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Build a calculator from the output of :meth:`to_dict`.

        The ``env`` variables whose value is ``"***"`` are dropped with a warning:
        pass them again with ``execute(env=...)``. The stored handlers are imported
        again and set with ``handler_properties(skip_incompatible=True)``, since the
        driver selected on this machine may differ.

        **Security**: importing the handlers runs the modules named in ``data``;
        only load files you trust.

        Raises:
            ValueError: If keys are missing or unknown, or if a handler cannot be
                imported.

        Warns:
            UserWarning: For masked variables and for skipped handlers.
        """
        keys = data.keys()
        if not _DICT_KEYS <= keys or keys - _DICT_KEYS - _OPTIONAL_DICT_KEYS:
            raise ValueError(
                f"AMAC data must have the keys {sorted(_DICT_KEYS)}, and optionally "
                f"'handlers'; got {sorted(data)}"
            )
        calc = cls(
            software=data["software"],
            validate=data["validate"],
            **data["spec"],
            **_unmask_env(data["exec_spec"]),
        )
        if references := data.get("handlers"):
            items = [_import_handler(entry) for entry in references]
            calc.handler_properties(*items, skip_incompatible=True)
        return calc

    def _resolve_handlers(
        self, handlers: Iterable[Any], skip_incompatible: bool
    ) -> list[HandlerSpec]:
        return resolve_handlers(
            type(self.software),
            self.spec,
            handlers,
            driver=self.driver.name,
            schema=self.schema,
            fallback=self.driver.fallback,
            skip_incompatible=skip_incompatible,
        )

    def _exec_spec_for(self, overrides: Mapping[str, Any]) -> ExecutionSpec:
        if "driver" in overrides:
            raise ValueError(
                "driver cannot be overridden in execute(): it is selected when "
                "AMAC is created"
            )
        _check_names(overrides, _EXEC_FIELDS - {"driver"}, _EXEC_FIELDS)
        return replace(self.exec_spec, **overrides)

    def _warn_ignored_settings(self, exec_spec: ExecutionSpec) -> None:
        driver = self.driver.driver
        if driver is None or "run" not in driver.PHASES:
            return
        for name in driver.ignored_settings(self.software, exec_spec):
            warnings.warn(
                f"Driver {driver.NAME!r} ignores the execution setting {name!r}",
                stacklevel=3,
            )

    def _locate_executable(self, exec_spec: ExecutionSpec) -> ExecutableLocation | None:
        """Locate the executable of a ``FILEIO`` run through the AMAC path."""
        driver = self.driver.driver
        if self.software.EXECUTION != "FILEIO" or (
            driver is not None and "run" in driver.PHASES
        ):
            return None
        if self.software.REQUIRES_EXECUTABLE:
            return self.software.require_executable(exec_spec)
        return self.software.locate_executable(exec_spec)

    def _run_image(
        self,
        atoms: Atoms,
        image_overrides: Mapping[str, Any] | None,
        image: int | None,
        exec_spec: ExecutionSpec,
        versions: tuple[str | None, str | None],
        executable: ExecutableLocation | None,
    ) -> Result:
        spec = _image_spec(self.spec, image_overrides)
        if image_overrides:
            self._validate_image(spec, atoms)
        else:
            self._validate_geometry(atoms)
        start, clock = datetime.now(UTC), time.perf_counter()
        directory = make_run_directory(exec_spec, image)
        ctx = self._context(atoms, spec, exec_spec, directory)
        if executable is not None:
            ctx.metadata[EXECUTABLE_KEY] = asdict(executable)
        properties: dict[str, Any] = {}
        errors: list[Any] = []
        run_error = self._run_phases(ctx)
        if run_error is None:
            properties, errors = self._run_handlers(ctx, self.handlers)
        else:
            errors.append(run_error)
        provenance = self._provenance(ctx, image, versions, start, clock, False)
        result = Result(run_error is None, properties, provenance, errors, ctx)
        destination = finalize_run_directory(directory, exec_spec)
        provenance["outdir"] = None if destination is None else str(destination)
        return result

    def _context(
        self,
        atoms: Atoms | None,
        spec: CalculationSpec,
        exec_spec: ExecutionSpec,
        directory: Path,
    ) -> RunContext:
        ctx = RunContext(
            atoms,
            spec,
            exec_spec,
            directory,
            software=self.software,
            driver=self.driver.name,
        )
        if self.schema is not None:
            tree = translate(spec, self.schema)
            inject_resources(tree, self.schema, exec_spec)
            ctx.metadata[INPUT_TREE_KEY] = tree
        return ctx

    def _run_phases(self, ctx: RunContext) -> RunError | None:
        """Run prepare, run and collect; return the failure unless it must be raised."""
        try:
            self._phase(ctx, "prepare")
            self._phase(ctx, "run")
            if ctx.return_code not in (None, 0):
                raise RunError(
                    f"{self.software.name} exited with code {ctx.return_code}", ctx
                )
            self._phase(ctx, "collect")
        except RunError as err:
            if ctx.exec_spec.raise_on_error:
                raise
            return err
        return None

    def _phase(self, ctx: RunContext, name: str) -> None:
        driver = self.driver.driver
        start = time.perf_counter()
        if driver is not None and name in driver.PHASES:
            _driver_phase(driver, name, self.software, ctx)
        else:
            getattr(self.software, name)(ctx)
        # FileIOSoftware.run already records the duration of the process itself.
        ctx.timings.setdefault(name, time.perf_counter() - start)

    def _run_handlers(
        self, ctx: RunContext, metas: list[HandlerSpec]
    ) -> tuple[dict[str, Any], list[Any]]:
        start = time.perf_counter()
        properties, handler_errors = run_handlers(ctx, metas)
        ctx.timings["handlers"] = time.perf_counter() - start
        return properties, list(handler_errors)

    def _provenance(
        self,
        ctx: RunContext,
        image: int | None,
        versions: tuple[str | None, str | None],
        start: datetime,
        clock: float,
        reprocessed: bool,
    ) -> dict[str, Any]:
        software_version, driver_version = versions
        return {
            "amac_version": _amac_version(),
            "software": self.software.name,
            "software_version": software_version,
            "driver": self.driver.name,
            "driver_version": driver_version,
            "driver_fallback": self.driver.fallback,
            "image": image,
            "spec": ctx.spec.to_dict(),
            "exec_spec": _masked_exec_spec(ctx.exec_spec),
            "validated": self.validated,
            "reprocessed": reprocessed,
            "directory": str(ctx.directory),
            "outdir": None,
            "hostname": socket.gethostname(),
            "start": start.isoformat(),
            "end": datetime.now(UTC).isoformat(),
            "duration": time.perf_counter() - clock,
            "atoms": None if ctx.atoms is None else ctx.atoms.copy(),
        }

    def _validate_image(self, spec: CalculationSpec, atoms: Atoms) -> None:
        """Validate the whole effective spec of an image with overrides."""
        if self.schema is not None and self.validate != "off":
            validate_spec(spec, self.schema, mode=self.validate, atoms=atoms)
        driver = self.driver.driver
        if (
            spec.raw is not None
            and driver is not None
            and "prepare" in driver.PHASES
            and not driver.SUPPORTS_RAW
        ):
            raise ValidationError(
                f"Driver {driver.NAME!r} does not support raw keywords; use "
                "driver='amac' to write them"
            )

    def _validate_geometry(self, atoms: Atoms) -> None:
        """Report the issues that ``atoms`` adds to those of the spec alone."""
        if self.schema is None or self.validate == "off":
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            issues = validate_spec(self.spec, self.schema, mode="warn", atoms=atoms)
        new = [issue for issue in issues if issue not in self.issues]
        if not new:
            return
        details = "\n".join(f"  - {issue.path}: {issue.message}" for issue in new)
        message = f"Invalid geometry for {self.software.name}:\n{details}"
        if self.validate == "strict":
            raise ValidationError(message)
        warnings.warn(message, stacklevel=4)


def reprocess(result: Result, handlers: Iterable[Any]) -> Result:
    """Run handlers again on the files of a stored result.

    The calculator is rebuilt from the provenance: software, spec, ``exec_spec``
    (masked ``env`` variables dropped with a warning) and requested driver, with
    ``validate="off"`` since the calculation already ran. The directory is
    ``provenance["directory"]``, or the ``outdir`` copy when the former no longer
    exists; the geometry is ``provenance["atoms"]``. Then
    :meth:`AMAC.reprocess` runs ``collect`` and ``handlers``.

    Args:
        result: Result returned by ``execute`` or reloaded by ``amac.load``.
        handlers: Handlers to run.

    Returns:
        The new result.

    Raises:
        ValueError: If the provenance lacks ``software``, ``spec``, ``exec_spec`` or
            ``directory``.
        FileNotFoundError: If neither the directory nor its copy exists.
        ConfigurationError: If the environment cannot run the software any more.
        DriverUnavailableError: If the requested driver cannot be used any more.
    """
    provenance = result.provenance
    required = ("software", "spec", "exec_spec", "directory")
    if missing := [key for key in required if key not in provenance]:
        raise ValueError(
            f"The provenance lacks {', '.join(missing)}: this result cannot be "
            "reprocessed"
        )
    calc = AMAC(
        software=provenance["software"],
        validate="off",
        **provenance["spec"],
        **_unmask_env(provenance["exec_spec"]),
    )
    directory = Path(provenance["directory"])
    outdir = provenance.get("outdir")
    if not directory.is_dir() and outdir and Path(outdir).is_dir():
        directory = Path(outdir)
    return calc.reprocess(directory, handlers=handlers, atoms=provenance.get("atoms"))


def _driver_phase(
    driver: Driver, name: str, software: Software, ctx: RunContext
) -> None:
    try:
        getattr(driver, name)(software, ctx)
    except RunError as err:
        if err.ctx is None:
            err.ctx = ctx
        raise
    # A library may raise anything: a failing driver phase is a failed run.
    except Exception as err:
        raise RunError(
            f"Driver {driver.NAME!r} failed in {name}: {err!r}", ctx
        ) from err


def _safe_version(source: Software | Driver | None) -> str | None:
    """Return ``source.version()``, ``None`` when there is no source or it fails."""
    if source is None:
        return None
    try:
        return source.version()
    # version() may run a program or read metadata: a failure only loses it.
    except Exception:
        return None


def _check_names(
    given: Iterable[str], accepted: Collection[str], known: Iterable[str]
) -> None:
    for name in given:
        if name in accepted:
            continue
        close = difflib.get_close_matches(name, sorted(known), n=1)
        if close:
            hint = f"did you mean {close[0]!r}?"
        else:
            hint = f"accepted: {', '.join(sorted(accepted))}"
        raise TypeError(f"Unknown argument {name!r}; {hint}")


def _images(geometry: Any) -> tuple[list[_Image], bool]:
    """Return the images of ``geometry`` and whether it is a single image."""
    if isinstance(geometry, Atoms):
        return [(geometry, None)], True
    if _is_image_pair(geometry):
        return [(geometry[0], _check_image_overrides(geometry[1]))], True
    if isinstance(geometry, str | bytes) or not isinstance(geometry, Iterable):
        raise TypeError(
            "geometry must be an Atoms, an (Atoms, overrides) tuple or an iterable "
            f"of them, got {type(geometry).__name__}"
        )
    images: list[_Image] = []
    wrong = []
    for item in geometry:
        if isinstance(item, Atoms):
            images.append((item, None))
        elif _is_image_pair(item):
            images.append((item[0], _check_image_overrides(item[1])))
        else:
            wrong.append(type(item).__name__)
    if wrong:
        raise TypeError(
            "geometry items must be Atoms or (Atoms, overrides), got "
            f"{', '.join(wrong)}"
        )
    if not images:
        raise ValueError("geometry contains no image")
    return images, False


def _is_image_pair(item: Any) -> bool:
    return (
        isinstance(item, tuple)
        and len(item) == 2
        and isinstance(item[0], Atoms)
        and isinstance(item[1], Mapping)
    )


def _check_image_overrides(overrides: Mapping[str, Any]) -> Mapping[str, Any]:
    if fixed := sorted({"method", "module"} & overrides.keys()):
        raise ValueError(
            f"{', '.join(fixed)} cannot be overridden per image: create another "
            "calculator"
        )
    if unknown := sorted(overrides.keys() - set(IMAGE_OVERRIDE_KEYS)):
        raise ValueError(
            f"Unknown image overrides {unknown}; accepted: "
            f"{', '.join(IMAGE_OVERRIDE_KEYS)}"
        )
    for key in ("method_args", "module_args", "parameters"):
        if key in overrides and not isinstance(overrides[key], Mapping):
            raise TypeError(f"image override {key} must be a mapping")
    return overrides


def _image_spec(
    spec: CalculationSpec, overrides: Mapping[str, Any] | None
) -> CalculationSpec:
    """Return ``spec`` with the image overrides merged in depth."""
    if not overrides:
        return spec
    data = spec.to_dict()
    for key, value in overrides.items():
        if key == "raw":
            if isinstance(data["raw"], Mapping) and isinstance(value, Mapping):
                data["raw"] = _deep_merge(data["raw"], value)
            else:
                data["raw"] = copy.deepcopy(value)
        elif key == "parameters":
            upper = {
                k.upper() if isinstance(k, str) else k: v for k, v in value.items()
            }
            data["parameters"] = _deep_merge(data["parameters"], upper)
        else:
            data[key] = _deep_merge(data[key], value)
    return CalculationSpec.from_dict(data)


def _deep_merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _masked_exec_spec(exec_spec: ExecutionSpec) -> dict[str, Any]:
    """Return ``exec_spec.to_dict()`` with every ``env`` value replaced by a mask."""
    data = exec_spec.to_dict()
    data["env"] = dict.fromkeys(data["env"], ENV_MASK)
    return data


def _unmask_env(exec_data: Mapping[str, Any]) -> dict[str, Any]:
    """Drop, with a warning, the ``env`` variables whose value is masked."""
    data = dict(exec_data)
    env = dict(data.get("env") or {})
    masked = sorted(name for name, value in env.items() if value == ENV_MASK)
    if masked:
        warnings.warn(
            f"Masked environment variables are ignored: {', '.join(masked)}; pass "
            "them again with execute(env=...)",
            stacklevel=3,
        )
        data["env"] = {name: value for name, value in env.items() if value != ENV_MASK}
    return data


def _handler_references(metas: Iterable[HandlerSpec]) -> list[dict[str, str]]:
    references, left_out = [], []
    for meta in metas:
        reference = _reference(meta.function)
        if reference is None:
            left_out.append(meta.name)
        else:
            references.append({"name": meta.name, "handler": reference})
    if left_out:
        warnings.warn(
            f"Handlers not stored, their function cannot be imported again: "
            f"{', '.join(left_out)}",
            stacklevel=3,
        )
    return references


def _reference(function: Any) -> str | None:
    """Return ``"module:qualname"`` if ``function`` can be imported back as itself."""
    module = getattr(function, "__module__", None)
    qualname = getattr(function, "__qualname__", None)
    if not isinstance(module, str) or not isinstance(qualname, str):
        return None
    if module == "__main__" or "<" in qualname:
        return None
    reference = f"{module}:{qualname}"
    try:
        target = _import_reference(reference)
    except (ImportError, AttributeError):
        return None
    return reference if target is function else None


def _import_reference(reference: str) -> Any:
    module_name, _, qualname = reference.partition(":")
    target = importlib.import_module(module_name)
    for part in qualname.split("."):
        target = getattr(target, part)
    return target


def _import_handler(entry: Mapping[str, Any]) -> tuple[str, Any]:
    try:
        return entry["name"], _import_reference(entry["handler"])
    except (KeyError, TypeError, ImportError, AttributeError) as err:
        raise ValueError(f"Cannot import the stored handler {entry!r}: {err}") from err


def _amac_version() -> str | None:
    # Imported here: the package __init__ imports this module.
    import amac

    return getattr(amac, "__version__", None)
