"""Machine-level configuration file of AMAC.

AMAC reads no environment variable: the file is always given explicitly, either
to one calculator (``AMAC(config=...)``) or to the process
(:func:`set_config`, which :func:`amac.configure` calls). Without any of them the
configuration is empty: no executable and no ``env`` are found. Format::

    {
        "workdir": "~/amac-runs",
        "software": {
            "DFTB+": {
                "executable": "/opt/dftbplus-24.1/bin/dftb+",
                "env": {"BASIS": "/data/slako/3ob-3-1/"}
            },
            "deMonNano": {
                "executable": "/opt/demonnano/deMon.x",
                "env": {"BASIS": "/data/demonnano/basis/"}
            }
        }
    }

``workdir`` is the default root of the run directories, used when no ``workdir=``
is given; ``~`` is expanded and the result must be an absolute path.

Messages designate the object ``software`` -> ``<NAME>`` as ``[software.<NAME>]``.
A key may not appear twice in the same object. ``"executable": null`` means that
the executable is not set, and so does ``"workdir": null``.

Software names and aliases are resolved through the registry to the canonical
``NAME``. The file is read once per path; :func:`clear_config_cache` forgets it.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from amac.engine.registry import get_software
from amac.exceptions import ConfigurationError, SoftwareNotFoundError

SOFTWARE_KEYS = frozenset({"executable", "env"})
TOP_LEVEL_KEYS = frozenset({"software", "workdir"})
NO_CONFIG = "no configuration file (AMAC(config=...) or amac.set_config())"

# Configuration file of the process, set by set_config(); None means none.
_DEFAULT_PATH: Path | None = None


@dataclass(frozen=True)
class SoftwareConfig:
    """Settings of one software in the configuration file.

    Attributes:
        executable: Executable of the software, ``None`` when not set.
        env: Environment variables added to its runs.
    """

    executable: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    """Content of the configuration file.

    Attributes:
        path: Path of the file, ``None`` when no file was given.
        software: Settings keyed by canonical software name.
        workdir: Default root of the run directories, ``None`` when not set.
    """

    path: Path | None = None
    software: dict[str, SoftwareConfig] = field(default_factory=dict)
    workdir: Path | None = None

    def for_software(self, name: str) -> SoftwareConfig:
        """Return the settings of the canonical ``name``, empty when not set."""
        return self.software.get(name, SoftwareConfig())


def set_config(path: str | Path | None) -> None:
    """Set the configuration file of the process, or forget it with ``None``.

    It is used by every calculator that is not given its own ``config=``. The
    file is not read here: an invalid or missing one raises when it is needed.

    Args:
        path: Configuration file, ``~`` expanded; ``None`` leaves AMAC without
            any configuration.
    """
    global _DEFAULT_PATH
    _DEFAULT_PATH = None if path is None else Path(path).expanduser().absolute()


def config_path(path: str | Path | None = None) -> Path | None:
    """Return the configuration file that would be read, without reading it.

    Args:
        path: Configuration file of a calculator; ``None`` falls back to
            :func:`set_config`.

    Returns:
        The absolute path, ``None`` when there is no configuration at all.
    """
    if path is not None:
        return Path(path).expanduser().absolute()
    return _DEFAULT_PATH


def config_label(path: str | Path | None = None) -> str:
    """Return how a message designates the configuration file.

    Args:
        path: Configuration file of a calculator; ``None`` falls back to
            :func:`set_config`.

    Returns:
        The path of the file, or a sentence telling how to give one.
    """
    resolved = config_path(path)
    return NO_CONFIG if resolved is None else str(resolved)


def load_config(path: str | Path | None = None) -> Config:
    """Return the configuration file, read once per path.

    Args:
        path: Configuration file to read; ``None`` reads the one of
            :func:`set_config`, and gives an empty configuration without it.

    Raises:
        ConfigurationError: If the file does not exist, cannot be read, is not
            valid JSON, is not a JSON object, has a duplicated key, an unknown
            section or key, a value of the wrong type, a relative ``workdir``, an
            unknown software, or two sections for the same software. The message
            includes the path.
    """
    resolved = config_path(path)
    return Config() if resolved is None else _read(resolved)


def clear_config_cache() -> None:
    """Forget the files already read, so that the next access reads them again."""
    _read.cache_clear()


@functools.cache
def _read(path: Path) -> Config:
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream, object_pairs_hook=_unique_keys)
    except FileNotFoundError as err:
        raise ConfigurationError(f"Configuration file {path} does not exist") from err
    except OSError as err:
        raise ConfigurationError(
            f"Cannot read configuration file {path}: {err}"
        ) from err
    except _DuplicateKeyError as err:
        raise ConfigurationError(f"{path}: duplicated key {err}") from err
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise ConfigurationError(f"Invalid JSON in {path}: {err}") from err
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path}: the top level must be a JSON object")
    return Config(path, _parse(data, path), _parse_workdir(data.get("workdir"), path))


class _DuplicateKeyError(ValueError):
    """Raised by :func:`_unique_keys`; its message is the duplicated key."""


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object, refusing a key given twice (``json`` keeps the last)."""
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise _DuplicateKeyError(repr(key))
        data[key] = value
    return data


def _parse(data: dict[str, Any], path: Path) -> dict[str, SoftwareConfig]:
    if unknown := sorted(data.keys() - TOP_LEVEL_KEYS):
        raise ConfigurationError(
            f"{path}: unknown section(s) {', '.join(unknown)}; expected "
            f"{', '.join(sorted(TOP_LEVEL_KEYS))}"
        )
    sections = data.get("software", {})
    if not isinstance(sections, dict):
        raise ConfigurationError(
            f"{path}: 'software' must be an object of <NAME> objects"
        )
    software: dict[str, SoftwareConfig] = {}
    names: dict[str, str] = {}
    for name, section in sections.items():
        try:
            canonical = get_software(name).NAME
        except SoftwareNotFoundError as err:
            raise ConfigurationError(f"{path}: [software.{name}]: {err}") from err
        if canonical in names:
            raise ConfigurationError(
                f"{path}: [software.{names[canonical]}] and [software.{name}] both "
                f"configure {canonical}"
            )
        names[canonical] = name
        software[canonical] = _parse_section(section, f"{path}: [software.{name}]")
    return software


def _parse_section(section: Any, where: str) -> SoftwareConfig:
    if not isinstance(section, dict):
        raise ConfigurationError(f"{where} must be an object")
    if unknown := sorted(section.keys() - SOFTWARE_KEYS):
        raise ConfigurationError(
            f"{where}: unknown key(s) {', '.join(unknown)}; accepted: "
            f"{', '.join(sorted(SOFTWARE_KEYS))}"
        )
    executable = section.get("executable")
    if executable is not None and (not isinstance(executable, str) or not executable):
        raise ConfigurationError(f"{where}: executable must be a non-empty string")
    env = section.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
        raise ConfigurationError(f"{where}: env must be an object of strings")
    return SoftwareConfig(executable, dict(env))


def _parse_workdir(value: Any, path: Path) -> Path | None:
    """Return the ``workdir`` of the file, ``None`` when it is absent or null."""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{path}: workdir must be a non-empty string")
    directory = Path(value).expanduser()
    if not directory.is_absolute():
        raise ConfigurationError(
            f"{path}: workdir {value!r} must be an absolute path once ~ is expanded"
        )
    return directory
