# R28 验证与范围记录

日期：2026-11-03。基线 R27：`424c054`。本地分支：`codex/r28-quest-pretrigger-locations`。

## 必要改动

- `war3_quest_pretrigger.py`：新增有界的任务创建／发现入口关联，复用已有静态位置及物品来源；不执行地图脚本。
- `war3_quest_locations.py`：新增触发区域／接取对象来源说明、背景索引接入和 `before(q)` 查询。
- `war3_quest_ui.py`：触发前位置独立分组、详情、优先顺序、灰色无位置；复用原点击导航。
- `test_quest_pretrigger.py`、`test_quest_ui.py`：新增静态入口和界面交互回归。
- 独立 R28 spec、文件版本、包校验脚本及本说明、使用说明。

不修改原条件判定语义。现有运行时状态无接取／发现标志，本版不新增读取，界面明确说明该限制。

## 验证

最终源代码检查：**190 passed in 10.30s**。

```powershell
python -m pytest source/test_quest_camera.py source/test_quest_locations.py source/test_quest_location_types.py source/test_quest_pretrigger.py source/test_quest_ui.py source/test_quest_readable.py source/test_quest_status.py source/test_native_quest_status.py source/test_fullclone_protocol.py source/test_quest_analysis.py source/test_quest_runtime_check.py -q --tb=short
```

覆盖了延迟创建、预创建隐藏任务、区域／NPC／物品入口、多地点、直接包装、显式前置触发与传送、对话框回溯、纯计时无位置、显式 false 排除、同名自定义函数、任务参数隔离、无关初始化与其他分支隔离、未知地点不可导航、未完成优先展示、已完成保留条件、刷新不移动相机。

真实文件只读样本：`Book of Rexxar - Drums of War.w3n::K-ValleyOfTrial.w3x`。位置索引约 0.61 秒；“入侵者”等能读出触发区域和接取对象坐标；百科物品缺少脚本坐标时保持无位置。该样本不是当前游戏会话来源证明，也不是游戏内验收。

冻结包检查和保护文件逐字节检查分别见 `R28-package-verification.json`、`R28-preservation-verification.json`。EXE、完整源码及说明的 SHA-256 见 `SHA256SUMS-R28.txt`。

helper DLL 继续使用 R27 同一字节：`f0571590d5255f3c442713b22723d77d588755c3e6bfd2f85bfdbeb7f46a7ce6`。原进程／单位读取、条件分析器、来源校验、native 参数与调用、协议、相机头文件及状态接口与 R27 Git 基线及交付源码 ZIP 一致。

## 交付边界

独立 R28-Test，旧版保留；仅本地提交，没有上传 GitHub。本轮不调用游戏中的相机、单位或任务操作，不改注册表。相机沿用先前 R26 已获用户确认的独立入口；新位置的逐项游戏内验收仍待用户核对。动态位置、复杂间接入口和超限关联不猜坐标。
