"""Software supported by AMAC.

Explicit imports register the known software (no filesystem scan). Each software
lives in a lowercase package named after it (``amac.assets.orca``,
``amac.assets.dftbplus``, ...), which exposes its handlers; the software module is
imported before its handlers module.
"""

import amac.assets._dummy.dummy
import amac.assets._dummy.inprocess
import amac.assets.demonnano.demonnano
import amac.assets.dftbplus.dftbplus
import amac.assets.gaussian.gaussian
import amac.assets.orca.orca
