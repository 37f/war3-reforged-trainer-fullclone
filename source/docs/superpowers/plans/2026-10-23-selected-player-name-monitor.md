# Selected Player Name Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在已有队伍监视中，每秒显示同一个实时选中目标所属玩家的编号、实际名字和队伍。

**Architecture:** 保留 R18 的队伍查询 316 及其返回格式，新增只读查询 317，返回队伍信息和有长度限制的玩家名字。Python/C 协议同步到 76；共用原操作锁、后台读取任务、监视开关和主线程刷新入口，不增加第二个轮询任务。

**Tech Stack:** Windows x64、Python 3.12、Tkinter、持久 C native helper、支持 Microsoft SEH 的 LLVM-MinGW、pytest、Capstone、PyInstaller。

**Spec:** `docs/superpowers/specs/2026-10-23-selected-player-name-monitor-design.md`

## Global Constraints

- 用户已确认设计与本计划，选择主会话 inline 执行和一次 fresh-context 全分支独立审阅。
- 独立 R19 工作副本：`work/v19-migration/fullclone-r19-player-name`；公开仓库根内的程序位于 `source/`。从 GitHub R18 提交 `75b8a868f435ef198c5a8394378f5fd63f6d3279` 恢复，保留远端和旧程序，不推送。
- 没有源码级改名功能；只显示单位所属玩家的实时名字。中文及中立玩家必须支持。
- 不改单位读取、归属、控制、队伍切换/恢复、外交关系或 R18 四项修复；原有 native 签名/哈希资料保持不变。
- 名字和队伍共用经身份校验的选中单位/所属玩家上下文。名称不可用时显示“名称暂无法读取”，不拼接旧名称，不每秒弹错误窗口。
- 新 EXE 命名 `War3ReforgedTrainer-v1.0.19-FullClone-R19.exe`，另交付源码 ZIP、说明、验证记录和 SHA-256；不覆盖 R18、不自行上传 GitHub。
- Python 3.12.10、pytest、PyInstaller、pefile 当前存在；Capstone 当前不可导入，clang 当前不在 PATH。执行时先查本机已有依赖/编译器，缺少时说明需要的来源，不把 C 夹具跳过算作验收通过。

## Review Focus

1. 中文、多字节边界、空名、超长字符串及无效编码：有界读取、严格解码，不崩溃或展示随机内存。
2. 名称返回值的 JASS ABI：原版字符串字段明确未开放；先以源码/反汇编/只读运行证据验证，不假设返回值是 C 字符串地址。
3. 快速切换目标、游戏 PID 变化、旧后台任务晚到：名字/队伍不串玩家，失效结果不得更新界面。
4. 原有队伍查询 316、快照和中立外交模板：原行为与原协议数据语义不变，监视没有写游戏状态的副作用。
5. 仅名称查询失败或缺少名称接口：本次有效的编号/队伍仍显示，旧名字清空，不使其他操作失效。

---

### Task 1: 恢复基线并验证只读名字接口

**Files:** `source/tools/war3_native_helper.c`、`source/war3_native_profile.py`、`source/tools/war3_native_bootstrap.h`（只读检查）；新增 `source/analysis/R19_PLAYER_NAME_ABI.md`。

**Interfaces:** 产出带游戏版本/文件身份、`GetPlayerName` 签名、返回值表示和长度/编码证据的 ABI 记录，供 Task 2 使用；没有证据时不得编造字符串解引用实现。

- [x] 依据 using-git-worktrees 的环境检查恢复独立工作副本；将已确认设计和本计划放入其 `source/docs/superpowers/`。不改旧 EXE、游戏或地图。
- [x] 检查现有构建依赖/SEH 编译器，恢复所需测试环境，执行 `python -m pytest -q` 基线；记录真实通过/跳过/失败，而非假定历史 1815 项结果仍有效。
- [x] 检查 `GetPlayerName` 的已知绑定及字符串返回接口。需要分析游戏二进制或运行证据时使用 reverse-engineer-anything 技能；仅只读采集，不执行未知 ABI 调用。游戏当前未运行，若必须进行游戏内采集，明确请求用户打开游戏配合。
- [x] 写下可复核的字符串路径、编码、长度界限、空/非法指针拒绝条件；若不能安全确定，暂停该实现点并报告，不用猜测布局填补证据。
- [x] 提交设计、计划和证据记录，保持功能代码未改。

### Task 2: 实现只读名字查询、模型和原监视接入

