# R23 来源与任务执行接口调查

2026-10-25。状态：已确认官方当前章节元数据、本地资源内容、当前 JASS VM 中的任务标识和原生状态读回；执行接口与正式来源绑定仍在实现中。没有调用任务完成／触发器执行，没有 R23 成品交付。

## 实际目标与只读证据

用户打开官方兽族序章“大逃亡”第一章“追寻幻象”。本轮游戏 PID 24336；PID／绝对地址只属于本轮调查，不进入产品。游戏 EXE SHA-256 为 `682c12552ca05e43c5fed2340ea132d3b06fe068e676db7d1f5623d8d4633229`，仍是已支持的 2.0.4.23745 x64。

检测到两个 R22 后，用户关闭了它们。后续正常持久 helper 通道仍使用协议 78，未改动其 DLL 或已有 native 表。

既有操作 318 的前后结果一致，会话为 `9554664792006420347`；精确配置字段读到：

```text
map_path = Campaign/Classic/ROC/Prologue01.w3m
campaign_path = 空
is_campaign = false
```

这说明官方章节由安装资源命名空间提供，不能按自定义 `.w3n` 嵌套章节或同名磁盘文件来找。

早期被动字段试读使用过占位 token 1，只用于定位；后续已使用正常 318 的实际 token 验证前后稳定，不能把早期占位数据当来源证明。

REA 成功绑定精确 EXE。原生分析提供者不可用：Ghidra／IDA 未配置，Hopper 不支持 Windows。未安装分析引擎，改用现有 Capstone、PE 和有界只读进程接口。私有证据保存在对话目录 `outputs/r23-investigation`，不会打包进发布源码。

## CASC 内容读取

固定 CascLib 源提交：`38a34665624b8775bb875274b36191b21c38d97b`。使用既有 LLVM MinGW 编译，不安装系统级依赖；源及原许可证保留在 `source/third_party/CascLib`。

本地 DLL SHA-256：`5641c4f30cb4367127a97dc6b00dda6bc906064323f3e3df5829872b2a829947`。

本机唯一活动 `.build.info` 为 Warcraft III，版本 `2.0.4.23745`，Build Key `9a94ff7d25781db6c09190cd69d52458`。本地 `CascOpenStorage` 不启用在线／下载标志。直接指定成员可读：

```text
war3.w3mod:campaign\classic\roc\prologue01.w3m
```

地图 392867 字节，CKey `ebb196becb07a048532b307a6e6f5d3e`，SHA-256 `12c68604325e146dbd23d46a551f882b2808117b628a5464936d43ab0c9506d8`。CASC 完整元数据指向 `data.017`，段内偏移 802544037，单 span。游戏实际持有同一安装目录的 `Data/data/data.017` 等数据文件；正式来源需进一步绑定文件身份、构建、覆盖和会话，不能以这些路径单独宣称生效版本已证明。

独立 StormLib 只读解出：

| 内容 | 字节 | SHA-256 |
| --- | ---: | --- |
| war3map.j | 394786 | c751d5b8719057a7da1f46a4deda4e594d492c237e319a33aecbf46f092de2ed |
| war3map.wts | 18183 | 0d945cbfa661c60441e6caf81280fc87394e7d3ab4959a457bfaf522046fa6d7 |
| 当前安装 scripts/blizzard.j | 481865 | ec6624f40abe870cd24dc7f19b8dded6f1454069ef7fa5733e6762f2564bbcee |
| 当前安装 scripts/common.j | 361478 | 8744d81546d34c645a1c63e8215facf035034d24b254f5b0a35c62ba6d470f64 |

实际读取的库文件可用于本轮 BJ 规则核对，优于把旧安装的 Blizzard.j 直接当当前标准库。原始官方资源和私有提取件不纳入发布包。

已证伪的猜测：地图内部多语言 WTS 并非当前中文差异的来源。`SFileEnumLocales` 只列出 neutral 0，设置本程序 StormLib locale 为 0x804 仍读回同一基础 WTS，随后已还原本程序库状态。基础 WTS 是英文。运行时 BlzGetLocale 的有界字段读取实际为 `zhCN`，需继续核对显示本地化；不把基础英文文本谎称为已核对的游戏中文标题。

早期通配符查询包含对话动画等非地图成员，随后收敛为精确章节／库路径；不存在在线补齐。私有输出不作为产品检索方式，发布逻辑不得依赖遍历整个 CASC 来猜章节。

