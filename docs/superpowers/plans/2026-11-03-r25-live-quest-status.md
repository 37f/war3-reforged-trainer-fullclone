# R25 实时任务状态同步实施计划

> **For agentic workers:** 实施时逐项完成并保留边界记录。不得调用任务 setter 或地图触发器。

**Goal:** 在 R24 静态任务页上只读显示当前主线／支线任务的进行中、已完成或已失败状态。

**Architecture:** 使用 R24 当前地图身份与来源校验；新建有界的 JASS quest 全局解析和状态映射模块；native helper 通过已注册 getter 读取状态；Tk 仅在页面可见、报告有效时异步轮询。任务名与运行时句柄无法唯一对应时 fail closed。

**Tech Stack:** Python 3.12、Tk、Windows x64 native helper、Warcraft III 2.0.4.23745 JASS native profile。

**Spec:** `docs/superpowers/specs/2026-11-03-r25-live-quest-status-design.md`

## 全局约束

- R24 基线提交：`876ec2ef55350ea4f2f174506a66c183caacbcfe`。
- R24 native helper protocol 80；R25 配对 protocol 81。
- 操作号 320–322 退役；323 继续用于来源策略；新增只读操作为 324。
- 只使用当前已校验的 2.0.4.23745 x64 profile；重新解析当前会话指针，不能缓存旧绝对地址。
- native getter 返回 bool 时读取低 8 位；不能用完整寄存器值是否为零判断。
- 不添加任务执行、脚本派发、setter、奖励、胜败或存档功能。
- 不覆盖或删除 R24，R25 不推送、不发布。
- 进行与本次状态读取直接相关的离线检查；将源代码/冻结包核对与实际游戏证据分别记录。

## 文件与责任

- `source/war3_quest_status.py`：静态别名资格、名称请求编解码、批次上限、唯一性判定和状态结果规范化；VM 及句柄解析放在游戏线程内。
- `source/war3_reforged_trainer.py`：沿用来源校验、将当前会话令牌和变量名批量交给 helper、配对协议常量与 R25 启动自检。
- `source/tools/war3_native_helper.c`：注册 `IsQuestCompleted`／`IsQuestFailed` getter，严格校验句柄与请求，仅返回布尔状态。
- `source/war3_quest_ui.py`：1 秒轮询、状态列/详情、错误与会话变化清理。
- `source/War3ReforgedTrainer-FullClone-R25.spec`、`source/tools/war3_r25_version_info.txt`、`source/analysis/verify-r25-package.py`：R25 独立构建标识、helper protocol 与冻结包对应关系。
- `source/R25_任务状态同步使用说明.md`：说明支持范围、“状态未确认”含义与游戏实测边界。

## Review Focus

1. 地图切换后迟到的 native 回复不能把旧状态写入新报告。
2. 8 位 bool 返回必须正确解释，不能因寄存器高位残留误判。
3. 全局名重名、多个别名映射到不同句柄、数组/局部变量不能被猜成唯一任务句柄。
4. native 缺失、SEH 异常、构建不匹配时只让实时状态未确认，不能让静态报告崩溃或消失。
5. 超过查询上限、任务页隐藏、连接断开时不能形成无限查询或使用过期缓存。

## 实施任务

### Task 1：当前会话的任务句柄解析

**Files:** 新建 `source/war3_quest_status.py`；修改 `source/war3_reforged_trainer.py`。

- [x] 依据当前 map snapshot/session identity 获取当前 VM 与 JASS namespace；每轮重取并验证 world/host/VM 类型签名和回指关系。
- [x] 只按 `QuestDefinition.aliases` 精确查询静态分析得出的全局名称；验证声明类型为 `quest`、全局值种类为 handle、值非空且句柄能由已验证的 handle resolver 解析。
- [x] 对缺失、重复、动态索引、局部句柄、数组或超限任务返回每任务的“状态未确认”原因，不执行全堆扫描。
- [x] 将运行时句柄结果与 report identity、session token、script hash 一同封装，确保状态回复绑定同一地图报告。

### Task 2：只读 native getter 操作

**Files:** 修改 `source/tools/war3_native_helper.c`；必要时新增 `source/tools/war3_native_quest_status.h`；修改 `source/war3_reforged_trainer.py`、native profile/bootstrap 名称表。

- [x] 按名称/签名在现有 native bootstrap 表内局部绑定两个 getter，保持既有持久表与初始化依赖稳定。
- [x] 新增 operation 324；最多每批 16 个变量名，附加输入不超过现有 28 个 QWORD；对输入句柄、当前进程/地图绑定和 getter executable pointer 做校验。
- [x] 单独调用 `IsQuestCompleted` 与 `IsQuestFailed`，用 `uint8_t` 接收；SEH 错误通过现有 helper 错误通道返回，不进行 setter 或触发器调用。
- [x] R25 Python/helper protocol 成对升级至 81；保留 320–323 旧语义，拒绝未知协议和越界批次。

### Task 3：状态轮询和 UI

**Files:** 修改 `source/war3_quest_ui.py`；修改 `source/war3_reforged_trainer.py` 的 provider wiring。

- [x] 仅当报告有效、任务页可见、当前身份未变且到达 1 秒间隔时，后台提交有界状态查询。
- [x] 结果逐项规范化为进行中／已完成／已失败／未确认；完成与失败同时为真时显示未确认。
- [x] 任务树增加“当前状态”列；详情显示状态与最近成功读取时间，搜索仍覆盖现有任务文字。
- [x] 在断开、切图、报告失效、关闭/隐藏和 generation 变化时清掉状态并丢弃迟到结果；status query 异常保留静态任务报告。

### Task 4：R25 独立构建

**Files:** 新建 R25 spec、版本信息、包校验器和中文使用说明。

- [x] 用 R25 独立 EXE 名称构建，不覆盖游戏目录里的 R24 或任何已发布版本。
- [x] 对照构建清单确认 Python helper protocol、native DLL protocol、operation 324、打包模块和版本信息全部一致。
- [x] 完成 135 项相关检查及冻结包核对；已只读核对游戏当前进行中/已完成状态，实际状态变化及失败现场仍明确标记待验证。
- [x] 不推送 GitHub，不改 R24 release/tag/assets。

## 完成条件

- R25 构建包含只读状态同步，R24 保持原样。
- 静态分析不可用的状态明确为未确认，不能误标为进行中/完成/失败。
- 报告记录 native 状态读取的构建、session 与时间边界。
- 用户需在安全测试地图中验证完成和失败各一项后，才能称为游戏实测通过。

## 执行记录（2026-11-03）

已完成只读状态实现、135 项相关检查、独立 DLL/EXE 构建和冻结包核对。用户重开游戏后，直接查询与产品控制器均连续三轮读回；用户确认萨科斯已完成、入侵者及塔兹利尔的镐进行中，与游戏一致。任务状态变更现场及失败现场未验证。

实施调整：从历史 R23 提取已验证的 VM/符号读取部分，在 helper 内按当前游戏线程解析，避免 Python 先取句柄再发请求的时间差；两个 getter 在查询范围内绑定，不更改既有持久 native 索引或扩大原有功能的初始化依赖。执行/奖励/触发器代码未迁回。
