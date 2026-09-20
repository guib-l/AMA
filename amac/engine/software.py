"""Abstract interface of the software supported by AMAC."""

from __future__ import annotations

import io
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from amac.config import config_label, load_config
from amac.engine.context import INPUT_TREE_KEY
from amac.engine.execute import LocalExecutor, build_environment
from amac.exceptions import ExecutableNotFoundError, RunError
from amac.parameter.composer import get_composer
from amac.parameter.schema import load as load_schema

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.engine.drivers import Driver
    from amac.parameter.composer import Composer
    from amac.parameter.parameters import ExecutionSpec
    from amac.parameter.schema import Schema

EXPLICIT_SOURCE = "executable="


@dataclass(frozen=True)
class ExecutableLocation:
    """Executable given for a software, and where it was given.

    Attributes:
        path: Executable as given, with ``~`` expanded.
        source: ``"executable="`` (explicit or ``amac.configure()``) or
            ``"file:<configuration file>"``.
    """

    path: str
    source: str


class Software(ABC):
    """Base class of every software supported by AMAC.

    ``prepare``, ``run`` and ``collect`` are called in this order on a ``RunContext``
    and fill it in place; together they form the ``"amac"`` driver. A library driver
    (``amac.engine.drivers.Driver``) may replace some of these phases.

    Attributes:
        NAME: Canonical name used by the registry.
        ALIASES: Other names accepted by the registry.
        DOC: Path of the ``doc.json`` describing the software, if any.
        EXECUTION: ``"FILEIO"`` or ``"INPROCESS"``, set by the intermediate class.
        HANDLERS: Result handlers keyed by name; each subclass has its own dict.
        DRIVERS: Optional ``Driver`` subclasses, in order of preference for
            ``driver="auto"``.
        composer_cls: Composer used by ``FileIOSoftware.prepare``; ``None``
            selects the composer of the ``SYNTAX`` of ``DOC``.
        REQUIRES_EXECUTABLE: Whether runs need an executable from an explicit
            source; ``AMAC.execute`` then checks it before creating any directory.
            ``False`` by default, ``True`` for ``FileIOSoftware``.
    """

    NAME: ClassVar[str] = ""
    ALIASES: ClassVar[tuple[str, ...]] = ()
    DOC: ClassVar[Path | None] = None
    EXECUTION: ClassVar[str] = ""
    HANDLERS: ClassVar[dict[str, Callable[[RunContext], Any]]] = {}
    DRIVERS: ClassVar[tuple[type[Driver], ...]] = ()
    composer_cls: ClassVar[type[Composer] | None] = None
    REQUIRES_EXECUTABLE: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.HANDLERS = {}

    def __init__(self, config: str | Path | None = None) -> None:
        """Bind the software to a configuration file.

        Args:
            config: Configuration file read for this software; ``None`` uses the
                one of ``amac.set_config()``, and no configuration at all without
                it.
        """
        self.config = config

    @property
    def name(self) -> str:
        """Canonical name of the software."""
        return type(self).NAME

    @abstractmethod
    def prepare(self, ctx: RunContext) -> None:
        """Prepare the calculation before it runs."""

    @abstractmethod
    def run(self, ctx: RunContext) -> None:
        """Run the calculation."""

    @abstractmethod
    def collect(self, ctx: RunContext) -> None:
        """Fill ``ctx`` with the produced files, outputs and native objects."""

    def resolve_executable(self, exec_spec: ExecutionSpec) -> str | None:
        """Return the path of :meth:`locate_executable`, ``None`` when not found."""
        location = self.locate_executable(exec_spec)
        return None if location is None else location.path

    def locate_executable(self, exec_spec: ExecutionSpec) -> ExecutableLocation | None:
        """Return the executable of a run and its source.

        The first source set wins; AMAC never searches ``PATH``:

        1. ``exec_spec.executable``; the facade has already put the executable of
           ``amac.configure()`` there;
        2. ``executable`` of ``[software.<NAME>]`` in the configuration file
           (:attr:`config`, ``amac.config``).

        The value is returned as given, with ``~`` expanded; nothing is checked
        here: see :meth:`require_executable`.

        The sources are read here, when the command is built, and not stored in
        ``exec_spec``: the spec keeps what the user asked, and every path (facade,
        ``AMAC``, ``AMAC.from_dict``) applies the same rule.

        Raises:
            ConfigurationError: If the configuration file is read and invalid.
        """
        if exec_spec.executable is not None:
            return _location(exec_spec.executable, EXPLICIT_SOURCE)
        config = load_config(self.config)
        if (value := config.for_software(self.NAME).executable) is not None:
            return _location(value, f"file:{config.path}")
        return None

    def require_executable(self, exec_spec: ExecutionSpec) -> ExecutableLocation:
        """Return :meth:`locate_executable`, checking that the executable can run.

        Raises:
            ExecutableNotFoundError: If no explicit source gives an executable
                (the message lists them), if it is not an absolute path, or if it
                is not an executable file.
            ConfigurationError: If the configuration file is invalid.
        """
        location = self.locate_executable(exec_spec)
        if location is None:
            tried = [
                f"{EXPLICIT_SOURCE}/configure()",
                f"{config_label(self.config)} [software.{self.NAME}]",
            ]
            raise ExecutableNotFoundError(
                f"{self.name}: executable not found. Tried: {', '.join(tried)}. Set "
                "one of them to the absolute path of the executable"
            )
        path = location.path
        if not os.path.isabs(path):
            raise ExecutableNotFoundError(
                f"{self.name}: executable {path!r} ({location.source}) must be an "
                "absolute path; AMAC does not search PATH"
            )
        if not Path(path).is_file() or not os.access(path, os.X_OK):
            raise ExecutableNotFoundError(
                f"{self.name}: executable {path} ({location.source}) does not exist "
                "or is not executable"
            )
        return location

    def configured_env(self) -> dict[str, str]:
        """Return the ``env`` of ``[software.<NAME>]`` in the configuration file.

        Raises:
            ConfigurationError: If the configuration file is invalid.
        """
        return dict(load_config(self.config).for_software(self.NAME).env)

    def check_environment(self) -> None:
        """Check that the environment can run the software; does nothing by default.

        ``AMAC`` calls it when the calculator is created, before the validation and
        the selection of the driver.

        Raises:
            ConfigurationError: If the environment cannot run the software, e.g. a
                missing library.
        """

    def version(self) -> str | None:
        """Return the software version, or ``None`` when unknown (default)."""
        return None

    def cleanup(self, ctx: RunContext) -> None:
        """Remove temporary data after a run; does nothing by default."""


