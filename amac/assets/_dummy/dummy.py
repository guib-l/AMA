"""Minimal software used to test the AMAC core without a real program."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from amac.engine.drivers import Driver
from amac.engine.registry import register_software
from amac.engine.software import FileIOSoftware
from amac.parameter.composer import Composer

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.engine.software import Software
    from amac.parameter.parameters import CalculationSpec, ExecutionSpec
    from amac.parameter.schema import Schema

INPUT_FILE = "input.json"
OUTPUT_FILE = "output.json"

# Fake program: reads the input tree, writes a fake output, prints a status line.
_PROGRAM = """\
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    tree = json.load(stream)
result = {"energy": -1.0, "forces": [], "keywords": tree["keywords"]}
with open(sys.argv[2], "w", encoding="utf-8") as stream:
    json.dump(result, stream, sort_keys=True)
print("dummy: done")
"""


class DummyComposer(Composer):
    """Writes the intermediate tree as deterministic JSON."""

    def compose(
        self,
        spec: CalculationSpec,
        schema: Schema,
        atoms: Any,
        exec_spec: ExecutionSpec,
    ) -> dict[str, str]:
        """Return ``{INPUT.FILENAME: JSON of the tree}``; ``atoms`` is not used."""
        tree = self.build_tree(spec, schema, exec_spec)
        content = json.dumps(tree.to_dict(), indent=4, sort_keys=True)
        return {schema.input["FILENAME"]: f"{content}\n"}


class DummyLibraryDriver(Driver):
    """Driver using the fake library ``amac_dummy_lib``, which only the tests create.

    The library provides ``write_input(tree, directory)``, returning the written
    path, ``compute(directory, cpu=1)``, writing ``output.json``, and
    ``read_output(directory)``, returning a native object with ``energy``,
    ``forces`` and ``keywords`` attributes. As for every driver, the library is
    imported inside the phases only.
    """

    NAME = "dummy-lib"
    REQUIRES = ("amac_dummy_lib",)
    DISTRIBUTION = "amac-dummy-lib"
    PHASES = frozenset({"prepare", "run", "collect"})
    SUPPORTED_SETTINGS = frozenset({"cpu"})

    def prepare(self, software: Software, ctx: RunContext) -> None:
        """Write ``ctx.metadata["input_tree"]`` with the library."""
        import amac_dummy_lib

        tree = ctx.metadata["input_tree"].to_dict()
        path = Path(amac_dummy_lib.write_input(tree, ctx.directory))
        ctx.input_files[path.name] = path

    def run(self, software: Software, ctx: RunContext) -> None:
        """Run the fake calculation in ``ctx.directory`` with the library."""
        import amac_dummy_lib

        settings = self.execution_settings(software, ctx.exec_spec)
        amac_dummy_lib.compute(ctx.directory, cpu=settings["cpu"])

    def collect(self, software: Software, ctx: RunContext) -> None:
        """Record ``output.json`` in ``ctx.files`` and its native reading in
        ``ctx.objects["dummy_lib"]``."""
        import amac_dummy_lib

        path = ctx.directory / OUTPUT_FILE
        if path.is_file():
            ctx.files[OUTPUT_FILE] = path
            ctx.objects["dummy_lib"] = amac_dummy_lib.read_output(ctx.directory)


@register_software
class DummySoftware(FileIOSoftware):
    """Test software; handlers are added later."""

    NAME = "DUMMY"
    ALIASES = ()
    DOC = Path(__file__).with_name("doc.json")
    composer_cls = DummyComposer
    DRIVERS = (DummyLibraryDriver,)
    REQUIRES_EXECUTABLE = False  # Falls back to the current Python interpreter.

    def command(self, ctx: RunContext) -> list[str]:
        """Return the command of the fake program.

        The program reads ``input.json`` and writes ``output.json`` with a fake
        energy. It runs with :meth:`resolve_executable`, or the current Python
        interpreter when no executable is found.
        """
        executable = self.resolve_executable(ctx.exec_spec) or sys.executable
        return [executable, "-c", _PROGRAM, INPUT_FILE, OUTPUT_FILE]
