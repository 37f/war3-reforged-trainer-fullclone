# R22 标准 JASS 兼容规则与边界

分析器只解析数据，不执行游戏或地图函数。规则先检查地图自身的函数定义；地图定义同名函数时，追踪地图函数体，禁用对应标准适配规则。不存在函数体的未知条件保留原表达式并提示缺口，不按函数名前缀推断。

兼容规则人工对照本地 `YDWE1.32.9正式版/compiler/jass/24/Blizzard.j` 函数体，文件 SHA-256 为 `D290865BD673F8394F4E6FB7B4D6720412FED3A447877523CEC9E54E65B8E62C`。这是明确的兼容规则依据，**不是声称该旧标准库文件就是 2.0.4.23745 加载的完整标准库**；当前地图的脚本、字符串表与游戏构建证据另见来源验证记录。

| 规则 | 核对依据及处理 |
| --- | --- |
| CreateQuestBJ | 原库 5387 行起：创建 quest、设置标题/说明/required/discovered、更新 bj_lastCreatedQuest 并返回；类别常量 0/1/2/3 对应必需已发现/必需未发现/可选已发现/可选未发现。地图遮蔽类别常量时不套用常量值。 |
| GetLastCreatedQuestBJ | 返回 bj_lastCreatedQuest。函数内按创建顺序关联，跨函数保留静态候选；无法唯一关联时列入未关联条件。 |
| CreateQuestItemBJ / GetLastCreatedQuestItemBJ | 原库 5442 行起：QuestCreateItem、设置描述、更新并返回最后条目。数组下标动态时不把不同实例当作同一对象。 |
| QuestSetCompletedBJ / QuestSetFailedBJ / QuestItemSetCompletedBJ | 参数顺序与原生 setter 一致；true 是设置，false 单列重置；动态布尔值分别保留正、反分支。 |
| QuestSetTitleBJ / DescriptionBJ / DiscoveredBJ | 参数顺序按对应库函数；多种静态候选保留并标注，不能称为当前运行值。 |
| ConditionalTriggerExecute | 原库 892 行起：先 TriggerEvaluate，成功后 TriggerExecute。直接 TriggerExecute 不附加注册条件。TriggerExecuteBJ 的第二个参数决定是否检查条件。 |
| CustomVictoryBJ / CustomDefeatBJ | 原库 5245 / 5349 行起：受 AllowVictoryDefeat 对应结算类型控制，调用 RemovePlayer；保留此许可条件，区分关卡结算与任务状态。 |
| RemovePlayer | 只有 PLAYER_GAME_RESULT_VICTORY / DEFEAT 明确归类胜败；中立/平局不当作胜败；动态结果列作未确认结算。 |
| 事件及 TimerStart | 保留完整注册表达式、目标、事件类型、计时参数和回调。事件派发与手动调用分开；发现启停调用时列出证据并提示没有推算当前启用状态。 |

以下是保留原文的标准条件原子：常用 IsUnitEnemy/IsUnitDeadBJ、任务条目状态、GetTriggerUnit/GetDyingUnit/Player 等。它们不在本机求值；没有读取单位当前状态或任务当前进度。未列入规则的外部谓词仍显示原表达式和缺少函数体的提示。

分析范围和上限：调用深度 64、每个目标最多 128 路径、最多 10000 个任务定义、表达式树深度 128、分析 30 秒。循环迭代、跨时序状态、动态 ExecuteFunc、动态对象下标、重复创建包装的实例数量、未确认入口等明确提示覆盖缺口。未知路径不因没有解析成功而消失。
