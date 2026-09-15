"""Registry mapping software names and aliases to their ``Software`` class."""

from __future__ import annotations

import importlib
import inspect
from typing import TYPE_CHECKING

from amac.exceptions import SoftwareNotFoundError

if TYPE_CHECKING:
    from amac.engine.software import Software

_REGISTRY: dict[str, type[Software]] = {}


def _discover() -> None:
    # Imported on demand so that `import amac` stays light and free of cycles.
    importlib.import_module("amac.assets")


def register_software[S: Software](cls: type[S]) -> type[S]:
    """Register a software class under its ``NAME`` and ``ALIASES``.

    Names are stored upper-cased. Registering the same class again has no effect.

    Args:
        cls: Subclass of ``Software`` to register.

    Returns:
        The class itself, so the function can be used as a decorator.

    Raises:
        TypeError: If ``cls`` is not a concrete strict subclass of ``Software`` or if
            its ``NAME`` or ``ALIASES`` are not non-empty strings.
        ValueError: If a name or alias is already registered by another class.
    """
    from amac.engine.software import Software

    if not isinstance(cls, type) or not issubclass(cls, Software) or cls is Software:
        raise TypeError(f"{cls!r} is not a subclass of Software")
    if inspect.isabstract(cls):
        raise TypeError(f"{cls.__name__} is abstract and cannot be registered")
    names = (cls.NAME, *cls.ALIASES)
    if not all(isinstance(name, str) and name for name in names):
        raise TypeError(f"{cls.__name__}.NAME and ALIASES must be non-empty str")
    keys = {name.upper() for name in names}
    for key in keys:
        owner = _REGISTRY.get(key)
        if owner is not None and owner is not cls:
            raise ValueError(
                f"Software name {key!r} is already registered by {owner.__name__}"
            )
    _REGISTRY.update(dict.fromkeys(keys, cls))
    return cls


def get_software(name: str) -> type[Software]:
    """Return the software class registered under ``name`` (case-insensitive).

    Args:
        name: Canonical name or alias of the software.

    Returns:
        The registered ``Software`` subclass.

    Raises:
        TypeError: If ``name`` is not a str.
        SoftwareNotFoundError: If no software is registered under ``name``.
    """
    _discover()
    if not isinstance(name, str):
        raise TypeError(f"Software name must be a str, got {type(name).__name__}")
    try:
        return _REGISTRY[name.upper()]
    except KeyError:
        available = ", ".join(available_software())
        raise SoftwareNotFoundError(
            f"Unknown software {name!r}. Available software: {available}"
        ) from None


def available_software() -> list[str]:
    """Return the sorted canonical names of the registered software."""
    _discover()
    return sorted({cls.NAME for cls in _REGISTRY.values()})
