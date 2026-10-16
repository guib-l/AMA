
import os
import json


def configure(config = None):
    """Set global default values calculation.

    Args:
        config: configuration of amac
    """
    global CONFIGURE

    if config is not None:
        CONFIGURE = config



def configure_from_file(path="amac-config.json"):
    """Load global configuration from a JSON file.

    Args:
        path: Path to the JSON configuration file.
    """
    if not os.path.exists(path):
        raise FileExistsError(f"File config.json didn't exists at {os.path.abspath(path)}")
    with open(path) as f:
        config = json.load(f)

    configure(config)










