## 原神乐器演奏检测器 1.1.1

**本次仅修复琴键栏 UI 异常，不包含检测算法或功能变化。**

### UI 修复

- 键面按游戏内样式重新还原：奶油色圆盘、内圈花瓣纹、居中的音级符号；字形直接采用游戏音乐的矢量路径。
- 键盘卡片标题栏新增「键位提示」开关：开启时在琴键左上角显示电脑键盘字母，关闭后只保留纯游戏内键面；悬停琴键仍显示完整键位与音名。
- 保留行首高音/中音/低音谱号、五线谱线、6 种乐器各自的配色、悠可琴和弦键行，以及晚风圆号的两排结构。

### 版本说明

- Windows 1.1.1：仅修复上述 UI 异常。
- Android 1.1.1：仅同步版本号，功能与 Android 1.1.0 相同；固定签名不变，可直接覆盖升级。

### 下载

| 文件 | 说明 |
|---|---|
| `GenshinInstrumentDetector-1.1.1-win64-setup.exe` | Windows 安装程序（当前用户安装，无需管理员；可覆盖旧版） |
| `GenshinInstrumentDetector-1.1.1-win64-portable.exe` | Windows 免安装版 |
| `GenshinInstrumentDetector-1.1.1-android.apk` | Android 安装包（Android 7.0+） |
| `SHA256SUMS.txt` | 以上文件的 SHA-256 校验和 |

> Windows exe 未做代码签名，SmartScreen 可能提示“未知发布者”；Android 从 1.1.0 起使用固定发布签名。
