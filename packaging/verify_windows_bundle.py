"""验证成品单文件 EXE 确实包含界面模块、Qt 扩展和 Windows 平台插件。"""
import argparse
import json

from PyInstaller.archive.readers import CArchiveReader


def verify(path):
    archive = CArchiveReader(path)
    modules = archive.open_embedded_archive("PYZ.pyz").toc
    required_modules = {"PySide6", "shiboken6", "pyqtgraph", "soundcard",
                        "ui_main", "detection", "screening", "app_version"}
    binaries = {name.replace("\\", "/").lower() for name in archive.toc}
    required_files = {"pyside6/qtcore.pyd", "pyside6/qtgui.pyd", "pyside6/qtwidgets.pyd",
                      "pyside6/plugins/platforms/qwindows.dll"}
    missing = sorted(required_modules - set(modules)) + sorted(required_files - binaries)
    if missing:
        raise RuntimeError("成品 EXE 缺少界面依赖：" + ", ".join(missing))
    print(json.dumps({"ok": True, "exe": path,
                      "verified_modules": sorted(required_modules),
                      "verified_files": sorted(required_files)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe")
    verify(parser.parse_args().exe)
