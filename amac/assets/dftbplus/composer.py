"""Writing of ``dftb_in.hsd`` from the intermediate tree and the geometry."""

from __future__ import annotations

import io
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ase.io import write

from amac.parameter.composer import TreeComposer, _node
from amac.parameter.schema import resolve_name

if TYPE_CHECKING:
    from ase import Atoms

    from amac.parameter.composer import InputTree
    from amac.parameter.parameters import CalculationSpec, ExecutionSpec
    from amac.parameter.schema import Schema

GEOMETRY_BLOCK = "Geometry"
GEOMETRY_FORMAT = "GenFormat"
GRADIENT_MODULE = "GRADIENT"
RESULTS_TAG = ("Options", "WriteResultsTag")
PRINT_FORCES = ("Analysis", "Printforces")


def complete_tree(tree: InputTree, spec: CalculationSpec, schema: Schema) -> None:
    """Write the options AMAC needs to read the results, in place.

    ``Options { WriteResultsTag = Yes }`` gives the machine-readable
    ``results.tag`` that the parser prefers (decision D4), and the ``GRADIENT``
    module needs ``Analysis { Printforces = Yes }`` to get forces out of a static
    run. A value already placed by the user is never overwritten.

    Args:
        tree: Tree completed in place.
        spec: Calculation, to know the module.
        schema: Schema of the software, to resolve the module alias.
    """
    _set_default(tree, RESULTS_TAG, True)
    if resolve_name(schema.modules, spec.module, kind="module") == GRADIENT_MODULE:
        _set_default(tree, PRINT_FORCES, True)


def _set_default(tree: InputTree, path: tuple[str, ...], value: Any) -> None:
    node = _node(tree, path)
    if node.value is None:
        node.value = value


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
    ) -> dict[str, str]:
        """Return ``{"dftb_in.hsd": text}``.

        The geometry comes first, unless ``raw`` already defines a ``Geometry``
        block, which then wins.

        Args:
            spec: Calculation to write.
            schema: Schema of DFTB+.
            atoms: Geometry of the image.
            exec_spec: Execution specification, for ``INPUT.RESOURCES``.

        Returns:
            The input file name mapped to its content.

        Raises:
            ValueError: If ``atoms`` is ``None`` and ``raw`` defines no geometry.
        """
        tree = self.build_tree(spec, schema, exec_spec)
        complete_tree(tree, spec, schema)
        geometry = ""
        if not _geometry_given(tree, spec.raw):
            if atoms is None:
                raise ValueError("DFTB+ needs a geometry: no atoms and no raw Geometry")
            geometry = geometry_block(atoms, tree.format.get("PADDING", "  "))
        return {schema.input["FILENAME"]: geometry + self.render(tree)}
