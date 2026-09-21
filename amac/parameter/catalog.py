"""Canonical catalog of AMAC and its links with the ``doc.json`` files.

The catalog (``catalog/<kind_dir>/<slug>/entry.json`` at the repository root, format
described in ``docs/CATALOG_SCHEMA.md``) names methods, modules and options independently
of any software. A ``doc.json`` node points to a catalog entry with ``CANONICAL``:
:func:`links` reads these pointers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from amac.engine.registry import available_software, get_software
from amac.exceptions import ValidationError
from amac.parameter.schema import Schema, _freeze, load, resolve_name

CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalog"
KINDS = ("METHOD", "MODULE", "OPTION")
KIND_DIRS = {"methods": "METHOD", "modules": "MODULE", "options": "OPTION"}
EQUIVALENCES = ("EXACT", "APPROX")
_ENTRY_FILE = "entry.json"
_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_LINKED_SECTIONS = ("MODULES", "METHODS", "PARAMETERS")
_LINK_KEYS = frozenset({"EQUIVALENCE", "NOTE", "SETS"})

type _Location = tuple[str, ...]


@dataclass(frozen=True)
class Entry:
    """Entry of the catalog.

    Attributes:
        id: Canonical name, unique in the whole catalog (case ignored, aliases
            included).
        kind: ``"METHOD"``, ``"MODULE"`` or ``"OPTION"``.
        parent: Id of the enclosing entry, ``None`` for a top-level entry.
        source: ``"<kind_dir>/<slug>"`` of the ``entry.json`` declaring the entry,
            e.g. ``"methods/dft"``.
        data: Read-only content of the entry, ``VARIANTS`` included.
    """

    id: str
    kind: str
    parent: str | None
    source: str
    data: Mapping[str, Any]

    @property
    def aliases(self) -> tuple[str, ...]:
        """Other names designating the entry."""
        return self.data.get("ALIASES", ())


@dataclass(frozen=True, eq=False)
class Catalog:
    """Read-only content of a catalog directory.

    Attributes:
        directory: Resolved root directory of the catalog.
        entries: Entries by id: kinds in ``KINDS`` order, slugs sorted
            alphabetically, each variant after its parent in declaration order.
    """

    directory: Path
    entries: Mapping[str, Entry]

    def resolve(self, name: str, kind: str | None = None) -> Entry:
        """Return the entry designated by an id or an alias, case ignored.

        Args:
            name: Id or alias.
            kind: Only search the entries of this kind, if given.

        Returns:
            The entry.

        Raises:
            ValueError: If ``kind`` is not one of ``KINDS``.
            TypeError: If ``name`` is not a str.
            ValidationError: If ``name`` designates no entry (of ``kind``).
        """
        if kind is not None:
            _check_kind(kind)
        nodes = {
            key: entry.data
            for key, entry in self.entries.items()
            if kind is None or entry.kind == kind
        }
        label = "catalog entry" if kind is None else f"catalog {kind}"
        return self.entries[resolve_name(nodes, name, kind=label)]

    def of_kind(self, kind: str) -> tuple[Entry, ...]:
        """Return the entries of a kind, in catalog order.

        Raises:
            ValueError: If ``kind`` is not one of ``KINDS``.
        """
        _check_kind(kind)
        return tuple(entry for entry in self.entries.values() if entry.kind == kind)

    def children(self, entry_id: str) -> tuple[Entry, ...]:
        """Return the direct variants of an entry, in declaration order.

        Raises:
            KeyError: If ``entry_id`` is not an id of the catalog.
        """
        if entry_id not in self.entries:
            raise KeyError(entry_id)
        return tuple(
            entry for entry in self.entries.values() if entry.parent == entry_id
        )


@dataclass(frozen=True)
class Link:
    """``CANONICAL`` pointer from a ``doc.json`` node to a catalog entry.

    Attributes:
        software: ``SOFTWARE`` of the ``doc.json``.
        canonical: Id of the catalog entry.
        location: Keys leading to the node in the ``doc.json``, e.g.
            ``("METHODS", "TIGHT_BINDING", "VARIANTS", "DFTB2")``.
        keyword: ``KEYWORD`` of the node when it is a non-empty str, else its key.
        equivalence: ``"EXACT"`` or ``"APPROX"``.
        sets: Values the options of the node take to express the entry.
        note: Free text qualifying the equivalence, if any.
    """

    software: str
    canonical: str
    location: _Location
    keyword: str
    equivalence: str
    sets: Mapping[str, Any]
    note: str | None


def load_catalog(directory: str | Path = CATALOG_DIR) -> Catalog:
    """Load and check every ``<kind_dir>/<slug>/entry.json`` of a catalog directory.

    Results are cached by resolved directory: the files are read once per process.
    Files directly under the root or a kind directory are ignored.

    Args:
        directory: Root directory of the catalog, the one of the repository by
            default.

    Returns:
        The read-only catalog.

    Raises:
        FileNotFoundError: If the directory holds no ``entry.json``.
        ValidationError: If the tree or an ``entry.json`` does not follow
            ``CATALOG_SCHEMA.md`` (unknown kind directory, invalid slug, missing
            ``entry.json``, invalid JSON or structure, duplicate names, unknown
            ``ACCEPTS``, required variant missing).
    """
    return _load_catalog(Path(directory).resolve())


@lru_cache(maxsize=None)
def _load_catalog(directory: Path) -> Catalog:
    paths = _entry_paths(directory)
    if not paths:
        raise FileNotFoundError(f"No catalog {_ENTRY_FILE} in {directory}")
    entries: dict[str, Entry] = {}
    for kind_dir, path in paths:
        data = _read(path)
        entry_id = data.pop("ID")
        source = f"{kind_dir}/{path.parent.name}"
        _collect(entries, entry_id, data, KIND_DIRS[kind_dir], None, source, path)
    _check_names(entries)
    _check_references(entries)
    return Catalog(directory, MappingProxyType(entries))


def _entry_paths(directory: Path) -> list[tuple[str, Path]]:
    subdirectories = sorted(path for path in directory.glob("*") if path.is_dir())
    for path in subdirectories:
        if path.name not in KIND_DIRS:
            raise ValidationError(
                f"{path}: not a catalog kind directory; expected one of "
                f"{', '.join(KIND_DIRS)}"
            )
    found = []
    for kind_dir in KIND_DIRS:
        slugs = (path for path in (directory / kind_dir).glob("*") if path.is_dir())
        for slug in sorted(slugs, key=lambda path: path.name):
            if not _SLUG.fullmatch(slug.name):
                raise ValidationError(
                    f"{slug}: invalid slug, expected lowercase words of letters and "
                    "digits separated by '-'"
                )
            path = slug / _ENTRY_FILE
            if not path.is_file():
                raise ValidationError(f"{slug}: missing {_ENTRY_FILE}")
            found.append((kind_dir, path))
    return found


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        try:
            data = json.load(stream)
        except json.JSONDecodeError as err:
            raise ValidationError(f"{path} is not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: the top level must be a JSON object")
    entry_id = data.get("ID")
    if not isinstance(entry_id, str) or not entry_id:
        raise ValidationError(f"{path}: ID must be a non-empty str")
    return data


def _collect(
    entries: dict[str, Entry],
    key: str,
    node: Any,
    kind: str,
    parent: str | None,
    source: str,
    path: Path,
) -> None:
    where = f"{path}: {key}"
    if not isinstance(node, dict):
        raise ValidationError(f"{where} must be a JSON object")
    if "ID" in node:
        raise ValidationError(f"{where}: ID is only allowed at the top level")
    if key in entries:
        raise ValidationError(
            f"{where} is already declared in {entries[key].source}/{_ENTRY_FILE}"
        )
    for field in ("ALIASES", "ACCEPTS"):
        value = node.get(field, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise ValidationError(f"{where}: {field} must be a list of non-empty str")
    if not isinstance(node.get("VARIANT_REQUIRED", False), bool):
        raise ValidationError(f"{where}: VARIANT_REQUIRED must be a boolean")
    variants = node.get("VARIANTS", {})
    if not isinstance(variants, dict):
        raise ValidationError(f"{where}: VARIANTS must be a JSON object")
    entries[key] = Entry(key, kind, parent, source, _freeze(node))
    for name, variant in variants.items():
        _collect(entries, name, variant, kind, key, source, path)


def _check_names(entries: Mapping[str, Entry]) -> None:
    owners: dict[str, str] = {}
    for entry in entries.values():
        for name in (entry.id, *entry.aliases):
            owner = owners.setdefault(name.casefold(), entry.id)
            if owner != entry.id:
                raise ValidationError(
                    f"{entry.source}/{_ENTRY_FILE}: name {name!r} of {entry.id} is "
                    f"already used by {owner}"
                )


def _check_references(entries: Mapping[str, Entry]) -> None:
    for entry in entries.values():
        for axis in entry.data.get("ACCEPTS", ()):
            target = entries.get(axis)
            if target is None or target.kind != "OPTION" or target.parent is not None:
                raise ValidationError(
                    f"{entry.source}/{_ENTRY_FILE}: {entry.id} ACCEPTS {axis!r}, "
                    "which is not an option axis"
                )
        if entry.data.get("VARIANT_REQUIRED") and not any(
            other.parent == entry.id for other in entries.values()
        ):
            raise ValidationError(
                f"{entry.source}/{_ENTRY_FILE}: {entry.id} requires a variant but "
                "has none"
            )


def links(schema: Schema, catalog: Catalog | None = None) -> tuple[Link, ...]:
    """Return the ``CANONICAL`` links of a ``doc.json``, in document order.

    Nodes are searched at any depth of ``MODULES``, ``METHODS`` and ``PARAMETERS``.

    Args:
        schema: Schema of the software.
        catalog: Catalog to link to, the one of the repository by default.

    Returns:
        One link per catalog id named by each ``CANONICAL``.

    Raises:
        ValidationError: If a ``CANONICAL`` is malformed, names an unknown id or an
            alias instead of the id, links a module from outside ``MODULES`` or
            ``MODULES`` to another kind, or if its ``SETS`` name an option the node
            does not declare or a value its ``VALUES`` do not allow.
    """
    catalog = load_catalog() if catalog is None else catalog
    found: list[Link] = []
    for section in _LINKED_SECTIONS:
        for location, node in _walk(schema.data[section], (section,)):
            if "CANONICAL" in node:
                found.extend(_node_links(schema, catalog, location, node))
    return tuple(found)


def _walk(
    node: Mapping[str, Any], location: _Location
) -> Iterator[tuple[_Location, Mapping[str, Any]]]:
    yield location, node
    for key, value in node.items():
        if key != "CANONICAL" and isinstance(value, Mapping):
            yield from _walk(value, (*location, key))


def _node_links(
    schema: Schema, catalog: Catalog, location: _Location, node: Mapping[str, Any]
) -> Iterator[Link]:
    where = f"{schema.path}: {'/'.join(location)}"
    raw = node["CANONICAL"]
    if isinstance(raw, str):
        targets: Mapping[str, Any] = {raw: MappingProxyType({})}
    elif isinstance(raw, Mapping) and raw:
        targets = raw
    else:
        raise ValidationError(
            f"{where}: CANONICAL must be a catalog id or a non-empty object"
        )
    keyword = node.get("KEYWORD")
    if not isinstance(keyword, str) or not keyword:
        keyword = location[-1]
    for canonical, details in targets.items():
        entry = _linked_entry(catalog, canonical, location[0], where)
        if not isinstance(details, Mapping):
            raise ValidationError(f"{where}: CANONICAL {canonical!r} must map to an object")
        if unknown := sorted(details.keys() - _LINK_KEYS):
            raise ValidationError(
                f"{where}: unknown keys in CANONICAL {canonical!r}: {', '.join(unknown)}"
            )
        equivalence = details.get("EQUIVALENCE", "EXACT")
        if equivalence not in EQUIVALENCES:
            raise ValidationError(
                f"{where}: EQUIVALENCE must be one of {', '.join(EQUIVALENCES)}, "
                f"got {equivalence!r}"
            )
        note = details.get("NOTE")
        if note is not None and not isinstance(note, str):
            raise ValidationError(f"{where}: NOTE must be a str")
        sets = details.get("SETS", MappingProxyType({}))
        _check_link_sets(node, sets, where)
        yield Link(
            schema.data["SOFTWARE"], entry.id, location, keyword, equivalence, sets, note
        )


def _linked_entry(catalog: Catalog, canonical: str, section: str, where: str) -> Entry:
    entry = catalog.entries.get(canonical)
    if entry is None:
        try:
            match = catalog.resolve(canonical)
        except ValidationError:
            raise ValidationError(f"{where}: unknown catalog id {canonical!r}") from None
        raise ValidationError(
            f"{where}: CANONICAL must use the catalog id {match.id!r}, not {canonical!r}"
        )
    if (section == "MODULES") != (entry.kind == "MODULE"):
        raise ValidationError(
            f"{where}: {entry.kind} {entry.id!r} cannot be linked from {section}"
        )
    return entry


def _check_link_sets(node: Mapping[str, Any], sets: Any, where: str) -> None:
    if not isinstance(sets, Mapping):
        raise ValidationError(f"{where}: SETS must be an object")
    arguments = {**node.get("COMMON_ARGUMENTS", {}), **node.get("ARGUMENTS", {})}
    for name, value in sets.items():
        try:
            key = resolve_name(arguments, name, kind="SETS option")
        except ValidationError as err:
            raise ValidationError(f"{where}: {err}") from None
        option = arguments[key]
        allowed = option.get("VALUES") if isinstance(option, Mapping) else None
        if (
            allowed
            and isinstance(value, str)
            and value.casefold() not in {str(item).casefold() for item in allowed}
        ):
            raise ValidationError(
                f"{where}: SETS gives {key} the value {value!r}, expected one of "
                f"{', '.join(map(str, allowed))}"
            )


def documented_software() -> dict[str, Schema]:
    """Return the schema of each registered software that has a ``doc.json``.

    Software defined in a private module (a segment of its dotted path starts with
    ``_``, such as the test dummies) is left out, as is a ``doc.json`` already
    returned for another software.

    Returns:
        Schemas by canonical software name, sorted by name.
    """
    schemas: dict[str, Schema] = {}
    for name in available_software():
        cls = get_software(name)
        if cls.DOC is None or any(
            part.startswith("_") for part in cls.__module__.split(".")
        ):
            continue
        schema = load(cls.DOC)
        if all(known is not schema for known in schemas.values()):
            schemas[name] = schema
    return schemas


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"Unknown kind {kind!r}; expected one of {', '.join(KINDS)}")
