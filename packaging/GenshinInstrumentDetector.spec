# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：单文件、无控制台窗口的 原神乐器演奏检测器.exe
# 用法（在仓库根目录）：python -m PyInstaller --noconfirm --clean packaging/GenshinInstrumentDetector.spec
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct)

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from app_version import APP_NAME, APP_VERSION, APP_URL  # noqa: E402

_v = tuple(int(p) for p in (APP_VERSION.split(".") + ["0", "0", "0"])[:4])
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_v, prodvers=_v, mask=0x3F, flags=0x0, OS=0x40004,
                      fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("080404B0", [
            StringStruct("CompanyName", "hutao48"),
            StringStruct("FileDescription", APP_NAME),
            StringStruct("FileVersion", APP_VERSION),
            StringStruct("InternalName", "GenshinInstrumentDetector"),
            StringStruct("LegalCopyright", APP_URL),
            StringStruct("OriginalFilename", APP_NAME + ".exe"),
            StringStruct("ProductName", APP_NAME),
            StringStruct("ProductVersion", APP_VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
    ],
)

datas = collect_data_files("pyqtgraph")
datas += [(os.path.join(ROOT, "packaging", "app.ico"), ".")]
hiddenimports = collect_submodules("soundcard")

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 检测引擎只用 numpy；排除常被可选导入拖进来的大包，减小体积
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "PIL", "pytest"],
    noarchive=False,
    optimize=0,
)
# QtCore 使用 Windows 系统 ICU 的无版本符号。PATH 中 Poppler 等工具的同名
# icuuc.dll 使用带版本后缀的另一套符号，误收进包会使 QtCore 报缺少入口点。
# 与其它 Windows 系统 DLL 一样，在目标机器上由系统加载，不打包外部同名库。
system_icu = {"icu.dll", "icuuc.dll", "icuin.dll", "icudt.dll"}
a.binaries = [entry for entry in a.binaries if entry[0].lower() not in system_icu]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "packaging", "app.ico"),
    version=version_info,
)
