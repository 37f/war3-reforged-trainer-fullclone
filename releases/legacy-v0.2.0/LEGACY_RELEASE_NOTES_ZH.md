# Warcraft III Legacy 修改器 v0.2.0-Test

Legacy独立测试版，适配 **Warcraft III 1.29.2.9231 x86**。与仓库的Reforged 3.0 FullClone版本分开发布，接口和地址不混用。

**本次是现有v0.2.0成品发布，仍有普通单位复制报错、复制落点未跟随鼠标及英雄升级无原生特效等已知问题。v0.2.1修复尚未完成，不包含在本包中。详见附件`LEGACY_KNOWN_ISSUES_ZH.md`。**

## 下载

- 程序：`War3LegacyTrainer-v0.2.0-Test.exe`
- 独立完整源码：`War3LegacyTrainer-v0.2.0-Test-source.zip`
- 中文使用说明：`LEGACY_USAGE_ZH.md`
- 已知问题与适配限制：`LEGACY_KNOWN_ISSUES_ZH.md`
- 校验：`SHA256SUMS-LEGACY-v0.2.0-PUBLISHED.txt`

源码ZIP为交付的独立33文件源码及清单；GitHub自动Source code压缩包是包含重制版和历史资料的整个仓库。无需安装Python，不含游戏、地图和存档。

## 功能

- 玩家金币、木材、已用人口和人口上限；Ctrl+L增加金币木材。
- 选中单位生命魔法全满：Ctrl+空格；不复活死亡单位。
- Ctrl+Q默认英雄每次升1级，勾选自定义后按输入值设置。
- Alt+Q默认永久三围各加2，勾选自定义后分别设置。
- Ctrl+B复制；Ctrl+A固定复制给自己；Ctrl+N大量复制。归属支持自己、源单位玩家或指定玩家，包含本图实际可用的中立槽位。
- Ctrl+U+8替换选中单位，默认单位ID为zhyd；替换最后才移除原单位。
- F5读取/刷新；三页白色标签界面；快捷键默认关闭，只在已连接游戏前台生效。

## 使用范围

默认目标路径固定为`E:\Games\Warcraft III (Legacy)\Warcraft III.exe`，没有路径选择器；其他路径需自行调整源码后构建。目标EXE精确SHA-256必须匹配`3f2ed0120d80578bf07e4423296dade1adfb959d59a2d20a7584224559570eed`。外壳Windows x64，内部助手x86。换图/读档后重新连接，不与其他修改器同时连接。

## 本次发布核对

直接上传原有EXE和源码包，没有重新编译或修改代码。2026-11-14回读验证33个源码文件、内嵌UI/后端、profile和两个32位组件一致；现有EXE离线三页界面检查通过，没有连接游戏。历史测试地图结果不等同任意地图保证，也不表示后来反馈的问题已修复。

EXE SHA-256：`3902e2747b4bf9f7cb550cfe1d699daf99e620620209b2924f22ff854589ea06`

源码ZIP SHA-256：`11a8fa1473bfadaf9340ee10e99f9a9af6e6be5bf5d197b58e4db00bb24d899b`

现有Reforged发布和源码保留，Legacy测试版不替换正式Latest版本。
