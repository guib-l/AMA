from __future__ import annotations


from collections.abc import Callable


from software import Software



type HandlerFunction = Callable

class HandlerSpec:

    name: str
    function: HandlerFunction
    software: type[Software] | None = None
    requires_files: tuple[str, ...] = ()
    modules: tuple[str, ...] | None = None
    drivers: tuple[str, ...] | None = None














