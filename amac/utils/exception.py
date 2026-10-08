

class AmacError(Exception):
    """Base class for every AMAC-specific error."""


class ConfigError(AmacError):
    """Raised when user-supplied parameters are missing or invalid."""


class ExecuteFailed(AmacError):
    """Raised when the software binary returns a non-zero exit code."""


class InputError(AmacError):
    """Raised when the input file cannot be assembled."""


class OutputParseError(AmacError):
    """Raised when output cannot be parsed."""



    






