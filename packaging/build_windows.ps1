<#
  一键打包 Windows 版：单文件 exe + 安装程序

  用法（任意目录执行均可）：
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 [-Python <python.exe>] [-SkipTests] [-Iscc <ISCC.exe>]

  依赖：
    pip install -r packaging\requirements-build.txt
    Inno Setup 6（ISCC.exe；默认在 PATH、%LOCALAPPDATA%\Programs、Program Files 中查找）

  产物（dist\）：
    原神乐器演奏检测器.exe                              单文件程序（免安装，双击运行）
    GenshinInstrumentDetector-<版本>-win64-portable.exe  同上，发布用的英文文件名
    GenshinInstrumentDetector-<版本>-win64-setup.exe     安装程序（开始菜单/桌面快捷方式、可卸载）
    SHA256SUMS-windows.txt                               校验和
#>
param(
    [string]$Python = "python",
    [switch]$SkipTests,
    [string]$Iscc = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    $env:PYTHONIOENCODING = "utf-8"
    $Version = (& $Python -c "import app_version; print(app_version.APP_VERSION)").Trim()
    if (-not $Version) { throw "无法读取 app_version.APP_VERSION" }
    Write-Host "== 版本 $Version"

    if (-not $SkipTests) {
        Write-Host "== 回归测试 test_detection.py"
        & $Python test_detection.py
        if ($LASTEXITCODE -ne 0) { throw "test_detection.py 未通过" }
    }

    Write-Host "== PyInstaller"
    & $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller packaging\GenshinInstrumentDetector.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }
    $exe = Join-Path $Root "dist\原神乐器演奏检测器.exe"
    if (-not (Test-Path $exe)) { throw "未找到 $exe" }
    $portable = Join-Path $Root "dist\GenshinInstrumentDetector-$Version-win64-portable.exe"
    Copy-Item $exe $portable -Force

    Write-Host "== Inno Setup"
    if (-not $Iscc) {
        $cmd = Get-Command iscc -ErrorAction SilentlyContinue
        $cands = @($env:ISCC, $(if ($cmd) { $cmd.Source }),
                   "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
                   "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                   "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { $_ -and (Test-Path $_) }
        if (-not $cands) { throw "未找到 Inno Setup 6 的 ISCC.exe（可用 -Iscc 指定）" }
        $Iscc = @($cands)[0]
    }
    & $Iscc "/DMyAppVersion=$Version" "packaging\installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "ISCC 失败" }
    $setup = Join-Path $Root "dist\GenshinInstrumentDetector-$Version-win64-setup.exe"
    if (-not (Test-Path $setup)) { throw "未找到 $setup" }

    $sums = foreach ($f in @($portable, $setup)) {
        "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $f).Hash.ToLower(), (Split-Path $f -Leaf)
    }
    $sums | Set-Content -Encoding ascii (Join-Path $Root "dist\SHA256SUMS-windows.txt")
    Write-Host "== 完成"
    Get-Item $exe, $portable, $setup | Format-Table Name, Length -AutoSize
}
finally {
    Pop-Location
}