## 当前 JASS 绑定

被动沿精确构建字段读取，未扫描整个进程堆：

- 世界对象沿 R22 已验证路径取得；世界 `+0x25e8` 是脚本宿主，当前 vtable RVA `0x2449bf0`。
- 当前宿主低 32 位语言／命名空间索引在 `+8`，本图为 1。
- 既有 context getter `0x30d360` 的 slot 5 为脚本上下文；本图可由游戏线程 TLS 读回。该 TLS 在帧外可能为零，不能据一次零值说没有 VM，也不能把旧缓存地址作为产品入口。
- 脚本上下文 `+0xe8/+0xf0` 是命名空间数量／数组；当前 VM 的 `+0x4868` 回指当前宿主。产品必须在游戏线程里重新解析和核对，不能缓存本次绝对地址。
- VM `+0x4878` 是全局变量名称表；当前 vtable RVA `0x2466598`。节点名在 `+0x28`，标量种类／声明类型在 `+0x30/+0x34`，值在 `+0x38`。
- `udg_QUESTFindProphet` 两种类型读到 7（handle），值 `0x10130a`；`gg_trg_Victory_Found_Medivh` 为 handle，值 `0x101065`。仍需在正式桥中核对具体 quest／trigger 类型与实例，不能只检查通用 handle 类型。
- VM `+0x48c8` 的函数名称表能找到 `Trig_QuestProphet_Complete_Actions`、`Trig_Victory_Found_Medivh_Actions`、main。其载荷是 JASS 字节码地址，**不能当 C 函数调用**。

已有 native profile 和指令已核对 GetFunctionId 与全局查询使用 slot 5 中相同命名空间、名称哈希桶及有界字符串比较。历史 YDWE 结构仅用于提供概念线索，未把旧版 32 位地址／布局搬到产品。

正常 helper 的原生表查询已校验四个现有 quest predicate。利用相同单标量实参 ABI 做只读调查，解释 bool 的 AL 返回字节，实际读回：

```text
IsQuestCompleted = false
IsQuestDiscovered = true
IsQuestFailed = false
IsQuestRequired = true
```

前后仍是同一会话。**关键 ABI 边界：** 部分 bool native 只写 AL，其余位留有旧指针值；本次原始 32 位值例如 1712319488，低字节却为 false。新的类型化桥必须采用正确的 8 位 bool 返回处理，不能用 `raw != 0`。不改旧读单位函数的参数或签名。

## 完成流程与机制选择

脚本本身有 620 个函数，识别出一项寻找先知任务。第 3380 行由 `Trig_QuestProphet_Complete_Actions` 设置完成，但这只是内层通知／标志动作。完整的正常达成流程由 `gg_trg_Victory_Found_Medivh` 的动作开始，设置 GameOver、保护 Thrall，等待后入队 `gg_trg_Prophet_Complete_Q` 和 `gg_trg_End_Cinematic`，最后再走下一关结算。

因此不能仅执行内层 setter 后声称剧情已推进。队列 BJ 调用链也需要识别，而不只是直接 call 或普通 TriggerExecute。

机制决定：优先使用经验证的**原触发器实例＋原生 TriggerExecute**。它接收单个 trigger 标量，原生入口 RVA `0xca87b0`，通过具体 trigger 解析器进入原游戏执行器；保留 GetTriggeringTrigger 所需的原实例，并由游戏建立脚本执行上下文。相较于直接 ExecuteFunc，它不需要新造 JASS string，也避免把新建触发上下文误当原触发器。此选择符合设计允许在原实例建立完整上下文的路径。

这里只确认静态接口、现有查询的 ABI 和实际对象标识。尚未调用 TriggerExecute，睡眠、剧情、奖励、切章与去重需在正式桥实现、用户准备恢复存档并选定任务后实测。

## 尚未通过的产品门槛

1. 正式官方来源绑定：当前安装／数据文件身份、活动构建、松散文件／模组覆盖优先级、中文显示来源、换图清理。
2. 任务与触发器的具体类型、对象代际，以及注册动作／函数签名和同脚本版本的运行时证明。
3. helper 内原子校验、派发前去重记录、超时不重试、重连不重复发奖。
4. 任务执行 UI、实际完整流程测试、官方第二章／独立自定义地图核对、完整回归和 R23 冻结包。

现在已经有只读 CASC 核心模块及首批 12 项测试，仍没有接入或启用官方来源发布／任务执行按钮。
