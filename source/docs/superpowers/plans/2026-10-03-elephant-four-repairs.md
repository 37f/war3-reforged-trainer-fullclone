# 大象模式四项修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 不启用子代理。

**Goal:** 修复全光环、全被动、六神器、全屏群星的错误弹窗，并保留 R17 全部其他行为。

**Architecture:** 延用持久 native helper 与绑定单位身份。背包仅开放安全添加分支；预设使用独立的有上限添加动作，普通技能操作不变；群星结束清理仅对 `AEsb` 做限定兼容。Python/C 协议同步升级到 75，防止旧 DLL 混用。

**Tech Stack:** Python 3.12、Windows C helper、pytest、LLVM-MinGW、PyInstaller。

**Spec:** `docs/superpowers/specs/2026-10-03-elephant-four-repairs.md`

## Global Constraints

- 四项范围之外不主动修改功能；不改读取、native 绑定资料、原作者操作号。
- R17 和附件原源码不覆盖；所有修改在独立 R18 副本。
- 不迁移游戏速度或每秒推进建造等已排除功能。
- 不吞掉真实引擎失败；身份失效时停止，不继续操作后续单位。
- 离线验证与游戏实测分开报告；此计划不授权发布到 GitHub。

## Review Focus

- 已有背包与没有背包的单位均可安全确保背包；已有组件不得删除或重置。
- 技能上限为 1、3、112 或超过 112，预设都不得超出实际提供等级。
- 地图不给有效等级上限、native 缺失或单位被回收时，停止写入并报明确失败。
- 群星期间用户重新下令，结束清理不得发送 stop 打断新命令。
- 群星原有技能/临时技能、地图改范围、单位或技能回收、重复释放均有独立断言。

---

### Task 1: 背包和预设等级

**Files:**
- Create: `test_elephant_preset_repairs.py`
- Modify: `tools/war3_native_ability_actions.h`
- Modify: `war3_reforged_trainer.py`（技能组合方法、全光环/全被动入口、协议）
- Modify: `tools/war3_native_helper.c`（协议）
- Modify: `test_fullclone_protocol.py`（协议断言）
- Test: `test_native_ability_actions.py`、`test_native_inventory_batch.py`

**Interfaces:**
- Consumes: `war3_manage_bound_ability(NativeCommand *, NativeOp *)`、绑定身份和现有 `UnitInventorySize` / `BlzGetAbilityIntegerField`。
- Produces: action 5 = 添加并将请求等级限制在 `alev` 上限内；`add_ability_bundle_to_selected_unit(entries, *, bounded_levels=False)` 仅预设入口启用该动作。

- [x] Step 1: 用现有 C harness 写失败测试：`AInv` 已有/新增都成功且没有删除和等级设置；动作 2/3/4 对基础组件仍失败。动作 5 请求 112 时实际写入 `min(112, alev)`；普通动作 3 不被改成钳制语义。
- [x] Step 2: 执行 `python -m pytest -q test_elephant_preset_repairs.py`，确认因未修复行为失败，而不是编译环境缺失。
- [x] Step 3: 在技能头文件增加安全背包分支及 action 5；getter 前后复核绑定单位/技能身份，拒绝无效等级上限；仅两种预设调用开启 `bounded_levels=True`。协议 Python/C 与协议测试同步到 75。
- [x] Step 4: 执行新测试及现有技能、物品批处理、协议回归，确认通过。
- [x] Step 5: 只提交此任务涉及的文件，记录专项结果。

### Task 2: 群星结束清理

**Files:**
- Create: `test_starfall_cleanup_repairs.py`
- Modify: `tools/war3_native_effect_lifecycle.h`
- Test: `test_native_effect_lifecycle.py`

**Interfaces:**
- Consumes: `war3_effect_cleanup(War3AbilityEffect *)` 以及现有 START/FINISH 操作 158..160。
- Produces: `AEsb` 的清理可退休有效 token，同时不覆盖地图的新值、不打断新命令；其他技能清理策略不变。

- [x] Step 1: 复用真实 C 生命周期测试，将技能 ID 换成 `AEsb`；测试换命令、范围第三值、已有/新增技能、技能回收、清理失败、再次释放。要求新命令下 stop 次数为 0，已有技能不被移除，临时技能只移除一次。
- [x] Step 2: 执行 `python -m pytest -q test_starfall_cleanup_repairs.py`，观察限定场景的失败。
- [x] Step 3: 仅对 `AEsb` 允许退休不再拥有的命令/字段改动；临时技能不必恢复即将删除的范围。所有对象身份复核及异常仍保留；普通技能原有测试不得放宽。
- [x] Step 4: 运行新测试和全部现有效果生命周期测试，确认其他效果无回归。
- [x] Step 5: 提交该任务修改和回归证据。

### Task 3: 独立打包与交付

**Files:**
- Modify: `魔兽争霸3重制版修改器.spec`、`analysis/verify-fullclone-package.py`、`V19_FULL_USAGE_GUIDE_ZH.md`
- Create: `R18_ELEPHANT_REPAIR_NOTES.md`、`analysis/R18_VERIFICATION.md`

**Interfaces:**
- Consumes: Task 1 协议 75 和 Task 2 效果清理。
- Produces: `War3ReforgedTrainer-v1.0.19-FullClone-R18.exe`、完整源码 ZIP、SHA-256 清单。

- [x] Step 1: 完整运行 `python -m pytest -q`，记录通过/跳过数量及耗时。
- [x] Step 2: 编译 helper DLL，打包独立 R18 EXE，验证内置源文件与 DLL 一致性和离线启动。
- [x] Step 3: 文档明确这四项修复与未进行游戏实测的边界；不覆盖旧文件。
- [x] Step 4: 交付新命名文件；提示重启游戏清除旧 helper/失败 token，并给出四项游戏验收步骤。
