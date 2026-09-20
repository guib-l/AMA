"""Software supported by AMAC.

Explicit imports register the known software (no filesystem scan). Each software
lives in a lowercase package named after it (``amac.assets.dftbplus``,
``amac.assets.demonnano``, ...), which exposes its handlers; the software module is
imported before its handlers module.
"""

# Registration imports: importing the module registers the software.
import amac.assets.demonnano.demonnano  # noqa: F401
import amac.assets.dftbplus.dftbplus  # noqa: F401
