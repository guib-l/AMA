"""Result handlers: registration, selection and execution.

A handler is a callable ``f(ctx: RunContext) -> Any``; the key of its result is the
handler name. Handlers of a software are declared with :func:`handler`, which
resolves the software through the registry at import time: the module defining the
software must therefore be imported before the module of its handlers. A handler
declared with ``software=None`` only carries metadata (e.g. ``requires_files``) and
is accepted by every software.
"""

from __future__ import annotations

import fnmatch
import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from amac.engine.registry import get_software
from amac.exceptions import HandlerError
from amac.parameter.parameters import HANDLER_ERRORS
from amac.parameter.schema import load as load_schema

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.engine.software import Software
    from amac.parameter.parameters import CalculationSpec
    from amac.parameter.schema import Schema

HANDLER_ATTRIBUTE = "__amac_handler__"

type HandlerFunction = Callable[[RunContext], Any]


@dataclass(frozen=True)
class HandlerSpec:
    """Metadata of a handler.

    Attributes:
        name: Key of the result.
        function: Callable receiving the run context.
        software: Software the handler belongs to, ``None`` for a handler accepted
            by every software.
        requires_files: Glob patterns, each matching at least one key of
            ``ctx.files``.
        modules: Compatible modules (canonical names or aliases), ``None`` for all.
        drivers: Compatible driver names, ``None`` for all.
    """

    name: str
    function: HandlerFunction
    software: type[Software] | None = None
    requires_files: tuple[str, ...] = ()
    modules: tuple[str, ...] | None = None
    drivers: tuple[str, ...] | None = None


def handler(
    software: str | None = None,
    name: str | None = None,
    requires_files: Iterable[str] = (),
    modules: Iterable[str] | None = None,
    drivers: Iterable[str] | None = None,
) -> Callable[[HandlerFunction], HandlerFunction]:
    """Declare a handler, of a software or of any software.

    With ``software``, the software is resolved when the decorator is created and the
    function is registered in ``software_cls.HANDLERS``. With ``software=None``, the
    handler is not registered anywhere and is accepted by every software; its
    metadata still apply. In both cases the function gets its :class:`HandlerSpec`
    in the ``__amac_handler__`` attribute and is returned unchanged.

    Args:
        software: Name or alias of a registered software, ``None`` for any software.
        name: Key of the result, the function name by default.
        requires_files: Glob patterns of ``ctx.files`` keys needed by the handler.
        modules: Compatible modules, ``None`` for all.
        drivers: Compatible drivers, ``None`` for all, e.g. ``("opi",)`` for a
            handler reading a native object of a library in ``ctx.objects``.

    Returns:
        The decorator.

    Raises:
        SoftwareNotFoundError: If ``software`` is not registered.
        TypeError: If a name list is a str or contains something else than
            non-empty str.
        ValueError: If the handler has no usable name, or if its name is already
            registered for the software.
    """
    software_cls = None if software is None else get_software(software)
    required = _names(requires_files, "requires_files")
    module_names = None if modules is None else _names(modules, "modules")
    driver_names = None if drivers is None else _names(drivers, "drivers")

    def register(function: HandlerFunction) -> HandlerFunction:
        key = _function_name(function) if name is None else name
        if software_cls is not None and key in software_cls.HANDLERS:
            raise ValueError(
                f"Handler {key!r} is already registered for {software_cls.NAME}"
            )
        meta = HandlerSpec(
            key, function, software_cls, required, module_names, driver_names
        )
        setattr(function, HANDLER_ATTRIBUTE, meta)
        if software_cls is not None:
            software_cls.HANDLERS[key] = function
        return function

    return register


def resolve_handlers(
    software_cls: type[Software],
    spec: CalculationSpec,
    handlers: Iterable[HandlerFunction | tuple[str, HandlerFunction]],
    driver: str = "amac",
    schema: Schema | None = None,
    fallback: str | None = None,
    skip_incompatible: bool = False,
) -> list[HandlerSpec]:
    """Check handlers against a calculation and return their metadata.

    A handler decorated for a software is accepted by this software and its
    subclasses. A custom handler (undecorated callable, or declared with
    ``software=None``) is accepted by every software; its name is its ``__name__``,
    or is given with a ``(name, callable)`` tuple. A tuple renames a decorated
    handler without changing its constraints.

    Args:
        software_cls: Software of the calculation.
        spec: Calculation; its module is compared with the handler ``modules``
            after alias resolution.
        handlers: Decorated handlers, custom callables or ``(name, callable)``
            tuples.
        driver: Name of the selected driver.
        schema: Schema of ``software_cls``, loaded from its ``DOC`` when needed.
            Without schema, module names are compared ignoring case.
        fallback: Why ``"auto"`` fell back to ``driver``, quoted in the error
            of an incompatible handler.
        skip_incompatible: Discard, with one warning listing them and their
            reasons, the handlers incompatible with the module or the driver,
            instead of raising.

    Returns:
        The metadata of the kept handlers, in the given order.

    Warns:
        UserWarning: If ``skip_incompatible`` discards handlers.

    Raises:
        TypeError: If an item is neither a callable nor a ``(name, callable)``
            tuple.
        ValueError: If a handler has no usable name, belongs to another software,
            or if two results have the same name; also if a handler is
            incompatible with the module or the driver, unless
            ``skip_incompatible``.
        ValidationError: If a module name is unknown to the schema.
    """
    resolved: list[HandlerSpec] = []
    skipped: list[str] = []
    for item in handlers:
        meta = _as_handler_spec(item)
        if any(other.name == meta.name for other in resolved):
            raise ValueError(f"Duplicate result name {meta.name!r}")
        if meta.software is not None and not issubclass(software_cls, meta.software):
            raise ValueError(
                f"Handler {meta.name!r} belongs to {meta.software.NAME}, "
                f"not to {software_cls.NAME}"
            )
        reason = None
        if meta.modules is not None:
            if schema is None and software_cls.DOC is not None:
                schema = load_schema(software_cls.DOC)
            compatible = {_module_key(module, schema) for module in meta.modules}
            if _module_key(spec.module, schema) not in compatible:
                reason = (
                    f"Handler {meta.name!r} is not compatible with module "
                    f"{spec.module!r}; compatible: {', '.join(meta.modules)}"
                )
        if (
            reason is None
            and meta.drivers is not None
            and driver.casefold() not in {name.casefold() for name in meta.drivers}
        ):
            fell_back = f" ('auto' fell back to it: {fallback})" if fallback else ""
            reason = (
                f"Handler {meta.name!r} is not compatible with driver {driver!r}"
                f"{fell_back}; compatible: {', '.join(meta.drivers)}"
            )
        if reason is None:
            resolved.append(meta)
        elif skip_incompatible:
            skipped.append(reason)
        else:
            raise ValueError(reason)
    if skipped:
        details = "\n".join(f"  - {reason}" for reason in skipped)
        warnings.warn(f"Incompatible handlers skipped:\n{details}", stacklevel=3)
    return resolved


