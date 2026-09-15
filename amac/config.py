"""Machine-level configuration file of AMAC.

The file is ``$AMAC_CONFIG`` when this variable is set and non-empty, otherwise
``$XDG_CONFIG_HOME/amac/config.toml``, with ``XDG_CONFIG_HOME`` defaulting to
``~/.config``. A missing default file is an empty configuration. Format::

    [software.ORCA]
    executable = "/opt/orca-6.1.0/orca"
    env = { LD_LIBRARY_PATH = "/opt/openmpi-4.1/lib" }

    [software."DFTB+"]
    executable = "dftb+"
    env = { DFTB_PREFIX = "/data/slako/3ob-3-1/" }

Software names and aliases are resolved through the registry to the canonical
``NAME``. The file is read once per path; :func:`clear_config_cache` forgets it.
"""

from __future__ import annotations

import functools
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from amac.engine.registry import get_software
from amac.exceptions import ConfigurationError, SoftwareNotFoundError

CONFIG_ENV = "AMAC_CONFIG"
SOFTWARE_KEYS = frozenset({"executable", "env"})


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
        path: Path of the file, even when it does not exist.
        software: Settings keyed by canonical software name.
    """

    path: Path
    software: dict[str, SoftwareConfig] = field(default_factory=dict)

    def for_software(self, name: str) -> SoftwareConfig:
        """Return the settings of the canonical ``name``, empty when not set."""
        return self.software.get(name, SoftwareConfig())


def config_path() -> Path:
    """Return the path of the configuration file, without reading it."""
    return _config_location()[0]


def load_config() -> Config:
    """Return the configuration file, read once per path.

    Raises:
        ConfigurationError: If ``$AMAC_CONFIG`` names a missing file, or if the
            file cannot be read, is not valid TOML, has an unknown section or key,
            a value of the wrong type, an unknown software, or two sections for the
            same software. The message includes the path.
    """
    return _read(*_config_location())


def clear_config_cache() -> None:
    """Forget the files already read, so that the next access reads them again."""
    _read.cache_clear()


def _config_location() -> tuple[Path, bool]:
    """Return the path of the file and whether ``$AMAC_CONFIG`` gave it."""
    if explicit := os.environ.get(CONFIG_ENV):
        return Path(explicit).expanduser().absolute(), True
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return (Path(base) / "amac" / "config.toml").absolute(), False


@functools.cache
def _read(path: Path, explicit: bool) -> Config:
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except FileNotFoundError as err:
        if not explicit:
            return Config(path)
        raise ConfigurationError(
            f"Configuration file {path} (${CONFIG_ENV}) does not exist"
        ) from err
    except OSError as err:
        raise ConfigurationError(
            f"Cannot read configuration file {path}: {err}"
        ) from err
    except tomllib.TOMLDecodeError as err:
        raise ConfigurationError(f"Invalid TOML in {path}: {err}") from err
    return Config(path, _parse(data, path))


def _parse(data: dict[str, Any], path: Path) -> dict[str, SoftwareConfig]:
    if unknown := sorted(data.keys() - {"software"}):
        raise ConfigurationError(
            f"{path}: unknown section(s) {', '.join(unknown)}; expected "
            "[software.<NAME>]"
        )
    sections = data.get("software", {})
    if not isinstance(sections, dict):
        raise ConfigurationError(
            f"{path}: 'software' must be a table of [software.<NAME>] sections"
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
        raise ConfigurationError(f"{where} must be a table")
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
        raise ConfigurationError(f"{where}: env must be a table of strings")
    return SoftwareConfig(executable, dict(env))
