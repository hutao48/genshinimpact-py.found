# -*- coding: utf-8 -*-
"""Translation catalogs. Keys are the Chinese source strings used with i18n.T()."""
try:
    from .en import EN
except ImportError:  # pragma: no cover - during initial packaging
    EN = {}

try:
    from .ja import JA
except ImportError:  # pragma: no cover
    JA = {}

try:
    from .zh_hant import ZH_HANT, ZH_TW_OVERRIDES
except ImportError:  # pragma: no cover
    ZH_HANT = {}
    ZH_TW_OVERRIDES = {}

__all__ = ["EN", "JA", "ZH_HANT", "ZH_TW_OVERRIDES"]
