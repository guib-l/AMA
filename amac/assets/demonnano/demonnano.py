"""deMonNano, driven in the current process by the ``deMonPy`` library.

The library owns the input file and the run: it writes ``deMon.inp``, starts the
``deMon.x`` binary and parses its output. AMAC therefore has no composer and no
command line here; it translates the calculation into the three dictionaries the
library expects (``BASIS``, ``DEMON_PARAMETERS`` and ``DEMON_MODULE``), hands it
the executable it resolved, and normalizes the results.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from dataclasses import fields, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from amac.assets.demonnano.parser import (
    DemonNanoOutput,
    from_results,
    parse_directory,
)
from amac.config import config_label
from amac.engine.context import OUTPUT_KEY
from amac.engine.registry import register_software
from amac.engine.software import InProcessSoftware
from amac.exceptions import ConfigurationError, ValidationError
from amac.parameter.composer import Node, _apply_raw, translate
from amac.parameter.schema import load as load_schema
from amac.parameter.schema import resolve_name

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.parameter.composer import InputTree
    from amac.parameter.schema import Schema

LIBRARY = "deMonPy"
DISTRIBUTION = "DeMonNanoPy"
CALCULATOR_KEY = "demonnano"
MODULE_KEY = "demonnano.module"

BASIS = "BASIS"
BASIS_ENV = "BASIS"
SKFILE = "SKFILE"
PARAMETERS = "DEMON_PARAMETERS"
MODULES = "DEMON_MODULE"
ACTIVE = "ACTIVE"
CI = "CI"
CI_VARIANT = "CI-DFTB"
PRINT = "PRINT"

# AMAC module name -> module of ``deMonPy.available_modules``; SINGLE_POINT has
# none: the plain calculator runs it.
LIBRARY_MODULES = {"GEOMETRY_OPTIMISATION": "opt", "MOLECULAR_DYNAMICS": "md"}
OPT = "OPT"
MD = "MD"
ALGORITHM = "ALGORITHM"
ALGORITHMS = ("CGRAD", "SDC")
THERMOSTAT = "THERMOSTAT"
# ``_io_write_bath`` of the library reads every one of these names.
THERMOSTATS = ("SCAL", "BERE", "NOSE", "LANGE", "STOCH_R", "ANDERSEN", "LOCA")
MDBATH = "MDBATH"
MDYNAMICS = "MDYNAMICS"
MDSTEP = "MDSTEP"
TIMESTEP = "TIMESTEP"
DEFAULT_MD = {
    MDYNAMICS: {"RANDOM": 300},
    TIMESTEP: 0.4,
    MDSTEP: {"MAX": 100, "OUT": 10},
}


@register_software
class DeMonNano(InProcessSoftware):
    """deMonNano, registered as ``DEMON``.

    The calculation runs in the current process through ``deMonPy``, which is not
    on PyPI: it is installed from its repository, and
    :meth:`check_environment` reports its absence when the calculator is created.
    The library starts the ``deMon.x`` binary, so runs still need an executable
    from an explicit source (``executable=``, ``amac.configure()``,
    ``DEMON_EXECUTABLE`` or the configuration file); AMAC never searches ``PATH``
    and passes the path it resolved to the library.
    """

    NAME = "DEMON"
    ALIASES = ("deMonNano",)
    DOC = Path(__file__).with_name("doc.json")
    REQUIRES_EXECUTABLE = True
    LIBRARY: ClassVar[str] = LIBRARY
    DISTRIBUTION: ClassVar[str] = DISTRIBUTION

    def check_environment(self) -> None:
        """Check that ``deMonPy`` can be found, without importing it.

        Raises:
            ConfigurationError: If the library is not installed.
        """
        if importlib.util.find_spec(self.LIBRARY) is None:
            raise ConfigurationError(
                f"{self.NAME} requires the {self.LIBRARY} library, which is not "
                f"installed ({self.DISTRIBUTION}; it is not on PyPI, install it "
                "from its repository)"
            )

    def schema(self) -> Schema:
        """Return the schema of the ``doc.json``.

        ``InProcessSoftware`` has no composer, so it inherits no schema helper:
        the document is loaded here, from the cache of ``amac.parameter.schema``.
        """
        return load_schema(type(self).DOC)

    def build(self, ctx: RunContext) -> None:
        """Create the calculator of the library in ``ctx.objects``.

        The intermediate tree of the spec, which ``AMAC`` puts in
        ``ctx.metadata["input_tree"]``, becomes the keyword arguments of the
        library: ``BASIS``, ``DEMON_PARAMETERS`` and ``DEMON_MODULE``. The blocks
        the library reads without a default are completed here, as the DFTB+
        composer completes ``WriteResultsTag``: the ``CI`` block of ``CI-DFTB``,
        the ``MDYNAMICS``, ``TIMESTEP`` and ``MDSTEP`` of a dynamics, and the
        seven thermostat flags of ``MDBATH``. ``BASIS.SKFILE`` is the ``BASIS``
        variable of the ``env`` of the software in the configuration file
        (decision D5). Nothing else is added: the ``PRINT GRAD`` directive that
        writes the gradient stays the user's call.

        Raises:
            ExecutableNotFoundError: If no explicit source gives ``deMon.x``.
            ConfigurationError: If ``BASIS`` is not set for deMonNano in the
                configuration file.
            ValidationError: If ``raw`` is given as text, which has no meaning for
                a library driven by dictionaries, or if ``raw`` gives ``SKFILE``.
        """
        from deMonPy.deMonNano import Module_DeMonNano, deMonNano

        schema = self.schema()
        arguments = self._arguments(ctx, schema)
        module = LIBRARY_MODULES.get(
            resolve_name(schema.modules, ctx.spec.module, kind="module")
        )
        common = {
            "execut": self.require_executable(ctx.exec_spec).path,
            "workdir": str(ctx.directory),
            "omp_threads": ctx.exec_spec.cpu,
            "properties": ["energy"],
            **arguments,
        }
        ctx.objects[MODULE_KEY] = module
        ctx.objects[CALCULATOR_KEY] = (
            deMonNano(**common)
            if module is None
            else Module_DeMonNano(module=module, **common)
        )

    def compute(self, ctx: RunContext) -> None:
        """Run the calculation with the library.

        A single point calls ``calculate`` directly; the other modules go through
        their module of the library, whose own arguments (steps, algorithm, time
        step, temperature) are passed again from the tree, since the module
        rewrites its block from them.
        """
        calculator = ctx.objects[CALCULATOR_KEY]
        module = ctx.objects[MODULE_KEY]
        if module is None:
            calculator.calculate(
                symbols=list(ctx.atoms.symbols),
                positions=ctx.atoms.get_positions(),
                read_charges=True,
            )
            return
        block = dict(calculator.parameters.get(MODULES, {}).get(ACTIVE, {}))
        if module == "opt":
            calculator(image=ctx.atoms, **_optimisation_arguments(block.get(OPT, {})))
        else:
            calculator(image=ctx.atoms, **_dynamics_arguments(block.get(MD, {})))

    def collect(self, ctx: RunContext) -> None:
        """List the produced files and store the normalized output.

        The files are read first, so that ``amac.reprocess`` gives the same
        result without the library; what only the library holds, such as the
        convergence of an optimisation, completes it.
        """
        for pattern in self.schema().output.get("FILES", {}):
            for path in sorted(ctx.directory.glob(pattern)):
                if path.is_file():
                    ctx.files[path.relative_to(ctx.directory).as_posix()] = path
        output = parse_directory(ctx.directory)
        calculator = ctx.objects.get(CALCULATOR_KEY)
        results = getattr(calculator, "results", None)
        if isinstance(results, Mapping) and results:
            output = _completed(output, from_results(results))
        ctx.objects[OUTPUT_KEY] = output

    def _arguments(self, ctx: RunContext, schema: Schema) -> dict[str, Any]:
        """Return the ``BASIS``, ``DEMON_PARAMETERS`` and ``DEMON_MODULE`` blocks."""
        tree = ctx.metadata.get("input_tree") or translate(ctx.spec, schema)
        merged, raw_lines = _apply_raw(tree)
        if raw_lines:
            raise ValidationError(
                f"{self.NAME}: raw keywords must be a mapping, since the library "
                "takes dictionaries and writes deMon.inp itself"
            )
        arguments = _plain(merged)
        basis = arguments.setdefault(BASIS, {})
        if any(key.casefold() == SKFILE.casefold() for key in basis):
            # The validator refuses it in the spec; raw is never validated.
            raise ValidationError(
                f"{self.NAME}: {SKFILE} cannot be given; it is {BASIS_ENV} of the "
                f"env of [software.{self.NAME}] of {config_label(self.config)}"
            )
        basis[SKFILE] = self._slater_koster_directory()
        active = arguments.setdefault(PARAMETERS, {}).setdefault(ACTIVE, {})
        if _variant(ctx.spec, schema) == CI_VARIANT:
            active.setdefault(CI, {})
        _complete_modules(arguments.get(MODULES, {}).get(ACTIVE, {}))
        return arguments

    def _slater_koster_directory(self) -> str:
        """Return ``BASIS`` of the configured ``env``, the ``SKFILE`` directory.

        Raises:
            ConfigurationError: If ``BASIS`` is missing or empty.
        """
        directory = self.configured_env().get(BASIS_ENV)
        if not directory:
            raise ConfigurationError(
                f"{self.NAME}: {BASIS_ENV} (directory of the Slater-Koster files) is "
                f"not set in the env of [software.{self.NAME}] of "
                f"{config_label(self.config)}"
            )
        return directory


def _variant(spec: Any, schema: Schema) -> str | None:
    """Return the canonical name of the method variant of ``spec``, if any."""
    name = spec.method_args.get("variant")
    if not isinstance(name, str):
        return None
    method = schema.methods[schema.resolve_alias("METHODS", spec.method)]
    return resolve_name(method.get("VARIANTS", {}), name, kind="variant")


def _complete_modules(active: dict[str, Any]) -> None:
    """Complete the module blocks with what the library reads without a default."""
    if (block := active.get(OPT)) is not None:
        _expand_flag(block, ALGORITHM, ALGORITHMS)
    if (block := active.get(MD)) is not None:
        for key, value in DEFAULT_MD.items():
            current = block.setdefault(key, dict(value) if isinstance(value, dict) else value)
            if isinstance(value, dict):
                for name, default in value.items():
                    current.setdefault(name, default)
        _expand_thermostat(block)


def _expand_flag(block: dict[str, Any], key: str, names: tuple[str, ...]) -> None:
    """Turn ``{key: "NAME"}`` into the flag the library expects, ``{"NAME": True}``.

    Only the chosen name is written: the library writes every key whose value is
    true and compares the others with ``> 0.0``.
    """
    chosen = block.pop(key, None)
    if isinstance(chosen, str):
        for name in names:
            if name.casefold() == chosen.casefold():
                block[name] = True


def _expand_thermostat(block: dict[str, Any]) -> None:
    """Write the ``MDBATH`` block of the chosen thermostat, or remove it.

    The library reads the seven thermostat names of the block, so they are all
    written; without a thermostat the block is dropped and the dynamics stays
    microcanonical.
    """
    chosen = block.pop(THERMOSTAT, None)
    bath = block.get(MDBATH) or {}
    if not isinstance(chosen, str):
        if bath:
            block.pop(MDBATH, None)
        return
    block[MDBATH] = {
        **{name: name.casefold() == chosen.casefold() for name in THERMOSTATS},
        **bath,
    }


def _optimisation_arguments(block: Mapping[str, Any]) -> dict[str, Any]:
    """Return the keyword arguments of the ``opt`` module of the library."""
    rest = {
        key: value
        for key, value in block.items()
        if key not in ("MAX", "OUT", *ALGORITHMS)
    }
    algorithm = next(
        (name for name in ALGORITHMS if block.get(name) is True), ALGORITHMS[0]
    )
    return {
        "max": block.get("MAX", 999),
        "algo": algorithm,
        "out": block.get("OUT", 1),
        **rest,
    }


def _dynamics_arguments(block: Mapping[str, Any]) -> dict[str, Any]:
    """Return the keyword arguments of the ``md`` module of the library."""
    steps = block.get(MDSTEP, {})
    return {
        "temp": block.get(MDYNAMICS, {}).get("RANDOM", 300),
        "timestep": block.get(TIMESTEP, 0.4),
        "max_steps": steps.get("MAX", 100),
        "out": steps.get("OUT", 10),
        "out_traj": block.get("TRAJECTORY", True),
    }


def _plain(tree: InputTree) -> dict[str, Any]:
    """Return the tree as the nested dictionaries the library takes."""
    return {name: _plain_node(node) for name, node in tree.nodes.items()}


def _plain_node(node: Node) -> Any:
    """Return a node as a value or a dict; a block never carries both."""
    if not node.children:
        return node.value
    children = {name: _plain_node(child) for name, child in node.children.items()}
    if node.value is not None:
        raise ValidationError(
            f"{node.value!r} cannot be written next to {sorted(children)}: the "
            "library takes a value or a block, not both"
        )
    return children


def _completed(base: DemonNanoOutput, extra: DemonNanoOutput) -> DemonNanoOutput:
    """Return ``base`` with its empty attributes taken from ``extra``."""
    missing = {
        item.name: getattr(extra, item.name)
        for item in fields(DemonNanoOutput)
        if _empty(getattr(base, item.name)) and not _empty(getattr(extra, item.name))
    }
    return replace(base, **missing) if missing else base


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, dict | tuple) and not value)
