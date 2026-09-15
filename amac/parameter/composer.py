"""Generic translation of a calculation into software input files.

:func:`translate` turns a ``CalculationSpec`` into an :class:`InputTree`, a
software-independent intermediate tree built from the ``KEYWORD``, ``PATH`` and
``ALIASES`` of the ``doc.json``. Each syntax family renders this tree as text in a
:class:`Composer`; library drivers may read it directly.

Values are placed at the input locations documented in
``amac/assets/DOC_SCHEMA.md`` and used by the validator, so that condition paths and
tree paths designate the same locations. Variants of options, ``SETS``,
``COMPANION`` and ``COMMON_ARGUMENTS`` follow the same rules as in the validator.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from amac.exceptions import ValidationError
from amac.parameter.schema import resolve_name
from amac.parameter.validator import (
    VARIANT_KEY,
    _base,
    _declared_path,
    _locate,
    _parameter_scope,
    _resolve_choice,
    _same,
    _top_location,
)

if TYPE_CHECKING:
    from amac.parameter.parameters import CalculationSpec, ExecutionSpec, RawKeywords
    from amac.parameter.schema import Schema

DEFAULT_BOOLEAN = ("true", "false")
RESOURCE_KEYS = ("CPU", "RAM")

type _Path = tuple[str, ...]
type _Groups = list[tuple[Mapping[str, Any], _Path]]
type _Scope = tuple[dict[str, Any], dict[str, _Path]]


@dataclass
class Node:
    """Location of the software input.

    Attributes:
        value: Value written at the location, ``None`` when there is none (block).
        unit: ``UNIT`` of the schema node, ``None`` when not declared.
        format: ``INPUT.FORMAT_DEFAULTS`` merged with the ``FORMAT`` of the node.
        children: Sub-locations keyed by input name, in insertion order.
    """

    value: Any = None
    unit: str | None = None
    format: dict[str, Any] = field(default_factory=dict)
    children: dict[str, Node] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the node as plain JSON-compatible data."""
        return {
            "value": copy.deepcopy(self.value),
            "unit": self.unit,
            "format": copy.deepcopy(self.format),
            "children": {name: node.to_dict() for name, node in self.children.items()},
        }


@dataclass
class InputTree:
    """Intermediate, software-independent form of an input.

    Attributes:
        nodes: Top-level locations keyed by input name.
        keywords: ``KEYWORD`` of the method, variant or module that have no input
            location, in order of appearance and without duplicates.
        raw: ``CalculationSpec.raw``, copied unchanged and never validated.
        format: ``INPUT.FORMAT_DEFAULTS``, e.g. to render ``keywords``.
    """

    nodes: dict[str, Node] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)
    raw: RawKeywords = None
    format: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the tree as plain JSON-compatible data."""
        return {
            "nodes": {name: node.to_dict() for name, node in self.nodes.items()},
            "keywords": list(self.keywords),
            "raw": copy.deepcopy(self.raw),
            "format": copy.deepcopy(self.format),
        }


def merge_format(
    defaults: Mapping[str, Any], node: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge ``INPUT.FORMAT_DEFAULTS`` with the ``FORMAT`` of a schema node.

    The merge is shallow: a top-level key of ``FORMAT`` replaces the default one.

    Args:
        defaults: ``INPUT.FORMAT_DEFAULTS``.
        node: Schema node, with or without ``FORMAT``.

    Returns:
        A new plain dict.
    """
    return _thaw({**defaults, **node.get("FORMAT", {})})


def render_bool(value: bool, fmt: Mapping[str, Any]) -> str:
    """Return the text of a boolean according to ``FORMAT.BOOLEAN``.

    Args:
        value: Boolean to render.
        fmt: Merged format of the node.

    Returns:
        ``BOOLEAN[0]`` for true and ``BOOLEAN[1]`` for false, ``"true"`` /
        ``"false"`` when ``BOOLEAN`` is not declared.

    Raises:
        TypeError: If ``value`` is not a bool.
    """
    if not isinstance(value, bool):
        raise TypeError(f"expected a bool, got {type(value).__name__}")
    true, false = fmt.get("BOOLEAN", DEFAULT_BOOLEAN)
    return true if value else false


