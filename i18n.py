# -*- coding: utf-8 -*-
"""轻量多语言层。

设计：
- 以中文原文作为 msgid（`T("开始监听")`），翻译表见 locales.py；
- 启动时确定语言（环境变量 GID_LANG > 设置文件 > 系统语言）；
- 语言切换通过重启应用生效，避免运行中的检测结果与界面语言混杂；
- 找不到翻译时回退到英文，再回退到中文，并记录到 MISSING 便于自检。
"""
from __future__ import annotations

import os

import settings
from locales import EN, JA, ZH_HANT, ZH_TW_OVERRIDES

LANGUAGES = [
    ("zh-CN", "简体中文"),
    ("zh-Hant", "繁體中文"),
    ("zh-TW", "正體中文（臺灣）"),
    ("en", "English"),
    ("ja", "日本語"),
]
CODES = [c for c, _ in LANGUAGES]
NATIVE_NAMES = dict(LANGUAGES)

_current = "zh-CN"
_initialized = False
MISSING: set[str] = set()


def system_language() -> str:
    """按系统语言给出默认值：中文（台/港/澳）→ 正體中文（臺灣），其余中文 → 简体，日文 → 日本語，其它 → English。"""
    name = ""
    try:
        from PySide6.QtCore import QLocale
        name = QLocale.system().name()          # zh_CN / zh_TW / ja_JP / en_US
    except Exception:
        name = os.environ.get("LANG", "")
    low = name.lower().replace("-", "_")
    if low.startswith("zh"):
        if any(x in low for x in ("_tw", "_hk", "_mo", "_hant")):
            return "zh-TW"
        return "zh-CN"
    if low.startswith("ja"):
        return "ja"
    if low.startswith("en"):
        return "en"
    return "en"


def normalize(code: str | None) -> str:
    code = (code or "").strip()
    if code in CODES:
        return code
    aliases = {
        "zh": "zh-CN", "zh_cn": "zh-CN", "zh-hans": "zh-CN", "zh_hans": "zh-CN",
        "zh-hant": "zh-Hant", "zh_hant": "zh-Hant", "zh-hk": "zh-Hant", "zh_hk": "zh-Hant",
        "zh-tw": "zh-TW", "zh_tw": "zh-TW", "zh-mo": "zh-TW", "zh_mo": "zh-TW",
        "ja": "ja", "ja-jp": "ja", "ja_jp": "ja",
        "en": "en", "en-us": "en", "en_us": "en", "en-gb": "en",
    }
    return aliases.get(code.lower(), "")


def init(language: str | None = None) -> str:
    """初始化语言；language 为空时按 GID_LANG → 设置 → 系统 的顺序决定。"""
    global _current, _initialized
    configured = settings.load().get("language", "")
    choice = (language or os.environ.get("GID_LANG") or configured or system_language())
    if os.environ.get("GID_LANG"):
        choice = os.environ["GID_LANG"]
    code = normalize(choice) or system_language()
    _current = code
    _initialized = True
    return code


def current() -> str:
    if not _initialized:
        init()
    return _current


def native_name(code: str | None = None) -> str:
    return NATIVE_NAMES.get(code or current(), code or current())


def _catalog() -> dict[str, str]:
    code = current()
    if code == "zh-CN":
        return {}
    if code == "en":
        return EN
    if code == "ja":
        return JA
    if code == "zh-TW":
        return {**ZH_HANT, **ZH_TW_OVERRIDES}
    if code == "zh-Hant":
        return ZH_HANT
    return EN


def T(text: str, **kwargs) -> str:
    """翻译一条 msgid；支持 {name} 占位符。缺失时回退英文/中文并记入 MISSING。"""
    if current() == "zh-CN":
        out = text
    else:
        out = _catalog().get(text)
        if out is None:
            out = EN.get(text)
        if out is None:
            out = text
            if current() != "zh-CN" and os.environ.get("GID_I18N_CHECK") == "1":
                MISSING.add(text)
    if kwargs:
        try:
            return out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return out
    return out


def instrument_name(name: str) -> str:
    """乐器内部名（中文，参与检测逻辑）→ 显示名。"""
    return T(name)


def coverage() -> dict:
    """返回各语言相对英文/中文的条目数，便于自检。"""
    keys = set(EN)
    return {
        "en": len(EN),
        "ja": len(JA),
        "zh-Hant": len(ZH_HANT),
        "zh-TW": len({**ZH_HANT, **ZH_TW_OVERRIDES}),
        "missing_in_ja": sorted(k for k in keys if k not in JA),
        "missing_in_zh-Hant": sorted(k for k in keys if k not in ZH_HANT),
    }
