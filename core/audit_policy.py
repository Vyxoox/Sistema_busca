from __future__ import annotations
from functools import wraps
from typing import Any, Callable

def audit_event(acao : str | None = None, *, categoria: str = "operacao", recurso: str | None = None):
    def deco(fn: Callable[..., Any]):
        acao_final = (acao or f"ROTA_{fn.__module__.split('.')[-1]}_{fn.__name__}").upper()

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            return fn(*args, **kwargs)

        wrapper.__audit_required__ = True
        wrapper.__audit_meta__ = {"acao": acao_final, "categoria": categoria, "recurso": recurso}
        return wrapper
    return deco
