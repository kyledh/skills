"""Provider registry. Add a provider: create a module here exposing `PROVIDER`
(an instance of mq.base.Provider) and list the module name in MODULES."""
from __future__ import annotations

import importlib
from typing import Dict, List

from ..base import Provider

MODULES = ["okx", "longbridge", "yf", "ibkr"]

_REGISTRY: Dict[str, Provider] = {}


def _load() -> Dict[str, Provider]:
    if not _REGISTRY:
        for mod in MODULES:
            m = importlib.import_module(f"{__name__}.{mod}")
            p: Provider = getattr(m, "PROVIDER")
            _REGISTRY[p.name] = p
    return _REGISTRY


def names() -> List[str]:
    return list(_load().keys())


def get(name: str) -> Provider:
    reg = _load()
    if name not in reg:
        raise KeyError(f"unknown provider '{name}'. Known: {', '.join(reg)}")
    return reg[name]


def all_providers() -> List[Provider]:
    return list(_load().values())
