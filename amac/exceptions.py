"""Exceptions raised by AMAC."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amac.engine.context import RunContext


class AMACError(Exception):
    """Base class of every AMAC error."""


class ValidationError(AMACError):
    """Raised when calculation parameters do not match the software schema."""


class SoftwareNotFoundError(AMACError):
    """Raised when a software name is not registered."""


class RunError(AMACError):
    """Raised when a calculation fails.

    Args:
        message: Description of the failure.
        ctx: Context of the failed run, if available.
    """

    def __init__(self, message: str, ctx: RunContext | None = None) -> None:
        super().__init__(message)
        self.ctx = ctx


class HandlerError(AMACError):
    """Raised when a result handler fails.

    Args:
        message: Description of the failure.
        handler: Name of the failed handler, if known.
        missing_files: ``requires_files`` patterns matched by no produced file.
    """

    def __init__(
        self,
        message: str,
        handler: str | None = None,
        missing_files: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.handler = handler
        self.missing_files = tuple(missing_files)


class DriverUnavailableError(AMACError):
    """Raised when a requested driver library is missing or unusable."""


class ConfigurationError(AMACError):
    """Raised when the machine configuration file is missing or invalid."""


class ExecutableNotFoundError(AMACError):
    """Raised when the executable of a software cannot be found or run."""
