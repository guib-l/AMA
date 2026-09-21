"""Loading of the ``doc.json`` files and read-only access to their content.

The expected format is described in ``docs/DOC_SCHEMA.md``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from amac.exceptions import ValidationError

REQUIRED_KEYS = (
    "SOFTWARE",
    "VERSION",
    "SYNTAX",
    "EXECUTION",
    "INPUT",
    "MODULES",
    "METHODS",
    "PARAMETERS",
    "OUTPUT",
)
_OBJECT_KEYS = ("INPUT", "MODULES", "METHODS", "PARAMETERS", "OUTPUT")
_ALIAS_SECTIONS = ("MODULES", "METHODS", "PARAMETERS")


def resolve_name(nodes: Mapping[str, Any], name: str, kind: str = "name") -> str:
    """Return the key of ``nodes`` designated by ``name``.

    The comparison ignores case. A key equal to ``name`` wins over the ``ALIASES``
    declared by the nodes.

    Args:
        nodes: Schema nodes keyed by canonical name, e.g. ``Schema.modules`` or an
            ``ARGUMENTS`` mapping.
        name: Name given by the user.
        kind: Word describing ``name`` in error messages.

    Returns:
        The canonical key.

    Raises:
        TypeError: If ``name`` is not a str.
        ValidationError: If ``name`` matches no key, or several keys.
    """
    if not isinstance(name, str):
        raise TypeError(f"{kind} must be a str, got {type(name).__name__}")
    folded = name.casefold()
    matches = [key for key in nodes if key.casefold() == folded]
    if not matches:
        matches = [
            key
            for key, node in nodes.items()
            if isinstance(node, Mapping)
            and any(alias.casefold() == folded for alias in node.get("ALIASES", ()))
        ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValidationError(
            f"Ambiguous {kind} {name!r}: matches {', '.join(matches)}"
        )
    available = ", ".join(nodes) or "none"
    raise ValidationError(f"Unknown {kind} {name!r}. Available: {available}")


@dataclass(frozen=True, eq=False)
class Schema:
    """Read-only content of a ``doc.json``.

    JSON objects are exposed as read-only mappings and arrays as tuples, so the
    instance shared by the cache of :func:`load` cannot be modified.

    Attributes:
        path: Resolved path of the ``doc.json``.
        data: Whole document.
    """

    path: Path
    data: Mapping[str, Any]

    @property
    def modules(self) -> Mapping[str, Any]:
        """``MODULES`` section: how the calculation is used (run types)."""
        return self.data["MODULES"]

    @property
    def methods(self) -> Mapping[str, Any]:
        """``METHODS`` section: which calculation is done."""
        return self.data["METHODS"]

    @property
    def parameters(self) -> Mapping[str, Any]:
        """``PARAMETERS`` section: general options."""
        return self.data["PARAMETERS"]

    @property
    def output(self) -> Mapping[str, Any]:
        """``OUTPUT`` section: produced files and retrievable quantities."""
        return self.data["OUTPUT"]

    @property
    def input(self) -> Mapping[str, Any]:
        """``INPUT`` section: input file name, geometry format, format defaults."""
        return self.data["INPUT"]

    @property
    def syntax(self) -> str:
        """Syntax family of the input, e.g. ``"TREE"``."""
        return self.data["SYNTAX"]

    @property
    def execution(self) -> tuple[str, ...]:
        """Supported execution kinds (``"FILEIO"`` and/or ``"INPROCESS"``)."""
        return self.data["EXECUTION"]

    def resolve_alias(self, section: str, name: str) -> str:
        """Return the canonical key of ``section`` designated by ``name``.

        Args:
            section: ``"MODULES"``, ``"METHODS"`` or ``"PARAMETERS"``, any case.
            name: Canonical key or alias, any case.

        Returns:
            The canonical key.

        Raises:
            ValueError: If ``section`` is not one of the sections above.
            TypeError: If ``name`` is not a str.
            ValidationError: If ``name`` is unknown or ambiguous in ``section``.
        """
        key = section.upper()
        if key not in _ALIAS_SECTIONS:
            raise ValueError(
                f"Unknown section {section!r}; expected one of "
                f"{', '.join(_ALIAS_SECTIONS)}"
            )
        return resolve_name(self.data[key], name, kind=f"{key} entry")


def load(path: str | Path) -> Schema:
    """Load a ``doc.json`` and check its top-level structure.

    Results are cached by resolved path: the file is read once per process, and
    later changes to it are not seen.

    Args:
        path: Path of the ``doc.json``.

    Returns:
        The read-only schema.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValidationError: If the file is not valid JSON or does not follow
            ``DOC_SCHEMA.md`` (missing top-level key, section not an object).
    """
    return _load(Path(path).resolve())


@lru_cache(maxsize=None)
def _load(path: Path) -> Schema:
    with path.open(encoding="utf-8") as stream:
        try:
            data = json.load(stream)
        except json.JSONDecodeError as err:
            raise ValidationError(f"{path} is not valid JSON: {err}") from err
    _check_structure(data, path)
    return Schema(path, _freeze(data))


def _check_structure(data: Any, path: Path) -> None:
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: the top level must be a JSON object")
    if missing := [key for key in REQUIRED_KEYS if key not in data]:
        raise ValidationError(f"{path}: missing top-level keys: {', '.join(missing)}")
    if wrong := [key for key in _OBJECT_KEYS if not isinstance(data[key], dict)]:
        raise ValidationError(f"{path}: must be JSON objects: {', '.join(wrong)}")


def _freeze(value: Any) -> Any:
    match value:
        case dict():
            return MappingProxyType({key: _freeze(item) for key, item in value.items()})
        case list():
            return tuple(_freeze(item) for item in value)
        case _:
            return value
