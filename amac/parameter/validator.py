"""Validation of a ``CalculationSpec`` against the ``doc.json`` of a software.

How the spec is matched against the schema:

- ``spec.method`` designates a ``METHODS`` family and ``spec.module`` a ``MODULES``
  entry, by canonical key or alias, ignoring case.
- The reserved key ``"variant"`` (any case) of ``method_args`` or ``module_args``
  designates an entry of the ``VARIANTS`` of the method or module, e.g.
  ``method="DFT", method_args={"variant": "PBE0"}``. The same key selects a variant
  in the mapping value of an option declaring ``VARIANTS``.
- The other keys of ``method_args`` are matched against the ``ARGUMENTS`` of the
  family merged with those of the variant (the variant wins), the keys of
  ``module_args`` against the ``ARGUMENTS`` of the module and the keys of
  ``parameters`` against ``PARAMETERS`` and their ``COMPANION`` entries. A mapping
  value is matched against the ``ARGUMENTS`` of its node, recursively. Names and
  aliases ignore case.
- The ``SETS`` of a selected variant give values to its options: an absent option
  takes the imposed value, a different user value is an issue.
- A node without an ``ARGUMENTS`` key has undescribed content, which is not
  checked; ``"ARGUMENTS": {}`` accepts no option.
- A ``CHOICE`` value is either the choice itself (``"Broyden"``) or a one-item
  mapping ``{choice: options}``. The choice designates an entry of ``ARGUMENTS`` or
  of ``VARIANTS``; ``options`` is checked against that entry, merged with the
  ``COMMON_ARGUMENTS`` of the ``CHOICE``.
- ``raw`` is never validated, nor are the free-text ``CONDITION`` fields.

``MANDATORY_IF``, ``EXCLUDE_IF`` and ``REQUIRES`` follow the semantics documented in
``DOC_SCHEMA.md``: condition paths are input locations, built from
``PATH`` / ``TARGET`` and ``KEYWORD``.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from amac.exceptions import ValidationError
from amac.parameter.schema import resolve_name

if TYPE_CHECKING:
    from amac.parameter.parameters import CalculationSpec
    from amac.parameter.schema import Schema

MODES = ("strict", "warn", "off")
VARIANT_KEY = "VARIANT"
SET_VALUE = "SET"

type _Path = tuple[str, ...]
type _Groups = Iterable[tuple[Mapping[str, Any], _Path]]
type _Scope = tuple[dict[str, Any], dict[str, _Path]]


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "FLAG": lambda value: isinstance(value, bool),
    "INTEGER": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "REAL": _is_number,
    "STRING": lambda value: isinstance(value, str),
    "CHOICE": lambda value: (
        isinstance(value, str | int | float)
        or (isinstance(value, Mapping) and len(value) == 1)
    ),
    "LIST": lambda value: isinstance(value, list | tuple),
    "TABLE": lambda value: isinstance(value, list | tuple),
    "BLOCK": lambda value: isinstance(value, Mapping),
    "TREE": lambda value: isinstance(value, Mapping),
}


@dataclass(frozen=True)
class Issue:
    """Problem found in a calculation spec.

    Attributes:
        level: Severity; the generic rules only produce ``"error"``.
        path: Location in the spec, e.g. ``"parameters.SCF.MaxIter"``.
        message: Human-readable description.
    """

    level: str
    path: str
    message: str


def validate(
    spec: CalculationSpec,
    schema: Schema,
    mode: str = "strict",
    atoms: Any = None,
) -> list[Issue]:
    """Check ``spec`` against ``schema``.

    Args:
        spec: Calculation to check.
        schema: Schema of the software.
        mode: ``"strict"`` raises on any issue, ``"warn"`` emits one
            ``UserWarning`` per issue, ``"off"`` skips the validation.
        atoms: Object with a ``pbc`` attribute (bool or sequence of three bools),
            e.g. an ``ase.Atoms``; ``PERIODIC`` is only checked when it is given.

    Returns:
        The issues found. Always empty with ``"off"``, and with ``"strict"`` since
        issues raise.

    Raises:
        ValueError: If ``mode`` is unknown.
        TypeError: If ``atoms`` has no ``pbc`` attribute.
        ValidationError: In ``"strict"`` mode, if any issue is found; the message
            lists all of them.
    """
    if mode not in MODES:
        raise ValueError(
            f"Unknown validation mode {mode!r}; expected one of {', '.join(MODES)}"
        )
    if mode == "off":
        return []
    issues = _Checker(schema).check(spec, atoms)
    if issues and mode == "strict":
        details = "\n".join(f"  - {_format(issue)}" for issue in issues)
        raise ValidationError(
            f"Invalid calculation for {schema.data['SOFTWARE']}:\n{details}"
        )
    for issue in issues:
        warnings.warn(_format(issue), stacklevel=2)
    return issues


@dataclass(frozen=True)
class _Slot:
    """A declared node, with the nodes that surround it."""

    node: Mapping[str, Any]
    spec_path: str
    siblings: Mapping[str, Any]
    located: Mapping[str, _Path]


class _Checker:
    """Collects the issues of one spec.

    Values are first indexed by input location; conditions are evaluated once the
    whole spec has been read, so that they may refer to any option.
    """

    def __init__(self, schema: Schema) -> None:
        self.schema = schema
        self.issues: list[Issue] = []
        self.values: dict[_Path, Any] = {}
        self.present: list[_Slot] = []
        self.absent: list[_Slot] = []

    def check(self, spec: CalculationSpec, atoms: Any) -> list[Issue]:
        selected = self._check_entry(
            "METHODS", spec.method, spec.method_args, "method"
        )
        module = self._check_entry("MODULES", spec.module, spec.module_args, "module")
        self._check_arguments(
            _parameter_scope(self.schema), spec.parameters, "parameters"
        )
        self._check_conditions()
        if module:
            self._check_requires(module[0][1])
        if atoms is not None:
            self._check_periodic([*selected, *module], atoms)
        return self.issues

    def _error(self, path: str, message: str) -> None:
        self.issues.append(Issue("error", path, message))

    def _check_entry(
        self, section: str, name: str, args: Mapping[str, Any], spec_name: str
    ) -> list[tuple[str, Mapping[str, Any]]]:
        """Check a method or module and its arguments; return the selected nodes."""
        try:
            key = self.schema.resolve_alias(section, name)
        except ValidationError as err:
            self._error(spec_name, str(err))
            return []
        node = self.schema.data[section][key]
        location = _top_location(node)
        if location and node.get("KEYWORD"):
            self.values[_fold(location)] = node["KEYWORD"]
        args_path = f"{spec_name}_args"
        args = dict(args)
        selected = [(spec_name, node)]
        groups = []
        if "ARGUMENTS" in node:
            groups.append((node["ARGUMENTS"], _base(node, location)))
        sets, owner = None, ""
        if variant := self._select_variant(node, args, args_path):
            given_key, variant_key, variant_node = variant
            selected.append((f"{args_path}.{given_key}", variant_node))
            if "ARGUMENTS" in variant_node:
                variant_location = _declared_path(variant_node) or location
                groups.append(
                    (variant_node["ARGUMENTS"], _base(variant_node, variant_location))
                )
            sets, owner = variant_node.get("SETS"), f"variant {variant_key!r}"
        if groups:
            self._check_arguments(_locate(groups), args, args_path, sets, owner)
        elif sets:
            self._error(args_path, f"{owner} sets options but declares no ARGUMENTS")
        return selected

    def _select_variant(
        self, node: Mapping[str, Any], args: dict[str, Any], args_path: str
    ) -> tuple[str, str, Mapping[str, Any]] | None:
        """Pop the variant keys from ``args``.

        Returns:
            The given key, the canonical variant key and the variant node, or
            ``None`` when no valid variant is selected.
        """
        keys = [
            key for key in args if isinstance(key, str) and key.upper() == VARIANT_KEY
        ]
        if not keys:
            return None
        names = [args.pop(key) for key in keys]
        where = f"{args_path}.{keys[0]}"
        if len(names) > 1:
            self._error(args_path, f"variant is given several times: {keys}")
        elif "VARIANTS" not in node:
            self._error(where, "no VARIANTS are declared for this entry")
        elif not isinstance(names[0], str):
            self._error(where, f"variant must be a str, got {type(names[0]).__name__}")
        else:
            try:
                variant = resolve_name(node["VARIANTS"], names[0], kind="variant")
            except ValidationError as err:
                self._error(where, str(err))
            else:
                return keys[0], variant, node["VARIANTS"][variant]
        return None

    def _check_arguments(
        self,
        scope: _Scope,
        given: Mapping[str, Any],
        spec_path: str,
        sets: Mapping[str, Any] | None = None,
        owner: str = "",
    ) -> None:
        """Match ``given``, then the ``SETS`` of ``owner``, against ``scope``.

        ``scope`` maps each declared node to its key and its input location.
        """
        declared, located = scope
        seen: dict[str, tuple[str, Any]] = {}
        for name, value in given.items():
            if not isinstance(name, str):
                self._error(spec_path, f"option names must be str, got {name!r}")
                continue
            where = f"{spec_path}.{name}"
            try:
                key = resolve_name(declared, name, kind="option")
            except ValidationError as err:
                self._error(where, str(err))
                continue
            if key in seen:
                self._error(where, f"option {key!r} is given several times")
                continue
            seen[key] = (name, value)
            slot = _Slot(declared[key], where, declared, located)
            self._check_value(slot, value, located[key])
        for name, imposed in (sets or {}).items():
            try:
                key = resolve_name(declared, name, kind="option")
            except ValidationError as err:
                self._error(spec_path, f"{owner} sets {name!r}: {err}")
                continue
            if key in seen:
                given_name, value = seen[key]
                if not _same(value, imposed):
                    self._error(
                        f"{spec_path}.{given_name}",
                        f"{owner} sets {key} to {imposed!r}",
                    )
                continue
            seen[key] = (key, imposed)
            slot = _Slot(declared[key], f"{spec_path}.{key}", declared, located)
            self._check_value(slot, imposed, located[key])
        for key, node in declared.items():
            if key not in seen:
                self.absent.append(_Slot(node, f"{spec_path}.{key}", declared, located))

    def _check_value(self, slot: _Slot, value: Any, path: _Path) -> None:
        """Check ``TYPE``, ``VALUES`` and ``RANGE``, then the nested options."""
        node = slot.node
        self.present.append(slot)
        node_type = node.get("TYPE")
        type_check = _TYPE_CHECKS.get(node_type)
        if type_check is not None and not type_check(value):
            self._error(
                slot.spec_path, f"expected {node_type}, got {type(value).__name__}"
            )
            return
        choice, content, choice_node = value, None, None
        if node_type == "CHOICE":
            if isinstance(value, Mapping):
                ((choice, content),) = value.items()
            if isinstance(choice, str):
                choice, choice_node = _resolve_choice(node, choice)
        self.values[_fold(path)] = choice
        if "VALUES" in node:
            if not any(_same(choice, v) for v in node["VALUES"]):
                allowed = ", ".join(map(str, node["VALUES"]))
                self._error(slot.spec_path, f"{choice!r} is not one of: {allowed}")
        elif node_type == "CHOICE" and "VARIANTS" in node and choice_node is None:
            allowed = ", ".join(node["VARIANTS"])
            self._error(
                slot.spec_path, f"{choice!r} is not one of the variants: {allowed}"
            )
        if "RANGE" in node and _is_number(value):
            low, high = node["RANGE"]
            if not low <= value <= high:
                self._error(slot.spec_path, f"{value!r} is outside [{low}, {high}]")
        if node_type == "CHOICE":
            if choice_node is not None or "COMMON_ARGUMENTS" in node:
                self._check_choice(node, choice_node, choice, content, slot, path)
        elif isinstance(value, Mapping):
            if "VARIANTS" in node:
                self._check_variant_value(slot, value, path)
            elif "ARGUMENTS" in node:
                scope = _locate([(node["ARGUMENTS"], _base(node, path))])
                self._check_arguments(scope, value, slot.spec_path)

    def _check_variant_value(
        self, slot: _Slot, value: Mapping[str, Any], path: _Path
    ) -> None:
        """Check the mapping value of an option declaring ``VARIANTS``."""
        node = slot.node
        given = dict(value)
        groups = []
        if "ARGUMENTS" in node:
            groups.append((node["ARGUMENTS"], _base(node, path)))
        sets, owner = None, ""
        if variant := self._select_variant(node, given, slot.spec_path):
            _, variant_key, variant_node = variant
            self.values[_fold(path)] = variant_node.get("KEYWORD") or variant_key
            variant_location = _declared_path(variant_node) or path
            if "ARGUMENTS" in variant_node:
                groups.append(
                    (variant_node["ARGUMENTS"], _base(variant_node, variant_location))
                )
            sets, owner = variant_node.get("SETS"), f"variant {variant_key!r}"
        if groups:
            self._check_arguments(_locate(groups), given, slot.spec_path, sets, owner)
        elif sets:
            self._error(
                slot.spec_path, f"{owner} sets options but declares no ARGUMENTS"
            )

    def _check_choice(
        self,
        parent_node: Mapping[str, Any],
        choice_node: Mapping[str, Any] | None,
        choice: Any,
        content: Any,
        parent: _Slot,
        parent_path: _Path,
    ) -> None:
        node = choice_node or {}
        path = _declared_path(node) or (*parent_path, str(choice))
        where = f"{parent.spec_path}.{choice}"
        common = parent_node.get("COMMON_ARGUMENTS")
        if common is None:
            if content is not None:
                self._check_value(_Slot(node, where, {}, {}), content, path)
            elif "ARGUMENTS" in node:
                scope = _locate([(node["ARGUMENTS"], _base(node, path))])
                self._check_arguments(scope, {}, where)
            return
        if content is not None and not isinstance(content, Mapping):
            self._error(where, f"expected options, got {type(content).__name__}")
            return
        base = _base(node, path)
        groups = [(common, base)]
        if "ARGUMENTS" in node:
            groups.append((node["ARGUMENTS"], base))
        self._check_arguments(_locate(groups), content or {}, where)

    def _check_conditions(self) -> None:
        for slot in self.present:
            if condition := self._first_holding(slot, "EXCLUDE_IF"):
                self._error(slot.spec_path, f"excluded when {_describe(condition)}")
        for slot in self.absent:
            if slot.node.get("MANDATORY") is True:
                self._error(slot.spec_path, "mandatory option is missing")
            elif condition := self._first_holding(slot, "MANDATORY_IF"):
                self._error(slot.spec_path, f"mandatory when {_describe(condition)}")

    def _first_holding(self, slot: _Slot, key: str) -> Mapping[str, Any] | None:
        return next((c for c in slot.node.get(key, ()) if self._holds(c, slot)), None)

    def _holds(self, condition: Mapping[str, Any], slot: _Slot) -> bool:
        path = self._resolve(condition["PATH"], slot)
        if path not in self.values:
            return False
        expected = condition["VALUE"]
        return expected == SET_VALUE or _same(self.values[path], expected)

    def _resolve(self, path: Iterable[str], slot: _Slot) -> _Path:
        """Return the folded input location of a condition ``PATH``.

        The path is relative to a sibling of the slot when its first element names
        one, absolute otherwise.
        """
        head, *rest = path
        with suppress(ValidationError):
            key = resolve_name(slot.siblings, head, kind="option")
            return _fold((*slot.located[key], *rest))
        return _fold((head, *rest))

    def _check_requires(self, module: Mapping[str, Any]) -> None:
        arguments = module.get("ARGUMENTS", {})
        base = _base(module, _top_location(module))
        slot = _Slot(module, "module", *_locate([(arguments, base)]))
        for requirement in module.get("REQUIRES", ()):
            if not isinstance(requirement, str):
                if not self._holds(requirement, slot):
                    self._error("module", f"requires {_describe(requirement)}")
                continue
            try:
                key = self.schema.resolve_alias("PARAMETERS", requirement)
            except ValidationError as err:
                self._error("module", f"REQUIRES {requirement!r}: {err}")
                continue
            path = _declared_path(self.schema.parameters[key]) or (key,)
            if _fold(path) not in self.values:
                self._error("module", f"requires parameters.{key}")

    def _check_periodic(
        self, selected: Iterable[tuple[str, Mapping[str, Any]]], atoms: Any
    ) -> None:
        try:
            pbc = atoms.pbc
        except AttributeError as err:
            raise TypeError("atoms must have a pbc attribute") from err
        try:
            periodic = any(pbc)
        except TypeError:
            periodic = bool(pbc)
        for where, node in selected:
            match node.get("PERIODIC"), periodic:
                case "MOLECULE", True:
                    self._error(where, "atoms.pbc is periodic, MOLECULE only")
                case "PERIODIC", False:
                    self._error(where, "atoms.pbc is not periodic, PERIODIC only")


def _locate(groups: _Groups) -> _Scope:
    """Merge the declared nodes of ``groups`` and compute their input locations."""
    declared: dict[str, Any] = {}
    located: dict[str, _Path] = {}
    for nodes, scope in groups:
        for key, node in nodes.items():
            declared[key] = node
            located[key] = _declared_path(node) or (*scope, key)
    return declared, located


def _parameter_scope(schema: Schema) -> _Scope:
    """Declared ``PARAMETERS`` and their ``COMPANION`` entries, with locations.

    A companion without ``PATH`` is placed next to its owner: at the location of
    the owner without its last element, followed by the companion key.
    """
    declared, located = _locate([(schema.parameters, ())])
    for owner_key, owner in schema.parameters.items():
        if not isinstance(owner, Mapping):
            continue
        for key, companion in owner.get("COMPANION", {}).items():
            declared[key] = companion
            located[key] = _declared_path(companion) or (
                *located[owner_key][:-1],
                key,
            )
    return declared, located


def _resolve_choice(
    node: Mapping[str, Any], choice: str
) -> tuple[str, Mapping[str, Any] | None]:
    """Resolve a choice against ``ARGUMENTS``, then ``VARIANTS`` of a ``CHOICE``.

    Returns:
        The canonical key and its node, or ``choice`` unchanged and ``None`` when
        no entry matches (choices may be closed by ``VALUES`` only).
    """
    for section in ("ARGUMENTS", "VARIANTS"):
        nodes = node.get(section)
        if nodes is None:
            continue
        with suppress(ValidationError):
            key = resolve_name(nodes, choice, kind="choice")
            return key, nodes[key]
    return choice, None


def _declared_path(node: Mapping[str, Any], key: str = "PATH") -> _Path:
    value = node.get(key)
    return tuple(value) if isinstance(value, list | tuple) else ()


def _top_location(node: Mapping[str, Any]) -> _Path:
    """Input location of a method (``PATH``) or a module (``TARGET``)."""
    return _declared_path(node) or _declared_path(node, "TARGET")


def _base(node: Mapping[str, Any], location: _Path) -> _Path:
    """Input location under which the ``ARGUMENTS`` of ``node`` are placed."""
    keyword = node.get("KEYWORD")
    return (*location, keyword) if isinstance(keyword, str) and keyword else location


def _fold(path: Iterable[str]) -> _Path:
    return tuple(part.casefold() for part in path)


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.casefold() == expected.casefold()
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    return actual == expected


def _describe(condition: Mapping[str, Any]) -> str:
    target = ".".join(condition["PATH"])
    if condition["VALUE"] == SET_VALUE:
        return f"{target} is set"
    return f"{target} = {condition['VALUE']!r}"


def _format(issue: Issue) -> str:
    return f"{issue.path}: {issue.message}"
