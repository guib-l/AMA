"""Writing of ``dftb_in.hsd`` from the intermediate tree and the geometry."""

from __future__ import annotations

import copy
import io
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ase.io import write

from amac.config import config_label
from amac.engine.registry import get_software
from amac.exceptions import ConfigurationError, ValidationError
from amac.parameter.composer import Node, TreeComposer, _node
from amac.parameter.schema import resolve_name

if TYPE_CHECKING:
    from ase import Atoms

    from amac.engine.software import Software
    from amac.parameter.composer import InputTree
    from amac.parameter.parameters import CalculationSpec, ExecutionSpec
    from amac.parameter.schema import Schema

GEOMETRY_BLOCK = "Geometry"
GEOMETRY_FORMAT = "GenFormat"
GRADIENT_MODULE = "GRADIENT"
RESULTS_TAG = ("Options", "WriteResultsTag")
PRINT_FORCES = ("Analysis", "Printforces")
BASIS_ENV = "BASIS"
SLATER_KOSTER = ("Hamiltonian", "DFTB", "SlaterKosterFiles")
SLATER_KOSTER_PARAMETER = "SLATER_KOSTER_FILES"
# DFTB+ defaults these to empty strings; LowerCaseTypeName already matches.
FILE_NAME_DEFAULTS = ("Separator", "Suffix")


def complete_tree(
    tree: InputTree, spec: CalculationSpec, schema: Schema, software: Software
) -> None:
    """Write the options AMAC needs to read the results, in place.

    ``Options { WriteResultsTag = Yes }`` gives the machine-readable
    ``results.tag`` that the parser prefers (decision D4), and the ``GRADIENT``
    module needs ``Analysis { Printforces = Yes }`` to get forces out of a static
    run. A value already placed by the user is never overwritten.

    The ``TARGET`` of the module is opened as a block: DFTB+ refuses a bare
    ``Driver = GeometryOptimisation`` (``Invalid driver '#text'``) and expects
    ``Driver = GeometryOptimisation {}`` when no option is given.

    ``Prefix`` of ``SlaterKosterFiles`` is the ``BASIS`` variable of the ``env``
    of the software in the configuration file (decision D5), in the
    ``Type2FileNames`` block when chosen, directly in ``SlaterKosterFiles``
    otherwise. ``Separator`` and ``Suffix`` of ``Type2FileNames`` get the
    ``DEFAULT`` of the ``doc.json`` when the spec does not give them.

    Args:
        tree: Tree completed in place.
        spec: Calculation, to know the module.
        schema: Schema of the software, to resolve the module alias.
        software: DFTB+, for its configured environment.

    Raises:
        ConfigurationError: If ``BASIS`` is not set for DFTB+ in the configuration
            file.
        ValidationError: If ``Prefix`` is already in the tree.
    """
    _set_default(tree, RESULTS_TAG, True)
    module = resolve_name(schema.modules, spec.module, kind="module")
    if module == GRADIENT_MODULE:
        _set_default(tree, PRINT_FORCES, True)
    if target := schema.modules[module].get("TARGET"):
        _open_block(tree, tuple(target))
    path = SLATER_KOSTER
    if isinstance(variant := _node(tree, path).value, str):
        path = (*path, variant)
    prefix = _node(tree, (*path, "Prefix"))
    if prefix.value is not None:
        # The EXPLICIT variant takes any pair name, so the validator lets it pass.
        raise ValidationError(
            f"{software.name}: Prefix of SlaterKosterFiles cannot be given; it is "
            f"{BASIS_ENV} of the env of [software.{software.name}] of "
            f"{config_label(software.config)}"
        )
    prefix.value = slater_koster_prefix(software)
    if isinstance(variant, str):
        for name, value in _file_name_defaults(schema, variant).items():
            _set_default(tree, (*path, name), value)


def slater_koster_prefix(software: Software) -> str:
    """Return ``BASIS`` of the configured ``env`` of ``software``.

    A path separator is appended when missing, since DFTB+ joins ``Prefix`` and
    the file names as plain text.

    Raises:
        ConfigurationError: If ``BASIS`` is missing or empty.
    """
    prefix = software.configured_env().get(BASIS_ENV)
    if not prefix:
        raise ConfigurationError(
            f"{software.name}: {BASIS_ENV} (directory of the Slater-Koster files) "
            f"is not set in the env of [software.{software.name}] of "
            f"{config_label(software.config)}"
        )
    return prefix if prefix.endswith(os.sep) else prefix + os.sep