def render_unit(unit: str | None, fmt: Mapping[str, Any]) -> str | None:
    """Return the unit text of a node according to ``FORMAT``.

    ``FORMAT.UNITS`` maps a physical quantity (``"energy"``) to the unit name of the
    software; a ``UNIT`` absent from it is used as the unit name. The name is then
    inserted in ``FORMAT.MODIFIER`` (e.g. ``"[{unit}]"``) when declared. Values are
    not converted.

    Args:
        unit: ``UNIT`` of the node.
        fmt: Merged format of the node.

    Returns:
        The unit text, or ``None`` when ``unit`` is ``None``.
    """
    if unit is None:
        return None
    name = fmt.get("UNITS", {}).get(unit, unit)
    modifier = fmt.get("MODIFIER")
    return modifier.format(unit=name) if modifier else name


def translate(spec: CalculationSpec, schema: Schema) -> InputTree:
    """Translate a canonical calculation into the intermediate tree of a software.

    The ``SETS`` of a selected variant are written for the options the spec does not
    give; a value given by the spec is kept.

    Args:
        spec: Calculation to translate; it is not validated here.
        schema: Schema of the software.

    Returns:
        The intermediate tree, ``raw`` included unchanged.

    Raises:
        ValidationError: If a name cannot be resolved against the schema (unknown
            method, module, variant or declared option), or if two different
            values are placed at the same location.
    """
    return _Translator(schema).run(spec)


def inject_resources(
    tree: InputTree, schema: Schema, exec_spec: ExecutionSpec
) -> None:
    """Place ``cpu`` and ``ram`` at the locations given by ``INPUT.RESOURCES``.

    A resource without location, or whose value is ``None``, is not written.

    Args:
        tree: Tree completed in place.
        schema: Schema of the software.
        exec_spec: Execution specification.

    Raises:
        ValidationError: If another value is already placed at the location.
    """
    resources = schema.input.get("RESOURCES", {})
    values = (exec_spec.cpu, exec_spec.ram)
    for key, value in zip(RESOURCE_KEYS, values, strict=True):
        if (path := tuple(resources.get(key, ()))) and value is not None:
            _assign(_node(tree, path), value, path)


class Composer(ABC):
    """Writes the input files of a software.

    Attributes:
        SYNTAX: Syntax family handled by the composer, e.g. ``"TREE"``.
    """

    SYNTAX: ClassVar[str] = ""

    def build_tree(
        self, spec: CalculationSpec, schema: Schema, exec_spec: ExecutionSpec
    ) -> InputTree:
        """Return :func:`translate` completed by :func:`inject_resources`."""
        tree = translate(spec, schema)
        inject_resources(tree, schema, exec_spec)
        return tree

    @abstractmethod
    def compose(
        self,
        spec: CalculationSpec,
        schema: Schema,
        atoms: Any,
        exec_spec: ExecutionSpec,
    ) -> dict[str, str]:
        """Return the input files, file name mapped to content."""


