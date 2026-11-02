## 原神乐器演奏检测器 Windows 1.0.4 / Android 1.0.3

### 下载

| 文件 | 说明 |
|---|---|
| `GenshinInstrumentDetector-1.0.4-win64-setup.exe` | **Windows 安装程序**：安装到当前用户目录（无需管理员），创建开始菜单/桌面快捷方式，可在“设置 → 应用”中卸载；覆盖安装即可从旧版升级 |
| `GenshinInstrumentDetector-1.0.4-win64-portable.exe` | **Windows 免安装版**：单文件，双击即可运行（首次启动需 2–5 秒解压） |
| `GenshinInstrumentDetector-1.0.3-android.apk` | **Android 安装包**：Android 7.0 及以上；本版仅做版本号与安全加固，桌面端新增的设置功能不在本 APK 中 |
| `SHA256SUMS.txt` | 以上文件的 SHA-256 校验和 |

> exe 未做代码签名，Windows SmartScreen 可能提示“未知发布者”，点击“更多信息 → 仍要运行”即可。
> APK 未配置固定签名，每个版本签名不同，升级前请先卸载旧版。

### 新增：设置窗口

顶栏齿轮按钮打开设置，语言、主题、更新检查集中在一处：

- **界面语言（5 种）**：简体中文、繁體中文、正體中文（臺灣）、English、日本語。切换后自动重启应用生效；检测结果、表格、导出 CSV、离线分析报告都会使用所选语言。
- **背景主题**：跟随系统 / 深色 / 浅色，立即生效；跟随系统会随 Windows 的深色模式自动切换。琴键、指标卡、BPM 图、表格都有对应的浅色配色。
- **更新检查**：查询本仓库的 GitHub Releases，显示当前版本、最新版本和下载入口；可在设置中开启/关闭启动时自动检查。发现新版本时顶栏会出现提示按钮。
- **关于**：版本号与项目主页入口。

### 安全加固

- 更新检查只访问固定的 `https://api.github.com/repos/hutao48/genshinimpact-py.found/releases/latest`，不接受用户输入的地址；限制 12 秒超时和 512 KB 响应体；只打开经过校验的 GitHub Release 页面，**不自动下载、不自动执行任何文件**。
- 设置保存在 `%LOCALAPPDATA%\GenshinInstrumentDetector\settings.ini`，继续不写注册表；语言/主题值做白名单校验，配置文件损坏时回退默认值。
- Android 关闭 `allowBackup`（避免通过 adb backup 导出应用数据）并显式关闭明文网络流量。

### 清理

- 移除仓库内的全部测试/评测源码、测试录音与合成数据（`test_*.py`、`benchmark_timing.py`、`eval_*.py`、`*.wav`、`score_seq.json`），仓库只保留运行所需代码与打包资源。
- Windows 打包脚本不再执行已移除的回归测试；构建由 GitHub Actions 在推送 `v*` tag 时完成。

### 说明

- Windows 端版本为 1.0.4；Android 端为 1.0.3（仅版本号与安全加固）。两端检测算法保持一致。
- 如果从 1.0.3 或更早版本升级，设置文件会在首次保存设置时创建；旧版没有设置文件，不影响启动。
