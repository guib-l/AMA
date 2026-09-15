"""Canonical catalog of AMAC and its links with the ``doc.json`` files.

The catalog (``amac/assets/catalog/*.json``, format described in
``amac/assets/CATALOG_SCHEMA.md``) names methods, modules and options independently
of any software. A ``doc.json`` node points to a catalog entry with ``CANONICAL``:
:func:`links` reads these pointers, :func:`availability` gathers them into
cross-software equivalence tables and :func:`write_availability` writes them to the
``available_*.json`` files (``python -m amac.assets.catalog``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from amac.engine.registry import available_software, get_software
from amac.exceptions import ValidationError
from amac.parameter.schema import Schema, _freeze, load, resolve_name

CATALOG_DIR = Path(__file__).resolve().parents[1] / "assets" / "catalog"
KINDS = ("METHOD", "MODULE", "OPTION")
EQUIVALENCES = ("EXACT", "APPROX")
OUTPUT_FILES = {
    "METHOD": "available_methods.json",
    "MODULE": "available_modules.json",
    "OPTION": "available_options.json",
}
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
        parent: Id of the family or axis the entry is a variant of, ``None`` for a
            top-level entry.
        source: Stem of the catalog file declaring the entry, e.g. ``"functionals"``.
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
        directory: Resolved directory of the catalog files.
        entries: Entries by id, in file then declaration order, each variant after
            its parent.
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
        """Return the variants of an entry, whatever file declares them.

        Raises:
            KeyError: If ``entry_id`` is not an id of the catalog.
        """
        if entry_id not in self.entries:
            raise KeyError(entry_id)
        return tuple(entry for entry in self.entries.values() if entry.parent == entry_id)


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
    """Load and check every ``*.json`` file of a catalog directory.

    Results are cached by resolved directory: the files are read once per process.

    Args:
        directory: Catalog directory, the one of the package by default.

    Returns:
        The read-only catalog.

    Raises:
        FileNotFoundError: If the directory holds no JSON file.
        ValidationError: If a file is not valid JSON or does not follow
            ``CATALOG_SCHEMA.md`` (structure, duplicate names, unknown ``PARENT``
            or ``ACCEPTS``, required variant missing).
    """
    return _load_catalog(Path(directory).resolve())


@lru_cache(maxsize=None)
def _load_catalog(directory: Path) -> Catalog:
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No catalog file in {directory}")
    entries: dict[str, Entry] = {}
    parents: list[tuple[Path, str, str]] = []
    for path in paths:
        data = _read(path)
        parent = data.get("PARENT")
        if parent is not None:
            parents.append((path, parent, data["KIND"]))
        for key, node in data["ENTRIES"].items():
            _collect(entries, key, node, data["KIND"], parent, path)
    for path, parent, kind in parents:
        owner = entries.get(parent)
        if owner is None or owner.kind != kind:
            raise ValidationError(f"{path}: PARENT {parent!r} is not a {kind} entry")
    _check_names(entries)
    _check_references(entries)
    return Catalog(directory, MappingProxyType(entries))


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        try:
            data = json.load(stream)
        except json.JSONDecodeError as err:
            raise ValidationError(f"{path} is not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: the top level must be a JSON object")
    if missing := [key for key in ("CATALOG", "KIND", "ENTRIES") if key not in data]:
        raise ValidationError(f"{path}: missing top-level keys: {', '.join(missing)}")
    if data["KIND"] not in KINDS:
        raise ValidationError(
            f"{path}: KIND must be one of {', '.join(KINDS)}, got {data['KIND']!r}"
        )
    if not isinstance(data["ENTRIES"], dict):
        raise ValidationError(f"{path}: ENTRIES must be a JSON object")
    if not isinstance(data.get("PARENT", ""), str):
        raise ValidationError(f"{path}: PARENT must be a str")
    return data


def _collect(
    entries: dict[str, Entry],
    key: str,
    node: Any,
    kind: str,
    parent: str | None,
    path: Path,
) -> None:
    where = f"{path}: {key}"
    if not isinstance(node, dict):
        raise ValidationError(f"{where} must be a JSON object")
    if key in entries:
        raise ValidationError(f"{where} is already declared in {entries[key].source}.json")
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
    entries[key] = Entry(key, kind, parent, path.stem, _freeze(node))
    for name, variant in variants.items():
        _collect(entries, name, variant, kind, key, path)


def _check_names(entries: Mapping[str, Entry]) -> None:
    owners: dict[str, str] = {}
    for entry in entries.values():
        for name in (entry.id, *entry.aliases):
            owner = owners.setdefault(name.casefold(), entry.id)
            if owner != entry.id:
                raise ValidationError(
                    f"{entry.source}.json: name {name!r} of {entry.id} is already "
                    f"used by {owner}"
                )


def _check_references(entries: Mapping[str, Entry]) -> None:
    for entry in entries.values():
        for axis in entry.data.get("ACCEPTS", ()):
            target = entries.get(axis)
            if target is None or target.kind != "OPTION" or target.parent is not None:
                raise ValidationError(
                    f"{entry.source}.json: {entry.id} ACCEPTS {axis!r}, which is not "
                    "an option axis"
                )
        if entry.data.get("VARIANT_REQUIRED") and not any(
            other.parent == entry.id for other in entries.values()
        ):
            raise ValidationError(
                f"{entry.source}.json: {entry.id} requires a variant but has none"
            )


def links(schema: Schema, catalog: Catalog | None = None) -> tuple[Link, ...]:
    """Return the ``CANONICAL`` links of a ``doc.json``, in document order.

    Nodes are searched at any depth of ``MODULES``, ``METHODS`` and ``PARAMETERS``.

    Args:
        schema: Schema of the software.
        catalog: Catalog to link to, the one of the package by default.

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


