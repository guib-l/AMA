"""JSON storage of AMAC results.

File layout::

    {
        "format": "amac-results",
        "format_version": 1,
        "results": [
            {"success": ..., "properties": ..., "provenance": ..., "errors": ...}
        ]
    }

Encoding of the values:

- ``str``, ``int``, ``float``, ``bool``, ``None``, lists and dicts with str keys are
  written as they are; tuples become lists.
- ``numpy.ndarray`` of bool, int, uint or float dtype becomes
  ``{"__ndarray__": nested lists, "dtype": "float64", "shape": [n, 3]}`` and is
  restored with the same dtype and shape.
- numpy scalars become Python ``bool``, ``int`` or ``float``: the value is kept, the
  numpy type is not.
- ``Path`` becomes a str, restored as a str.
- ``ase.Atoms`` becomes ``{"__atoms__": geometry}``, restored as ``Atoms``.
- Exceptions become ``{"type", "message"}``, plus ``handler`` and ``missing_files``
  when relevant; they are restored as these dicts.
- Anything else, complex numbers included, raises ``TypeError``.

A geometry holds ``symbols``, ``positions``, ``cell`` and ``pbc``, plus
``initial_charges`` and ``initial_magnetic_moments`` when the atoms define them.
``info``, constraints and calculator are not kept. ``provenance["atoms"]`` is written
as a plain geometry (no tag) and restored as ``Atoms``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms

from amac.engine.context import Result
from amac.exceptions import HandlerError

FORMAT = "amac-results"
FORMAT_VERSION = 1
STORE_FORMATS = ("json",)
NDARRAY_TAG = "__ndarray__"
ATOMS_TAG = "__atoms__"

_ARRAY_KINDS = "biuf"


def store_results(
    results: Iterable[Result], filename: str | Path, format: str = "json"
) -> Path:
    """Write results to a JSON file.

    ``.json`` is appended to ``filename`` unless it already ends with it (any
    case). The contexts of the results are not stored. Every value is encoded
    before the file is opened, so an encoding error leaves no file behind.

    Args:
        results: Results to write.
        filename: Path of the file.
        format: Only ``"json"`` is supported.

    Returns:
        The path written.

    Raises:
        NotImplementedError: If ``format`` is not ``"json"``.
        TypeError: If a value cannot be encoded (see the module docstring).
    """
    if format not in STORE_FORMATS:
        raise NotImplementedError(
            f"Unsupported store format {format!r}; supported: "
            f"{', '.join(STORE_FORMATS)}"
        )
    data = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "results": [_encode_result(result) for result in results],
    }
    path = _json_path(filename)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=4)
    return path


def load_results(filename: str | Path) -> list[Result]:
    """Read results written by :func:`store_results`.

    ``filename`` follows the same rule as for :func:`store_results`: ``.json`` is
    appended unless it already ends with it. Errors are restored as dicts and
    contexts as ``None``.

    Args:
        filename: Path of the file.

    Returns:
        The results, in file order.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not valid JSON, is not an AMAC results file, or
            has an unsupported ``format_version``.
    """
    path = _json_path(filename)
    with path.open(encoding="utf-8") as stream:
        try:
            data = json.load(stream, object_hook=_decode_object)
        except json.JSONDecodeError as err:
            raise ValueError(f"{path} is not valid JSON: {err}") from err
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError(
            f"{path} is not an AMAC results file: missing format header {FORMAT!r}"
        )
    if (version := data.get("format_version")) != FORMAT_VERSION:
        raise ValueError(
            f"{path}: unsupported format_version {version!r}; "
            f"supported: {FORMAT_VERSION}"
        )
    if not isinstance(data.get("results"), list):
        raise ValueError(f"{path}: 'results' must be a list")
    return [_decode_result(item) for item in data["results"]]


def _json_path(filename: str | Path) -> Path:
    path = Path(filename)
    if path.suffix.lower() == ".json":
        return path
    return path.with_name(f"{path.name}.json")


def _encode_result(result: Result) -> dict[str, Any]:
    provenance = dict(result.provenance)
    if isinstance(provenance.get("atoms"), Atoms):
        provenance["atoms"] = _atoms_to_dict(provenance["atoms"])
    return {
        "success": result.success,
        "properties": _encode(result.properties),
        "provenance": _encode(provenance),
        "errors": _encode(result.errors),
    }


def _decode_result(item: dict[str, Any]) -> Result:
    provenance = item.get("provenance")
    if isinstance(provenance, dict) and isinstance(provenance.get("atoms"), dict):
        provenance["atoms"] = _dict_to_atoms(provenance["atoms"])
    return Result.from_dict(item)


def _encode(value: Any) -> Any:
    match value:
        case np.generic():
            if value.dtype.kind not in _ARRAY_KINDS:
                raise TypeError(f"Cannot store a numpy scalar of dtype {value.dtype}")
            return value.item()
        case np.ndarray():
            if value.dtype.kind not in _ARRAY_KINDS:
                raise TypeError(f"Cannot store an ndarray of dtype {value.dtype}")
            return {
                NDARRAY_TAG: value.tolist(),
                "dtype": str(value.dtype),
                "shape": list(value.shape),
            }
        case bool() | int() | float() | str() | None:
            return value
        case Path():
            return str(value)
        case Atoms():
            return {ATOMS_TAG: _atoms_to_dict(value)}
        case BaseException():
            return _encode_error(value)
        case Mapping():
            return {_check_key(key): _encode(item) for key, item in value.items()}
        case list() | tuple():
            return [_encode(item) for item in value]
    raise TypeError(f"Cannot store a value of type {type(value).__name__}")


def _check_key(key: Any) -> str:
    if not isinstance(key, str):
        raise TypeError(f"Stored dict keys must be str, got {key!r}")
    if key in (NDARRAY_TAG, ATOMS_TAG):
        raise TypeError(f"Dict key {key!r} is reserved by the AMAC store format")
    return key


def _encode_error(error: BaseException) -> dict[str, Any]:
    data: dict[str, Any] = {"type": type(error).__name__, "message": str(error)}
    if isinstance(error, HandlerError):
        if error.handler is not None:
            data["handler"] = error.handler
        if error.missing_files:
            data["missing_files"] = list(error.missing_files)
    return data


def _decode_object(obj: dict[str, Any]) -> Any:
    if NDARRAY_TAG in obj:
        return np.array(obj[NDARRAY_TAG], dtype=obj["dtype"]).reshape(obj["shape"])
    if ATOMS_TAG in obj:
        return _dict_to_atoms(obj[ATOMS_TAG])
    return obj


def _atoms_to_dict(atoms: Atoms) -> dict[str, Any]:
    data: dict[str, Any] = {
        "symbols": atoms.get_chemical_symbols(),
        "positions": atoms.get_positions().tolist(),
        "cell": atoms.cell.array.tolist(),
        "pbc": [bool(periodic) for periodic in atoms.pbc],
    }
    if atoms.has("initial_charges"):
        data["initial_charges"] = atoms.get_initial_charges().tolist()
    if atoms.has("initial_magmoms"):
        moments = atoms.get_initial_magnetic_moments().tolist()
        data["initial_magnetic_moments"] = moments
    return data


def _dict_to_atoms(data: Mapping[str, Any]) -> Atoms:
    atoms = Atoms(
        symbols=data["symbols"],
        positions=data["positions"],
        cell=data["cell"],
        pbc=data["pbc"],
    )
    if "initial_charges" in data:
        atoms.set_initial_charges(data["initial_charges"])
    if "initial_magnetic_moments" in data:
        atoms.set_initial_magnetic_moments(data["initial_magnetic_moments"])
    return atoms