def run_handlers(
    ctx: RunContext,
    handlers: Iterable[HandlerSpec],
    on_error: str | None = None,
) -> tuple[dict[str, Any], list[HandlerError]]:
    """Run handlers on a context filled by ``collect``.

    A handler fails when it raises, or when one of its ``requires_files`` matches no
    key of ``ctx.files``; it is then not called. A failed handler has no entry in
    the properties and produces a :class:`HandlerError` chained to the original
    exception. The success of the calculation is not affected.

    Args:
        ctx: Run context.
        handlers: Output of :func:`resolve_handlers`.
        on_error: ``"collect"`` records failures and runs the other handlers,
            ``"raise"`` raises the first failure; ``None`` uses
            ``ctx.exec_spec.handler_errors``.

    Returns:
        The properties keyed by handler name, and the recorded errors.

    Warns:
        UserWarning: If ``handlers`` is empty.

    Raises:
        ValueError: If ``on_error`` is unknown.
        HandlerError: The first failure, with ``"raise"``.
    """
    mode = ctx.exec_spec.handler_errors if on_error is None else on_error
    if mode not in HANDLER_ERRORS:
        raise ValueError(
            f"on_error must be one of {', '.join(HANDLER_ERRORS)}, got {mode!r}"
        )
    handlers = list(handlers)
    if not handlers:
        warnings.warn("No handler declared: no property is computed", stacklevel=2)
        return {}, []
    properties: dict[str, Any] = {}
    errors: list[HandlerError] = []
    for meta in handlers:
        try:
            properties[meta.name] = _call(meta, ctx)
        except HandlerError as error:
            if mode == "raise":
                raise
            errors.append(error)
    return properties, errors


def _call(meta: HandlerSpec, ctx: RunContext) -> Any:
    missing = tuple(
        pattern
        for pattern in meta.requires_files
        if not any(fnmatch.fnmatchcase(key, pattern) for key in ctx.files)
    )
    if missing:
        raise HandlerError(
            f"Handler {meta.name!r} not run, missing files: {', '.join(missing)}",
            meta.name,
            missing,
        )
    try:
        return meta.function(ctx)
    # Handlers are arbitrary code: any failure is reported as a HandlerError.
    except Exception as err:
        raise HandlerError(f"Handler {meta.name!r} failed: {err!r}", meta.name) from err


def _as_handler_spec(item: Any) -> HandlerSpec:
    if isinstance(item, tuple):
        if len(item) != 2 or not isinstance(item[0], str) or not callable(item[1]):
            raise TypeError(f"A handler tuple must be (name, callable), got {item!r}")
        name, function = item
        if not name:
            raise ValueError("A handler name must not be empty")
        decorated = getattr(function, HANDLER_ATTRIBUTE, None)
        if decorated is None:
            return HandlerSpec(name, function)
        return replace(decorated, name=name)
    if not callable(item):
        raise TypeError(f"A handler must be callable, got {item!r}")
    decorated = getattr(item, HANDLER_ATTRIBUTE, None)
    return decorated or HandlerSpec(_function_name(item), item)


def _function_name(function: Any) -> str:
    name = getattr(function, "__name__", None)
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError(
            f"{function!r} has no usable name; give one explicitly "
            "(name= or a (name, handler) tuple)"
        )
    return name


def _names(values: Iterable[str], what: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{what} must be an iterable of str, not a str")
    names = tuple(values)
    if not all(isinstance(value, str) and value for value in names):
        raise TypeError(f"{what} must contain non-empty str, got {names!r}")
    return names


def _module_key(name: str, schema: Schema | None) -> str:
    if schema is None:
        return name.upper()
    return schema.resolve_alias("MODULES", name)