class FileIOSoftware(Software):
    """Software driven through input files and an external executable.

    A subclass sets ``NAME`` and ``DOC``, is registered with
    ``@register_software`` and implements :meth:`command`. It may set
    ``composer_cls``, and override :meth:`stdin` and
    :meth:`stdout_file`. Its runs require an executable (``REQUIRES_EXECUTABLE``).
    ``amac.assets.dftbplus.dftbplus`` is a complete example.
    """

    EXECUTION = "FILEIO"
    REQUIRES_EXECUTABLE = True

    def prepare(self, ctx: RunContext) -> None:
        """Compose the input files and write them in ``ctx.directory``.

        The composer is ``composer_cls`` when set, otherwise the one of the
        ``SYNTAX`` of ``DOC``. Written files are recorded in ``ctx.input_files``.

        The tree ``AMAC`` put in ``ctx.metadata["input_tree"]`` is given to the
        composer, which works on it rather than translating the spec again: the
        provenance then holds the tree the input file was written from.

        Raises:
            ValueError: If ``DOC`` is not set or no composer handles its ``SYNTAX``.
            FileNotFoundError: If ``ctx.directory`` does not exist.
        """
        schema = self._schema()
        composer_cls = type(self).composer_cls or get_composer(schema.syntax)
        files = composer_cls().compose(
            ctx.spec,
            schema,
            ctx.atoms,
            ctx.exec_spec,
            ctx.metadata.get(INPUT_TREE_KEY),
        )
        for name, content in files.items():
            path = ctx.directory / name
            with path.open("w", encoding="utf-8") as stream:
                stream.write(content)
            ctx.input_files[name] = path

    @abstractmethod
    def command(self, ctx: RunContext) -> list[str]:
        """Return the command line that runs the calculation."""

    def stdin(self, ctx: RunContext) -> Path | None:
        """Return the file fed to the standard input, relative to ``ctx.directory``.

        ``None`` (default) gives an empty standard input.
        """
        return None

    def stdout_file(self, ctx: RunContext) -> Path | None:
        """Return the file receiving the standard output, relative to
        ``ctx.directory``.

        ``None`` (default) captures the output in ``ctx.stdout``.
        """
        return None

    def run(self, ctx: RunContext) -> None:
        """Run :meth:`command` in ``ctx.directory`` with ``LocalExecutor``.

        The environment is the current one with ``OMP_NUM_THREADS`` set to
        ``exec_spec.cpu``, updated with :meth:`configured_env`, then with
        ``exec_spec.env``. ``ctx.stdout``,
        ``ctx.stderr``, ``ctx.return_code`` and ``ctx.timings["run"]`` are filled.

        A non-zero exit code raises when ``exec_spec.raise_on_error`` is true, and is
        only recorded in ``ctx.return_code`` otherwise. A program that cannot start
        or exceeds ``exec_spec.timeout`` always raises, its process group killed;
        ``ctx.return_code`` then stays ``None``.

        Raises:
            RunError: In the cases above; ``RunError.ctx`` is ``ctx``.
        """
        exec_spec = ctx.exec_spec
        try:
            result = LocalExecutor().run(
                self.command(ctx),
                ctx.directory,
                env=build_environment(
                    exec_spec.cpu, {**self.configured_env(), **exec_spec.env}
                ),
                timeout=exec_spec.timeout,
                stdin=self.stdin(ctx),
                stdout_file=self.stdout_file(ctx),
            )
        except RunError as err:
            raise RunError(f"{self.name}: {err}", ctx) from err
        ctx.stdout = result.stdout
        ctx.stderr = result.stderr
        ctx.return_code = result.return_code
        ctx.timings["run"] = result.duration
        if result.return_code != 0 and exec_spec.raise_on_error:
            raise RunError(
                f"{self.name} exited with code {result.return_code}", ctx
            )

    def collect(self, ctx: RunContext) -> None:
        """List the produced files in ``ctx.files``.

        Each key of ``doc.json`` ``OUTPUT.FILES`` is a glob pattern relative to
        ``ctx.directory``. Matching files are recorded under their relative POSIX
        path, in sorted order; a missing file is not an error.

        Raises:
            ValueError: If ``DOC`` is not set.
        """
        for pattern in self._schema().output.get("FILES", {}):
            for path in sorted(ctx.directory.glob(pattern)):
                if path.is_file():
                    ctx.files[path.relative_to(ctx.directory).as_posix()] = path

    def _schema(self) -> Schema:
        cls = type(self)
        if cls.DOC is None:
            raise ValueError(f"{cls.__name__}.DOC is not set")
        return load_schema(cls.DOC)


