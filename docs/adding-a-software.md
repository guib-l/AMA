# Adding a software

[← README](../README.md)

1. **Create its package** `amac/assets/<software>/`, named after the software in
   lowercase (`dftbplus`, `demonnano`), and **describe it** in
   its `doc.json`, following [`DOC_SCHEMA.md`](DOC_SCHEMA.md): syntax
   family, modules, methods, parameters, output files. A future PySCF package keeps
   the name `amac.assets.pyscf`: imports are absolute, so `import pyscf` inside it
   still designates the library, which is only imported by the software module.

2. **Write the input.** The composer is `composer_cls` when set, otherwise the one of
   the `SYNTAX` of the `doc.json`. The concrete `KEYWORD_BLOCK`, `TREE`, `NAMELIST`
   and `FLAT` composers are not implemented yet, so a new software currently brings
   its own composer, rendering the intermediate tree:

   ```python
   from amac.parameter.composer import Composer


   class MySoftComposer(Composer):
       def compose(self, spec, schema, atoms, exec_spec, tree=None):
           # tree is the one AMAC already built for this image; build_tree() only
           # translates the spec when it is None (composer called outside a run).
           tree = self.build_tree(spec, schema, exec_spec, tree)
           return {schema.input["FILENAME"]: render(tree, atoms)}
   ```

   The composer works on that tree in place: what it completes, such as the
   options the software needs for its results to be read back, ends up in
   `ctx.metadata["input_tree"]` and therefore in the provenance.

3. **Subclass `FileIOSoftware`** and register it:

   ```python
   from pathlib import Path

   from amac.engine.registry import register_software
   from amac.engine.software import FileIOSoftware


   @register_software
   class MySoft(FileIOSoftware):
       NAME = "MYSOFT"  # canonical name, looked up case-insensitively
       ALIASES = ("my-soft",)
       DOC = Path(__file__).with_name("doc.json")
       composer_cls = MySoftComposer  # None: dispatch on the doc.json SYNTAX

       def command(self, ctx):
           executable = self.require_executable(ctx.exec_spec).path
           return [executable, "input.inp"]

       def stdout_file(self, ctx):
           return Path("output.log")  # for programs writing on stdout
   ```

   A software driven through a Python API subclasses `InProcessSoftware` instead:
   `build(ctx)` creates the native objects in `ctx.objects`, `compute(ctx)` runs
   them, `collect(ctx)` stores what the handlers need. See
   `amac/assets/demonnano/demonnano.py`.

4. **Declare its handlers** in a module imported *after* the software, since
   `@handler` resolves the software through the registry at import time, and expose
   them in the `__init__.py` of the package (`from amac.assets import mysoft`, then
   `mysoft.energy`):

   ```python
   from amac.assets.mysoft.mysoft import MySoft  # registers MYSOFT first
   from amac.engine.handlers import handler


   @handler(software="MYSOFT", requires_files=("output.log",))
   def energy(ctx):
       return parse_energy(ctx.files["output.log"].read_text())
   ```

   Produced files are listed in `ctx.files` from the glob patterns of
   `OUTPUT.FILES` in the `doc.json`. Use the common result names, so that the same
   property has the same key whatever the software:

   | Handler | Result |
   |---|---|
   | `energy` | Total energy |
   | `forces` | Forces on the atoms, shape `(n, 3)` |
   | `dipole` | Dipole moment, shape `(3,)` |
   | `charges` | Atomic charges, shape `(n,)` |
   | `final_geometry` | Last geometry of an optimisation, as `ase.Atoms` |
   | `frequencies` | Vibrational frequencies |
   | `hessian` | Hessian matrix |

   Handlers return ASE units (eV, Å): the normalized dataclass of a software keeps
   the units of the program, and the handlers convert them. DFTB+ and deMonNano
   follow this rule today; the other packages will as they are written.

5. **Import the software module** explicitly in `amac/assets/__init__.py` (there is
   no filesystem scan).

Two software are registered today. DFTB+ (`amac/assets/dftbplus/`) is the complete
example of a file-based software (`composer.py`, `parser.py`, `handlers.py`,
`drivers.py`), and deMonNano (`amac/assets/demonnano/`) that of an in-process
software (`demonnano.py`, `parser.py`, `handlers.py`), driven by the `deMonPy`
library.