def _file_name_defaults(schema: Schema, variant: str) -> dict[str, Any]:
    """Return the ``doc.json`` defaults of ``FILE_NAME_DEFAULTS`` for ``variant``."""
    variants = schema.parameters[SLATER_KOSTER_PARAMETER].get("VARIANTS", {})
    folded = variant.casefold()
    arguments = next(
        (
            node.get("ARGUMENTS", {})
            for key, node in variants.items()
            if node.get("KEYWORD", key).casefold() == folded
        ),
        {},
    )
    return {
        name: arguments[name]["DEFAULT"]
        for name in FILE_NAME_DEFAULTS
        if "DEFAULT" in arguments.get(name, {})
    }


def _set_default(tree: InputTree, path: tuple[str, ...], value: Any) -> None:
    node = _node(tree, path)
    if node.value is None:
        node.value = value


def _open_block(tree: InputTree, path: tuple[str, ...]) -> None:
    """Make the node at ``path`` a block, when its value names one.

    HSD refuses a bare ``Driver = GeometryOptimisation``: a name selecting a block
    always opens one, empty when the calculation gives no option. An empty child
    named after the value is what ``TreeComposer`` renders as ``{}``.
    """
    node = _node(tree, path)
    if isinstance(node.value, str) and node.value and not node.children:
        node.children[node.value] = Node(format=copy.deepcopy(node.format))


def geometry_block(atoms: Atoms, padding: str = "  ") -> str:
    """Return the ``Geometry = GenFormat { ... }`` block of ``atoms``.

    The geometry is written in the input file itself, in the native gen format of
    DFTB+ (Ångström), so that a run is reproduced by copying one file.

    Args:
        atoms: Geometry of the calculation.
        padding: Indentation of one level, from ``INPUT.FORMAT_DEFAULTS``.

    Returns:
        The block, ending with a newline.
    """
    stream = io.StringIO()
    write(stream, atoms, format="gen")
    # ase.io pads its columns: strip the trailing blanks it leaves on each line.
    lines = [f"{padding}{line.rstrip()}" for line in stream.getvalue().splitlines()]
    head = f"{GEOMETRY_BLOCK} = {GEOMETRY_FORMAT} {{"
    return "\n".join([head, *lines, "}", ""])


def _geometry_given(tree: InputTree, raw: Any) -> bool:
    """Return whether a ``Geometry`` block is already asked for.

    ``raw`` is merged into the tree at render time only, so it is looked at here
    too: a ``raw`` dict naming ``Geometry`` replaces the geometry of the
    ``ase.Atoms``, instead of adding a second block. A ``raw`` given as text
    cannot be inspected: the geometry is then written as usual.
    """
    names = [*tree.nodes, *(raw if isinstance(raw, Mapping) else ())]
    folded = GEOMETRY_BLOCK.casefold()
    return any(isinstance(name, str) and name.casefold() == folded for name in names)


class DftbPlusComposer(TreeComposer):
    """HSD input of DFTB+: the geometry, then the tree rendered by ``TreeComposer``."""

    def compose(
        self,
        spec: CalculationSpec,
        schema: Schema,
        atoms: Any,
        exec_spec: ExecutionSpec,
        tree: InputTree | None = None,
    ) -> dict[str, str]:
        """Return ``{"dftb_in.hsd": text}``.

        The geometry comes first, unless ``raw`` already defines a ``Geometry``
        block, which then wins.

        Args:
            spec: Calculation to write.
            schema: Schema of DFTB+.
            atoms: Geometry of the image.
            exec_spec: Execution specification, for ``INPUT.RESOURCES``.
            tree: Tree of the image, modified in place; ``None`` builds it here.

        Returns:
            The input file name mapped to its content.

        Raises:
            ValueError: If ``atoms`` is ``None`` and ``raw`` defines no geometry.
            ConfigurationError: If ``BASIS`` is not set for DFTB+ in the
                configuration file.
        """
        tree = self.build_tree(spec, schema, exec_spec, tree)
        complete_tree(tree, spec, schema, get_software(schema.data["SOFTWARE"])())
        geometry = ""
        if not _geometry_given(tree, spec.raw):
            if atoms is None:
                raise ValueError("DFTB+ needs a geometry: no atoms and no raw Geometry")
            geometry = geometry_block(atoms, tree.format.get("PADDING", "  "))
        return {schema.input["FILENAME"]: geometry + self.render(tree)}
