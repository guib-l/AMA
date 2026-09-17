"""Writing of ``orca.inp`` from the intermediate tree and the geometry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from amac.parameter.composer import KeywordBlockComposer

if TYPE_CHECKING:
    from ase import Atoms

    from amac.parameter.composer import InputTree
    from amac.parameter.parameters import CalculationSpec, ExecutionSpec
    from amac.parameter.schema import Schema

GEOMETRY_NODE = "*xyz"
GEOMETRY_KEYS = ("Charge", "Multiplicity")
CHARGE = "CHARGE"
MULTIPLICITY = "MULTIPLICITY"


def _find(tree: InputTree, name: str) -> str | None:
    """Return the key of ``tree.nodes`` equal to ``name``, case ignored."""
    folded = name.casefold()
    return next((key for key in tree.nodes if key.casefold() == folded), None)


def pop_geometry_arguments(tree: InputTree, schema: Schema) -> tuple[int, int]:
    """Remove the geometry node of ``tree`` and return its charge and multiplicity.

    ``CHARGE`` and ``MULTIPLICITY`` are ordinary ``PARAMETERS`` entries, placed by
    ``translate`` at ``["*xyz", ...]``. ORCA writes them on the ``* xyz`` line
    rather than in a block, so the node is taken out of the tree here and
    :func:`geometry_block` writes its values. A value the spec does not give
    falls back to the ``DEFAULT`` of the ``doc.json``.

    Args:
        tree: Tree modified in place.
        schema: Schema of ORCA, for the defaults.

    Returns:
        The charge and the multiplicity.
    """
    defaults = tuple(
        schema.parameters[key].get("DEFAULT") for key in (CHARGE, MULTIPLICITY)
    )
    key = _find(tree, GEOMETRY_NODE)
    if key is None:
        return defaults
    node = tree.nodes.pop(key)
    values = []
    for name, default in zip(GEOMETRY_KEYS, defaults, strict=True):
        child = next(
            (c for k, c in node.children.items() if k.casefold() == name.casefold()),
            None,
        )
        values.append(default if child is None or child.value is None else child.value)
    return values[0], values[1]


def scale_memory(tree: InputTree, schema: Schema, exec_spec: ExecutionSpec) -> None:
    """Turn the total memory written by ``inject_resources`` into memory per core.

    ``%maxcore`` is the memory of one ORCA process, while ``ExecutionSpec.ram`` is
    the memory of the whole run: the value is divided by the number of cores.

    Args:
        tree: Tree modified in place.
        schema: Schema of ORCA, for ``INPUT.RESOURCES``.
        exec_spec: Execution specification of the run.
    """
    path = tuple(schema.input.get("RESOURCES", {}).get("RAM", ()))
    if not path or exec_spec.ram is None:
        return
    node = tree.nodes.get(path[0])
    for part in path[1:]:
        node = None if node is None else node.children.get(part)
    if node is not None and node.value is not None:
        node.value = max(1, int(exec_spec.ram) // max(1, exec_spec.cpu))


def geometry_block(
    atoms: Atoms, charge: int, multiplicity: int, padding: str = "  "
) -> str:
    """Return the ``* xyz`` block of ``atoms``, in Angstrom.

    Args:
        atoms: Geometry of the calculation; ORCA is molecular, no cell is written.
        charge: Total charge.
        multiplicity: Spin multiplicity.
        padding: Indentation of one atom line.

    Returns:
        The block, ending with a newline.
    """
    lines = [f"* xyz {charge} {multiplicity}"]
    for atom in atoms:
        x, y, z = atom.position
        lines.append(f"{padding}{atom.symbol:<2s} {x:>15.8f} {y:>15.8f} {z:>15.8f}")
    lines.append("*")
    return "".join(f"{line}\n" for line in lines)


def _check_raw(raw: Any) -> None:
    """Refuse a ``raw`` dict redefining the reserved geometry node.

    Raises:
        ValueError: If ``raw`` names ``*xyz``, which the composer writes itself.
    """
    if isinstance(raw, Mapping) and any(
        isinstance(name, str) and name.casefold() == GEOMETRY_NODE
        for name in raw
    ):
        raise ValueError(
            f"{GEOMETRY_NODE} is written by the composer: pass the geometry as "
            "ase.Atoms, and the charge and multiplicity as parameters"
        )


class OrcaComposer(KeywordBlockComposer):
    """ORCA input: the ``!`` keyword line, the ``%`` blocks, then the geometry."""

    KEYWORD_PREFIX = "!"

    def compose(
        self,
        spec: CalculationSpec,
        schema: Schema,
        atoms: Any,
        exec_spec: ExecutionSpec,
    ) -> dict[str, str]:
        """Return ``{"orca.inp": text}``.

        The keyword line and the blocks are rendered by ``KeywordBlockComposer``;
        the ``* xyz`` block closes the file, as ORCA expects.

        Args:
            spec: Calculation to write.
            schema: Schema of ORCA.
            atoms: Geometry of the image.
            exec_spec: Execution specification, for ``INPUT.RESOURCES``.

        Returns:
            The input file name mapped to its content.

        Raises:
            ValueError: If ``atoms`` is ``None``, or if ``raw`` redefines the
                geometry node.
        """
        _check_raw(spec.raw)
        if atoms is None:
            raise ValueError("ORCA needs a geometry: no atoms given")
        tree = self.build_tree(spec, schema, exec_spec)
        charge, multiplicity = pop_geometry_arguments(tree, schema)
        scale_memory(tree, schema, exec_spec)
        padding = tree.format.get("PADDING", "  ")
        text = self.render(tree) + geometry_block(atoms, charge, multiplicity, padding)
        return {schema.input["FILENAME"]: text}