def availability(
    kind: str,
    schemas: Mapping[str, Schema] | None = None,
    catalog: Catalog | None = None,
) -> dict[str, dict[str, tuple[Link, ...]]]:
    """Return which software implements each catalog entry of a kind.

    Args:
        kind: ``"METHOD"``, ``"MODULE"`` or ``"OPTION"``.
        schemas: Schemas by software name, :func:`documented_software` by default.
        catalog: Catalog to use, the one of the package by default.

    Returns:
        For each entry of ``kind``, in catalog order, the links of each software in
        the order of ``schemas``; an empty tuple means the software does not
        implement the entry.

    Raises:
        ValueError: If ``kind`` is not one of ``KINDS``.
        ValidationError: If a ``CANONICAL`` link is invalid.
    """
    catalog = load_catalog() if catalog is None else catalog
    schemas = documented_software() if schemas is None else schemas
    table = {entry.id: {name: [] for name in schemas} for entry in catalog.of_kind(kind)}
    for name, schema in schemas.items():
        for link in links(schema, catalog):
            if link.canonical in table:
                table[link.canonical][name].append(link)
    return {
        entry_id: {name: tuple(found) for name, found in row.items()}
        for entry_id, row in table.items()
    }


def available(
    name: str,
    schemas: Mapping[str, Schema] | None = None,
    catalog: Catalog | None = None,
) -> dict[str, tuple[Link, ...]]:
    """Return the implementations of a catalog entry in each software.

    Args:
        name: Id or alias of the entry, case ignored, e.g. ``"scc-dftb"``.
        schemas: Schemas by software name, :func:`documented_software` by default.
        catalog: Catalog to use, the one of the package by default.

    Returns:
        Links by software name; an empty tuple means the software does not
        implement the entry.

    Raises:
        TypeError: If ``name`` is not a str.
        ValidationError: If ``name`` designates no entry, or a link is invalid.
    """
    catalog = load_catalog() if catalog is None else catalog
    entry = catalog.resolve(name)
    return availability(entry.kind, schemas, catalog)[entry.id]


def availability_document(
    kind: str,
    schemas: Mapping[str, Schema] | None = None,
    catalog: Catalog | None = None,
) -> dict[str, Any]:
    """Return the JSON content of the equivalence table of a kind.

    Args:
        kind: ``"METHOD"``, ``"MODULE"`` or ``"OPTION"``.
        schemas: Schemas by software name, :func:`documented_software` by default.
        catalog: Catalog to use, the one of the package by default.

    Returns:
        ``KIND``, ``SOFTWARE`` (version of each ``doc.json``) and ``ENTRIES``: for
        each entry, its ``PARENT`` and, per software, the list of its links or
        ``None`` when the software does not implement it.

    Raises:
        ValueError: If ``kind`` is not one of ``KINDS``.
        ValidationError: If a ``CANONICAL`` link is invalid.
    """
    catalog = load_catalog() if catalog is None else catalog
    schemas = documented_software() if schemas is None else schemas
    table = availability(kind, schemas, catalog)
    return {
        "KIND": kind,
        "GENERATED_BY": "python -m amac.assets.catalog",
        "SOFTWARE": {name: schema.data["VERSION"] for name, schema in schemas.items()},
        "ENTRIES": {
            entry_id: {
                "PARENT": catalog.entries[entry_id].parent,
                "SOFTWARE": {
                    name: [_link_content(link) for link in found] or None
                    for name, found in row.items()
                },
            }
            for entry_id, row in table.items()
        },
    }


def write_availability(
    directory: str | Path = ".",
    schemas: Mapping[str, Schema] | None = None,
    catalog: Catalog | None = None,
) -> list[Path]:
    """Write the equivalence table of each kind, named after ``OUTPUT_FILES``.

    Args:
        directory: Existing output directory.
        schemas: Schemas by software name, :func:`documented_software` by default.
        catalog: Catalog to use, the one of the package by default.

    Returns:
        The written paths, in the order of ``OUTPUT_FILES``.

    Raises:
        ValidationError: If a ``CANONICAL`` link is invalid.
    """
    schemas = documented_software() if schemas is None else schemas
    written = []
    for kind, filename in OUTPUT_FILES.items():
        path = Path(directory) / filename
        document = availability_document(kind, schemas, catalog)
        text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def _link_content(link: Link) -> dict[str, Any]:
    content: dict[str, Any] = {
        "LOCATION": "/".join(link.location),
        "KEYWORD": link.keyword,
        "EQUIVALENCE": link.equivalence,
    }
    if link.sets:
        content["SETS"] = _thaw(link.sets)
    if link.note is not None:
        content["NOTE"] = link.note
    return content


def _thaw(value: Any) -> Any:
    match value:
        case Mapping():
            return {key: _thaw(item) for key, item in value.items()}
        case tuple():
            return [_thaw(item) for item in value]
        case _:
            return value


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"Unknown kind {kind!r}; expected one of {', '.join(KINDS)}")
