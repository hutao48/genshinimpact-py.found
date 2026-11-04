# -*- coding: utf-8 -*-
"""用户设置（不写注册表）：%LOCALAPPDATA%\\GenshinInstrumentDetector\\settings.ini"""
from __future__ import annotations

import configparser
import os
import tempfile

APP_DIR_NAME = "GenshinInstrumentDetector"

DEFAULTS = {
    "language": "",          # 空 = 首次启动时跟随系统
    "theme": "system",       # system / dark / light
    "check_updates": "0",    # 默认不联网；用户在设置中显式开启后启动时才检查
    "auto_update": "0",      # 发现新版本后是否自动下载并安装
    "float_window": "0",     # 默认不显示；可在设置或顶栏按钮开启
}

VALID_THEMES = {"system", "dark", "light"}


def config_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIR_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), "settings.ini")


def load() -> dict:
    """读取设置；文件缺失/损坏时回退到默认值，绝不因配置问题阻止启动。"""
    data = dict(DEFAULTS)
    path = config_path()
    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(path, encoding="utf-8")
        if cp.has_section("general"):
            for key in DEFAULTS:
                if cp.has_option("general", key):
                    data[key] = cp.get("general", key).strip()
    except (OSError, configparser.Error, ValueError):
        data = dict(DEFAULTS)
    if data.get("theme") not in VALID_THEMES:
        data["theme"] = "system"
    if data.get("check_updates") not in ("0", "1"):
        data["check_updates"] = "0"
    if data.get("auto_update") not in ("0", "1"):
        data["auto_update"] = "0"
    if data.get("float_window") not in ("0", "1"):
        data["float_window"] = "0"
    return data


def save(values: dict) -> bool:
    """原子写入设置；失败时返回 False（例如目录只读），不抛异常打断界面。"""
    data = dict(DEFAULTS)
    data.update({k: str(v) for k, v in values.items() if k in DEFAULTS})
    if data["theme"] not in VALID_THEMES:
        data["theme"] = "system"
    try:
        os.makedirs(config_dir(), exist_ok=True)
        cp = configparser.ConfigParser(interpolation=None)
        cp["general"] = data
        fd, tmp = tempfile.mkstemp(prefix="settings.", suffix=".tmp", dir=config_dir())
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                cp.write(f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, config_path())
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return True
    except OSError:
        return False