**Files:** 修改 `source/tools/war3_native_helper.c`、`source/war3_reforged_trainer.py`、`source/war3_ui_i18n.py`、`source/test_fullclone_protocol.py`；新增 `source/tools/war3_native_player_name.h`、`source/test_fullclone_player_name_monitor.py`；原 `source/test_fullclone_team_monitor.py` 继续回归。

**Interfaces:**
- C：`static DWORD war3_read_bound_player_name(const NativeCommand *cmd, uint64_t owner_handle, unsigned char *output, uint32_t capacity, uint32_t *byte_length)`，仅使用 Task 1 已验证接口；容量 512 字节，不返回游戏内部字符串地址。
- C/Python 新只读操作 `317`：保留队伍结果 `result`、owner `arg0`、slot/peer_count `arg1`；extra_results 为关系快照 qword，随后为 `name_status`、`name_byte_length`、零填充 UTF-8 字节 qword。名字最多 512 字节，超长拒绝而非切断多字节字符；长度/额外数据数量必须一致。
- `PlayerTeamStatus` 尾部增加默认字段 `player_name: str | None = None`、`player_name_error: int = 0`，兼容现有位置参数构造。
- `query_selected_owner_team(self, *, include_player_name: bool = False) -> PlayerTeamStatus`：默认仍为操作 316；GUI 传 `True` 使用 317。`format_player_team_status(value)` 在有名字时拼入实际名字；新名字查询失败时插入明确的不可用提示，原无名字调用保留其旧描述。

- [x] 先写并运行失败测试：中文/英文精确还原；玩家25/28保留中立标识；512字节边界、超长、非法UTF-8、空名和长度不符；名字失败保留本次队伍；跨玩家/进程结果拒绝；旧316不变；C夹具确认零状态写入。
- [x] 根据已验证 ABI 实现有界字符串读取和 317，复用队伍读取但不改 316；用新头文件隔离名字读取，不改普通技能/物品字段接口。仅确有必要时追加名称绑定，不改变旧名称索引或 native profile；名称接口缺失不得让原队伍读取失效。
- [x] 同步 Python/C 协议到 76，严格检查新返回格式；为新名称绑定失败及其他既有绑定仍严格受检补上回归。
- [x] 将原监视 worker 改用 `include_player_name=True`，沿用锁、generation、trainer/PID 和主线程验证；清空失效名称，维持原手动按钮及每秒刷新开关。
- [x] 运行真实 Tk GUI 测试：只有原监视开关；手动和定时均读取名字；从有名字到空选择/断开/换PID不残留；后台迟到结果不更新；名称失败不触发循环弹窗。
- [x] 执行 `python -m pytest -q test_fullclone_player_name_monitor.py test_fullclone_team_monitor.py test_fullclone_protocol.py`，确认全部新增C夹具实际运行，检查补丁没有新增状态写入，然后提交。

### Task 3: 验证、打包与独立交付

**Files:** 修改 `source/魔兽争霸3重制版修改器.spec`、`source/analysis/verify-fullclone-package.py`、`source/V19_FULL_USAGE_GUIDE_ZH.md`；新增 `source/R19_PLAYER_NAME_MONITOR_NOTES.md`、`source/analysis/R19_VERIFICATION.md`；产物放 `outputs/v1.0.19-FullClone-R19/`。

**Interfaces:** 程序版本仍为 `1.0.19`，扩展名 R19、协议 76；现有扩展操作 300～316 不改编号，新增 317。EXE、源码、说明及校验必须相互对应。

- [x] 更新 spec 和包校验器为 R19/76/317，保留原 helper/源码一致性及离线运行自检断言；补一条冻结包身份/协议不匹配的失败校验。
- [x] 先用支持 SEH 的 LLVM-MinGW 重编 helper DLL，再执行 `python -m pytest -q`；如有失败先解决，不用跳过绕过验收。
- [x] 执行 `python -m PyInstaller --noconfirm --clean '魔兽争霸3重制版修改器.spec'` 与 `python analysis/verify-fullclone-package.py`，检查内嵌 DLL、源码、协议和新增操作匹配，离线自检通过。
- [x] 做全分支复审；按用户选定执行方式决定是否启用审阅子代理。检查 Review Focus 五项、无关功能差异及只读边界；没有实际游戏验证时明确记录。
- [x] 输出独立 EXE、完整源码 ZIP、使用说明、验证记录和 SHA256SUMS；验证 ZIP 内容/源码对应关系与所有文件哈希，保留 R18。先存档、重启游戏并只运行 R19后再验收真实名字；不自行上传 GitHub。
