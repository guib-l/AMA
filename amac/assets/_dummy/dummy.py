"""Minimal software used to test the AMAC core without a real program.

It has no ``doc.json``: its calculations run with ``validate="off"``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from amac.engine.context import OUTPUT_KEY
from amac.engine.drivers import Driver
from amac.engine.registry import register_software
from amac.engine.software import FileIOSoftware

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.engine.software import Software

INPUT_FILE = "input.json"
OUTPUT_FILE = "output.json"

# Fake program: reads the input spec, writes a fake output, prints a status line.
_PROGRAM = """\
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    spec = json.load(stream)
result = {"energy": -1.0, "forces": [], "method": spec["method"]}
with open(sys.argv[2], "w", encoding="utf-8") as stream:
    json.dump(result, stream, sort_keys=True)
print("dummy: done")
"""


@dataclass(frozen=True)
class DummyOutput:
    """Normalized output of the dummy software, values as written by the program.

    Attributes:
        energy: Fake energy.
        forces: Fake forces.
        method: Method of the spec.
    """

    energy: float
    forces: list[list[float]]
    method: str


def parse_directory(directory: Path) -> DummyOutput:
    """Read ``output.json`` of ``directory``.

    Raises:
        FileNotFoundError: If ``output.json`` does not exist.
        KeyError: If a value is missing from ``output.json``.
    """
    with (Path(directory) / OUTPUT_FILE).open(encoding="utf-8") as stream:
        data = json.load(stream)
    return DummyOutput(data["energy"], data["forces"], data["method"])


class DummyLibraryDriver(Driver):
    """Driver using the fake library ``amac_dummy_lib``, which only the tests create.

    The library provides ``write_input(spec, directory)``, returning the written
    path, ``compute(directory, cpu=1)``, writing ``output.json``, and
    ``read_output(directory)``, returning a native object with ``energy``,
    ``forces`` and ``method`` attributes. As for every driver, the library is
    imported inside the phases only.
    """

    NAME = "dummy-lib"
    REQUIRES = ("amac_dummy_lib",)
    DISTRIBUTION = "amac-dummy-lib"
    PHASES = frozenset({"prepare", "run", "collect"})
    SUPPORTED_SETTINGS = frozenset({"cpu"})

    def prepare(self, software: Software, ctx: RunContext) -> None:
        """Write ``ctx.spec`` with the library."""
        import amac_dummy_lib

        path = Path(amac_dummy_lib.write_input(ctx.spec.to_dict(), ctx.directory))
        ctx.input_files[path.name] = path

    def run(self, software: Software, ctx: RunContext) -> None:
        """Run the fake calculation in ``ctx.directory`` with the library."""
        import amac_dummy_lib

        settings = self.execution_settings(software, ctx.exec_spec)
        amac_dummy_lib.compute(ctx.directory, cpu=settings["cpu"])

    def collect(self, software: Software, ctx: RunContext) -> None:
        """Record ``output.json`` in ``ctx.files``, its native reading in
        ``ctx.objects["dummy_lib"]`` and its :class:`DummyOutput` in
        ``ctx.objects[OUTPUT_KEY]``."""
        import amac_dummy_lib

        path = ctx.directory / OUTPUT_FILE
        if path.is_file():
            ctx.files[OUTPUT_FILE] = path
            native = amac_dummy_lib.read_output(ctx.directory)
            ctx.objects["dummy_lib"] = native
            ctx.objects[OUTPUT_KEY] = DummyOutput(
                native.energy, native.forces, native.method
            )


@register_software
class DummySoftware(FileIOSoftware):
    """Test software without ``doc.json``; handlers are added later."""

    NAME = "DUMMY"
    ALIASES = ()
    DRIVERS = (DummyLibraryDriver,)
    REQUIRES_EXECUTABLE = False  # Falls back to the current Python interpreter.

    def prepare(self, ctx: RunContext) -> None:
        """Write ``ctx.spec`` as deterministic JSON in ``input.json``."""
        path = ctx.directory / INPUT_FILE
        content = json.dumps(ctx.spec.to_dict(), indent=4, sort_keys=True)
        with path.open("w", encoding="utf-8") as stream:
            stream.write(f"{content}\n")
        ctx.input_files[INPUT_FILE] = path

    def command(self, ctx: RunContext) -> list[str]:
        """Return the command of the fake program.

        The program reads ``input.json`` and writes ``output.json`` with a fake
        energy and the method of the spec. It runs with :meth:`resolve_executable`,
        or the current Python interpreter when no executable is found.
        """
        executable = self.resolve_executable(ctx.exec_spec) or sys.executable
        return [executable, "-c", _PROGRAM, INPUT_FILE, OUTPUT_FILE]

    def collect(self, ctx: RunContext) -> None:
        """Record ``output.json`` in ``ctx.files`` when the program wrote it."""
        path = ctx.directory / OUTPUT_FILE
        if path.is_file():
            ctx.files[OUTPUT_FILE] = path
