import json
import ase
import numpy as np

from pathlib import Path
from datetime import date
import uuid

class AseEncoder(json.JSONEncoder):
    """Encode NumPy scalars/arrays, sets and :class:`ase.Atoms` as JSON."""

    def default(self, obj):
        
        if isinstance(obj, date):
            return str(obj)
        
        if isinstance(obj, Path):
            return str(obj)
        
        if isinstance(obj, uuid.UUID):
            return str(obj)

        if isinstance(obj, np.ndarray):
            return obj.tolist()

        if isinstance(obj, np.integer):
            return int(obj)

        if isinstance(obj, np.floating):
            return float(obj)

        if isinstance(obj, np.bool_):
            return bool(obj)

        if isinstance(obj, (set, frozenset)):
            return sorted(obj, key=str)

        if isinstance(obj, ase.Atoms):
            return obj.__repr__()

        return super().default(obj)


    