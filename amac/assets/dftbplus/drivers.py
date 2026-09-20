"""Optional library drivers of DFTB+: ``hsd`` and ``dftbplus-api``.

Neither library is required: both are imported inside the phases only. The
DFTB+ Python API is installed with DFTB+ itself, and AMAC never searches for the
shared library: its path is given explicitly as ``DFTBP_LIBRARY`` in the ``env``
of DFTB+ in the configuration file, or in ``env=`` of the run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from amac.assets.dftbplus.composer import _geometry_given, complete_tree, geometry_block
from amac.assets.dftbplus.parser import parse_directory
from amac.engine.context import OUTPUT_KEY
from amac.engine.drivers import Driver
from amac.engine.execute import applied_environment
from amac.parameter.composer import _apply_raw

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.engine.software import Software

LIBRARY_ENV = "DFTBP_LIBRARY"
INPUT_FILE = "dftb_in.hsd"
LOG_FILE = "dftb.out"


class HsdDriver(Driver):
    """Writes ``dftb_in.hsd`` with ``hsd-python`` instead of the AMAC renderer.

    Only ``prepare`` goes through the library: the intermediate tree is dumped as
    HSD, after the geometry block, which AMAC writes from ``ase.Atoms``.
    """

    NAME = "hsd"
    REQUIRES = ("hsd",)
    DISTRIBUTION = "hsd-python"
    PHASES = frozenset({"prepare"})
    SUPPORTS_RAW = True

    def prepare(self, software: Software, ctx: RunContext) -> None:
        """Write the input of ``ctx`` with ``hsd.dump_string``.

        ``raw`` follows the rule of the AMAC path: a dict is merged into the tree,
        text is written as-is at the end of the file. The geometry comes first,
        unless ``raw`` provides its own ``Geometry``.

        Raises:
            ValueError: If the software has no ``doc.json``, so no tree.
            ConfigurationError: If ``BASIS`` is not set for DFTB+ in the
                configuration file.
        """
        import hsd

        tree = ctx.metadata.get("input_tree")
        if tree is None:
            raise ValueError(f"{software.name}: no input tree to write with hsd")
        schema = software.schema()
        complete_tree(tree, ctx.spec, schema, software)
        merged, raw_lines = _apply_raw(tree)
        content = hsd.dump_string(_plain(merged))
        geometry = ""
        if not _geometry_given(merged, None):
            geometry = geometry_block(ctx.atoms, tree.format.get("PADDING", "  "))
        path = ctx.directory / schema.input["FILENAME"]
        with path.open("w", encoding="utf-8") as stream:
            stream.write(geometry + content + "".join(f"{line}\n" for line in raw_lines))
        ctx.input_files[path.name] = path


def _plain(tree: Any) -> dict[str, Any]:
    """Return the tree as the nested dict ``hsd`` expects.

    A node with a value and children becomes ``{name: {value: {...}}}``, the form
    HSD writes as ``Name = Value { ... }``.
    """
    return {name: _plain_node(node) for name, node in tree.nodes.items()}


def _plain_node(node: Any) -> Any:
    children = {name: _plain_node(child) for name, child in node.children.items()}
    if not children:
        return node.value
    if node.value is None:
        return children
    return {str(node.value): children}


class DftbPlusApiDriver(Driver):
    """Runs DFTB+ in the current process through its Python API.

    The API is the ``dftbplus`` module shipped with DFTB+ (``tools/pythonapi``),
    which loads the shared library of the program. Its exact calls are not
    verified here (placeholder P12): the driver reads ``dftb_in.hsd`` written by
    the AMAC path, runs the calculation, and lets the parser read the files the
    program wrote.

    The library is never searched for: ``env["DFTBP_LIBRARY"]`` must hold its
    absolute path, as ``executable`` does for the file path.
    """

    NAME = "dftbplus-api"
    REQUIRES = ("dftbplus",)
    DISTRIBUTION = None  # Installed with DFTB+, not from PyPI.
    PHASES = frozenset({"run", "collect"})
    SUPPORTED_SETTINGS = frozenset({"cpu", "env"})
    LIBRARY_ENV: ClassVar[str] = LIBRARY_ENV

    def library_path(
        self, software: Software, env: dict[str, str] | None = None
    ) -> str | None:
        """Return the explicit path of the DFTB+ shared library, ``None`` if unset.

        The value comes from ``env`` of the run, else from the ``env`` of the
        software in the configuration file. Nothing is searched for, and no
        environment variable is read: an unset value means the driver cannot be
        used.

        Args:
            software: Software of the run, for its configured environment.
            env: Environment of the run, from :meth:`execution_settings`; absent
                when the driver is being selected, before any ``ExecutionSpec``.
        """
        sources = {**software.configured_env(), **(env or {})}
        return sources.get(self.LIBRARY_ENV) or None

    def check_environment(self, software: Software) -> str | None:
        """Return why the driver cannot run, ``None`` when it can.

        The shared library of DFTB+ has no default location, and the driver is
        chosen before the run: the value must therefore be in the configuration
        file, not only in ``env=``.
        """
        if self.library_path(software) is None:
            return (
                f"the path of the DFTB+ library is missing: set {self.LIBRARY_ENV} "
                "in the env of DFTB+ in the configuration file"
            )
        return None

    def run(self, software: Software, ctx: RunContext) -> None:
        """Run the calculation of ``ctx.directory`` with the API.

        ``OMP_NUM_THREADS``, set from ``cpu``, and the ``env`` of the run are
        applied to the process before the library is loaded, the threads being
        fixed when it starts. They are restored once the run is over, even if it
        fails: the calculation runs in this process, so an environment left
        behind would change the next one.
        """
        from dftbplus import DftbPlus

        settings = self.execution_settings(software, ctx.exec_spec)
        with applied_environment(settings["cpu"], settings["env"]):
            calculator = DftbPlus(
                libpath=self.library_path(software, settings["env"]),
                hsdpath=str(ctx.directory / INPUT_FILE),
                logfile=str(ctx.directory / LOG_FILE),
            )
            calculator.set_geometry(
                ctx.atoms.get_positions(),
                latvecs=ctx.atoms.get_cell() if ctx.atoms.pbc.any() else None,
            )
            ctx.objects["dftbplus"] = calculator
            ctx.objects["energy"] = calculator.get_energy()
            calculator.close()
        ctx.return_code = 0

    def collect(self, software: Software, ctx: RunContext) -> None:
        """List the files with the software, then read them with the parser."""
        software.collect(ctx)
        ctx.objects[OUTPUT_KEY] = parse_directory(ctx.directory)