class InProcessSoftware(Software):
    """Software driven through its Python API in the current process.

    Subclasses implement :meth:`build`, :meth:`compute` and :meth:`collect`;
    ``amac.assets.demonnano.demonnano`` is a complete example.
    """

    EXECUTION = "INPROCESS"

    def prepare(self, ctx: RunContext) -> None:
        """Do nothing by default; the native object is built by :meth:`run`."""

    @abstractmethod
    def build(self, ctx: RunContext) -> None:
        """Build the native objects (e.g. a pySCF ``Mole`` and ``RKS``) in
        ``ctx.objects``."""

    @abstractmethod
    def compute(self, ctx: RunContext) -> None:
        """Run the native calculation on the objects built by :meth:`build`.

        This is where the software-specific call happens, e.g. ``kernel()`` or
        ``get_potential_energy()``.
        """

    def run(self, ctx: RunContext) -> None:
        """Call :meth:`build` then :meth:`compute`, capturing their logs.

        Text written to Python's ``sys.stdout`` / ``sys.stderr`` is stored in
        ``ctx.stdout`` / ``ctx.stderr``, even if the calculation raises. Output
        written directly to the file descriptors by compiled code is not captured.
        """
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.build(ctx)
                self.compute(ctx)
        finally:
            ctx.stdout = stdout.getvalue()
            ctx.stderr = stderr.getvalue()


def _location(value: str, source: str) -> ExecutableLocation:
    """Return ``value`` from ``source`` with ``~`` expanded."""
    return ExecutableLocation(os.path.expanduser(value), source)
