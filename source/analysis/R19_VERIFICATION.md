# FullClone R19 验证记录

## 身份和范围

- 日期：2026-10-23；目标游戏 2.0.4.23745。
- 来源：已发布 R18 提交 `75b8a868f435ef198c5a8394378f5fd63f6d3279`，在独立克隆/分支实施，未覆盖 R18。
- 范围：现有队伍监视增加选中单位所属玩家的实际名字。旧操作 300～316 不改号；新增只读 317，Python/C 协议 76。
- 原 native profile、签名/哈希、必需绑定表不变。没有新增名字写入、归属/队伍/联盟/控制设置；没有第二个轮询任务。

## 测试过程

1. 恢复原 R18 后完整基线：`1815 passed, 12 skipped, 113 subtests passed in 215.25s`。
2. 名字读取器/协议测试在实现前：`29 failed, 5 passed`；真实 Tk 名字监视也先失败。失败原因为缺少新参数/DTO/C 读取操作，不是用编译失败代替行为测试。
3. 英文界面曾把字面玩家名 `英雄（玩家）` 误翻为 `Hero(Player)`，新真实 Tk 语言切换回归先失败再通过。修复只翻译监视标签，保留玩家名字原文。
4. 名字、原队伍和协议专项：`82 passed in 13.76s`；包含实际编译运行的 Microsoft SEH C 夹具。加上国际化回归：`87 passed in 26.64s`。
5. 冻结包身份三条新测试先全部失败，更新 R19/76/317 后 `3 passed in 0.54s`。覆盖旧协议拒绝、R19 独立文件名以及旧内嵌源码拒绝。
6. 中间一次全套检查发现三条新增错误提示缺少英文映射：`1 failed, 1850 passed`，已补映射。长 GUI 工作流也暴露重复 Tcl 解释器销毁的测试环境问题，改为新工作流独占子进程；原程序启动不改。

审阅前完整回归（重编 helper 后）：

```text
python -m pytest -q
1854 passed, 12 skipped, 113 subtests passed in 225.94s (0:03:45)
exit_code=0
```

12 项跳过仍列为跳过，不能算通过；新增名字 C 夹具均实际运行。

## 实际游戏读回

用户关闭 R18 并回复已重开游戏后，R19 源码/协议 76 后端实际查询 PID 25360：

```text
player_slot=4     # 界面玩家 5
native_team=1    # 界面队伍 2
owner_handle=1048588
player_name=石塔赛特斯
player_name_error=0
显示：玩家 5（石塔赛特斯）：队伍 2
```

连续三次返回一致的名字/队伍，没有执行名字、归属、队伍、联盟或控制设置。此次读回证明该游戏环境下有界 UTF-8 读取可用；用户尚未独立确认其与所选单位的归属一致。中立玩家/其他地图以及最终冻结 EXE 界面未进行真实游戏验收，不能用离线夹具或源码读回代替。

## 构建与包一致性

- Python 3.12.10、Capstone 5.0.7、PyInstaller 6.22.2、官方 LLVM-MinGW 20261020 / clang 23.1.4。
- LLVM-MinGW 下载档 SHA-256：`FD5462B7F5D93B2FF981FCD3F9C7E427E47F3203C64EA91C27BCC444EEBD74CD`。
- SEH helper 编译、PyInstaller 构建及 `python analysis/verify-fullclone-package.py` 均退出 0。
- EXE 为 x64 GUI，版本 1.0.19.0；最终修复后重建为 15474903 字节。
- 内嵌主模块、国际化和运行自检模块与本次源码语义一致；内嵌 helper 与重编 DLL 字节一致，无旧独立扩展 helper。
- EXE 离线 `--runtime-self-test` 通过，包括 Capstone 解码及 helper 哈希。
- 最终 EXE SHA-256：`54929BC3B7365A51B5FFBC0EA156BFC393A8F3DE3F0887CD32DF5B13AFB2B109`。
- helper SHA-256：`2F0A9597D27C54C8ED7AF9884DDC448C504D8759707B74E11E1EC039BD16F5D9`。
- 原 R18 EXE 校验仍为 `CAF3B3FA2BC74D5FE4C81EB32D5392B4D8FCCFD07F300C4094AB326DA4DC6D2C`，与发布版本相同。
- 机器可读包报告：`r19-package-verification.json`。离线校验未打开游戏。

## 审阅和交付状态

一次独立全分支审阅完成，Critical 0 / Important 1 / Minor 0。唯一 Important 是等待 helper 期间选择变化后旧名字仍可能被发布；已接受并做一次针对性修复。五类后台上下文变化及真实 Tk 手动读取迟到结果先重现失败，再修复为全部通过，相关专项 93 passed。默认 316 不增加额外选择读取。详情与保留边界见 `R19_CODE_REVIEW.md`。

修复后已重新构建 EXE，内嵌源码、DLL 和离线运行时自检再次通过。最终完整回归：

```text
python -m pytest -q
1860 passed, 12 skipped, 113 subtests passed in 231.23s (0:03:51)
exit_code=0
```

只有这一次修复轮次，没有再次委派审阅，也没有遗留 Critical/Important 或延期 Minor。源码 ZIP 交付身份和每文件校验分别记录在交付目录的 `delivery-verification.json` 与 `SHA256SUMS.txt`；测试与 ABI 原始证据另存 `verification-evidence/`。只在本地保留 R19 分支，不推送 GitHub。