class _PendingComposer(Composer):
    """Syntax family whose rendering is not implemented yet."""

    def compose(
        self,
        spec: CalculationSpec,
        schema: Schema,
        atoms: Any,
        exec_spec: ExecutionSpec,
    ) -> dict[str, str]:
        """Raise, the concrete composers are outside the core.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(f"The {self.SYNTAX} composer is not implemented")


class KeywordBlockComposer(_PendingComposer):
    """Keyword line and blocks (ORCA, Gaussian)."""

    SYNTAX = "KEYWORD_BLOCK"


class TreeComposer(_PendingComposer):
    """Hierarchical tree (DFTB+ HSD)."""

    SYNTAX = "TREE"


class NamelistComposer(_PendingComposer):
    """Fortran namelists and cards (Quantum Espresso)."""

    SYNTAX = "NAMELIST"


class FlatComposer(_PendingComposer):
    """One ``variable value`` per line (Abinit)."""

    SYNTAX = "FLAT"


_COMPOSERS: dict[str, type[Composer]] = {
    cls.SYNTAX: cls
    for cls in (KeywordBlockComposer, TreeComposer, NamelistComposer, FlatComposer)
}


def get_composer(syntax: str) -> type[Composer]:
    """Return the composer class of a ``SYNTAX`` family (case-insensitive).

    Args:
        syntax: ``SYNTAX`` of the ``doc.json``.

    Returns:
        The composer class.

    Raises:
        TypeError: If ``syntax`` is not a str.
        ValueError: If no composer handles ``syntax``.
    """
    if not isinstance(syntax, str):
        raise TypeError(f"syntax must be a str, got {type(syntax).__name__}")
    try:
        return _COMPOSERS[syntax.upper()]
    except KeyError:
        available = ", ".join(_COMPOSERS)
        raise ValueError(
            f"No composer for syntax {syntax!r}. Available: {available}"
        ) from None


class _Translator:
    """Builds the tree of one spec."""

    def __init__(self, schema: Schema) -> None:
        self.schema = schema
        defaults = schema.input.get("FORMAT_DEFAULTS", {})
        self.tree = InputTree(format=_thaw(defaults))

    def run(self, spec: CalculationSpec) -> InputTree:
        self._entry("METHODS", spec.method, spec.method_args)
        self._entry("MODULES", spec.module, spec.module_args)
        self._options(_parameter_scope(self.schema), spec.parameters)
        self.tree.raw = copy.deepcopy(spec.raw)
        return self.tree

    def _entry(self, section: str, name: str, args: Mapping[str, Any]) -> None:
        """Place a method or module, its variant and its arguments."""
        node = self.schema.data[section][self.schema.resolve_alias(section, name)]
        location = _top_location(node)
        self._keyword(node, location)
        args = dict(args)
        base = _base(node, location)
        groups: _Groups = []
        if "ARGUMENTS" in node:
            groups.append((node["ARGUMENTS"], base))
        sets = None
        if (variant := self._pop_variant(node, args)) is not None:
            self._keyword(variant, _declared_path(variant))
            base = _base(variant, _declared_path(variant) or location)
            if "ARGUMENTS" in variant:
                groups.append((variant["ARGUMENTS"], base))
            sets = variant.get("SETS")
        if groups:
            self._options(_locate(groups), args, sets)
        else:
            for key, value in args.items():
                self._copy((*base, key), value)

    def _keyword(self, node: Mapping[str, Any], location: _Path) -> None:
        keyword = node.get("KEYWORD")
        if location:
            _assign(self._node(location, node), keyword or None, location)
        elif keyword and keyword not in self.tree.keywords:
            self.tree.keywords.append(keyword)

    def _pop_variant(
        self, node: Mapping[str, Any], args: dict[str, Any]
    ) -> Mapping[str, Any] | None:
        keys = [k for k in args if isinstance(k, str) and k.upper() == VARIANT_KEY]
        if not keys:
            return None
        if len(keys) > 1:
            raise ValidationError(f"variant is given several times: {keys}")
        name = args.pop(keys[0])
        if "VARIANTS" not in node:
            raise ValidationError("no VARIANTS are declared for this entry")
        variants = node["VARIANTS"]
        return variants[resolve_name(variants, name, kind="variant")]

    def _options(
        self,
        scope: _Scope,
        given: Mapping[str, Any],
        sets: Mapping[str, Any] | None = None,
    ) -> None:
        declared, located = scope
        given_keys = set()
        for name, value in given.items():
            key = resolve_name(declared, name, kind="option")
            given_keys.add(key)
            self._value(declared[key], value, located[key])
        for name, value in (sets or {}).items():
            key = resolve_name(declared, name, kind="option")
            if key not in given_keys:
                self._value(declared[key], value, located[key])

    def _value(self, node: Mapping[str, Any], value: Any, path: _Path) -> None:
        target = self._node(path, node)
        if node.get("TYPE") == "CHOICE":
            self._choice(target, node, value, path)
        elif isinstance(value, Mapping):
            if "VARIANTS" in node:
                self._variant_value(target, node, value, path)
            elif "ARGUMENTS" in node:
                scope = _locate([(node["ARGUMENTS"], _base(node, path))])
                self._options(scope, value)
            else:
                for key, item in value.items():
                    self._copy((*path, key), item)
        else:
            _assign(target, value, path)

    def _variant_value(
        self,
        target: Node,
        node: Mapping[str, Any],
        value: Mapping[str, Any],
        path: _Path,
    ) -> None:
        """Place the mapping value of an option declaring ``VARIANTS``.

        The ``KEYWORD`` of the selected variant is the value of the option location;
        the arguments go under the base of the variant.
        """
        given = dict(value)
        base = _base(node, path)
        groups: _Groups = []
        if "ARGUMENTS" in node:
            groups.append((node["ARGUMENTS"], base))
        sets = None
        if (variant := self._pop_variant(node, given)) is not None:
            _assign(target, variant.get("KEYWORD") or None, path)
            base = _base(variant, _declared_path(variant) or path)
            if "ARGUMENTS" in variant:
                groups.append((variant["ARGUMENTS"], base))
            sets = variant.get("SETS")
        if groups:
            self._options(_locate(groups), given, sets)
        else:
            for key, item in given.items():
                self._copy((*base, key), item)

    def _choice(
        self,
        target: Node,
        node: Mapping[str, Any],
        value: Any,
        path: _Path,
    ) -> None:
        """Place a ``CHOICE`` given as ``choice`` or ``{choice: options}``."""
        choice, content = value, None
        if isinstance(value, Mapping) and len(value) == 1:
            ((choice, content),) = value.items()
        choice_node = None
        if isinstance(choice, str):
            choice, choice_node = _resolve_choice(node, choice)
        _assign(target, choice, path)
        if content is None:
            return
        choice_path = (_declared_path(choice_node) if choice_node else ()) or (
            *path,
            choice,
        )
        common = node.get("COMMON_ARGUMENTS")
        if common is not None and isinstance(content, Mapping):
            base = _base(choice_node or {}, choice_path)
            groups: _Groups = [(common, base)]
            if choice_node and "ARGUMENTS" in choice_node:
                groups.append((choice_node["ARGUMENTS"], base))
            self._options(_locate(groups), content)
        elif choice_node is None:
            self._copy((*path, choice), content)
        else:
            self._value(choice_node, content, choice_path)

    def _copy(self, path: _Path, value: Any) -> None:
        """Place content that the schema does not describe, names unchanged."""
        if not isinstance(path[-1], str):
            raise TypeError(f"option names must be str, got {path[-1]!r}")
        target = self._node(path)
        if isinstance(value, Mapping):
            for key, item in value.items():
                self._copy((*path, key), item)
        else:
            _assign(target, value, path)

    def _node(self, path: _Path, schema_node: Mapping[str, Any] | None = None) -> Node:
        node = _node(self.tree, path)
        if schema_node is not None:
            if "FORMAT" in schema_node:
                node.format = merge_format(self.tree.format, schema_node)
            if "UNIT" in schema_node:
                node.unit = schema_node["UNIT"]
        return node


def _node(tree: InputTree, path: _Path) -> Node:
    """Return the node at ``path``, created if needed; names ignore case."""
    if not path:
        raise ValueError("an input location cannot be empty")
    children = tree.nodes
    for part in path:
        folded = part.casefold()
        node = next((n for k, n in children.items() if k.casefold() == folded), None)
        if node is None:
            node = children[part] = Node(format=copy.deepcopy(tree.format))
        children = node.children
    return node


def _assign(node: Node, value: Any, path: _Path) -> None:
    if value is None:
        return
    if node.value is None:
        node.value = copy.deepcopy(value)
    elif not _same(node.value, value):
        raise ValidationError(
            f"Conflicting values at {'.'.join(path)}: {node.value!r} and {value!r}"
        )


def _thaw(value: Any) -> Any:
    match value:
        case Mapping():
            return {key: _thaw(item) for key, item in value.items()}
        case tuple() | list():
            return [_thaw(item) for item in value]
        case _:
            return value
