# 魔兽争霸 III 重制版修改器 FullClone

这是基于[原作者的 v1.0.19 源码提交](https://github.com/dc114154qq/war3-reforged-trainer/tree/4124cd582ed624eeb85d665484755fa8cae65697)制作的非官方扩展版。本仓库不代表原作者发布；原项目的功能与本扩展的改动请分别参看源码和[迁移审计](releases/v1.0.19-R16/FULLCLONE_MIGRATION_AUDIT.md)。

当前发布版本是 **v1.0.19 FullClone R16**，目标游戏版本为 **Warcraft III 2.0.4.23745**。R16 修复了“大量复制”和 `Ctrl+N` 因批量方法不接收 `preserve_owner` 参数而弹错的问题；批量复制会把面板归属选择传给每一次复制。

## 下载

- [Windows 单文件 EXE](releases/v1.0.19-R16/War3ReforgedTrainer-v1.0.19-FullClone-R16.exe)
- [R16 源码 ZIP](releases/v1.0.19-R16/war3-reforged-trainer-v1.0.19-fullclone-r16-source.zip)，也可直接浏览 [source/](source/)
- [完整中文使用说明](releases/v1.0.19-R16/V19_FULL_USAGE_GUIDE_ZH.md)
- [SHA-256 校验文件](releases/v1.0.19-R16/SHA256SUMS.txt)

运行前先启动游戏并进入地图，再以管理员身份运行修改器、连接游戏进程。切换地图或重启游戏后应重新连接。复制归属开关和快捷键的具体用法见使用说明。

## 验证范围

R16 源码完整回归结果为 `1747 passed, 12 skipped, 113 subtests passed`。冻结包验证确认应用版本 `1.0.19`、helper 协议 `73`、内置 DLL 身份和离线自检。R16 的大量复制归属结果仍需在游戏地图内复测。

本仓库的 `source/` 来自 R16 提交 `2f1cf8f`。公开打包时排除了一份含本机路径的旧环境审计，并清理了主程序文件末尾的空白行；程序逻辑、测试和 helper 文件未改。
