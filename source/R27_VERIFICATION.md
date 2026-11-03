# R27 验证与范围记录

日期：2026-11-03。基线 R26：`f84e389`。本地分支：`codex/r27-quest-location-types`。

## 保留内容

以下 10 个文件已分别与 R26 Git 基线、交付的 R26 完整源码 ZIP 核对。其中交付 ZIP 的文件字节与当前文件逐项完全相同：

- `war3_reforged_trainer.py`
- `war3_quest_analysis.py`
- `war3_current_map_script.py`
- `war3_native_profile.py`
- `tools/war3_native_bootstrap_profile.h`
- `tools/war3_native_helper.c`
- `tools/war3_native_helper.dll`
- `tools/war3_quest_camera.h`
- `tools/war3_native_quest_status.h`
- `war3_runtime_check.py`

因此进程／单位读取、原条件判定、native 参数／签名表、已有调用逻辑及相机入口没有改动。helper DLL SHA-256 为 `f0571590d5255f3c442713b22723d77d588755c3e6bfd2f85bfdbeb7f46a7ce6`，继续使用协议 82 与独立相机操作 325；本版没有重新编译 DLL。

## 检查结果

最终检查：**175 passed in 11.13s**。

```powershell
python -m pytest source/test_quest_camera.py source/test_quest_locations.py source/test_quest_location_types.py source/test_quest_ui.py source/test_quest_readable.py source/test_quest_status.py source/test_native_quest_status.py source/test_fullclone_protocol.py source/test_quest_analysis.py source/test_quest_runtime_check.py -q --tb=short
```

新增场景覆盖：

- 进入／离开区域、触发半径、直接矩形。
- 命名击杀／救援／目标命令对象、护送移动及传送位置；Reforged 带皮肤单位构造、直线及同分支局部别名。
- 物品创建、匹配商店、死亡回调、候选掉落表、持有者不等于掉落、交付与使用目标、随机刷新引用区域。
- 可破坏物、中立建筑／归属变更、建造目标。
- 镜头预设、固定观察点和传送目的地。
- 显式计时关联及纯倒计时无位置。
- 参数包装函数、相反分支隔离、同名自定义函数不猜语义、其他任务初始化区域隔离。
- 无坐标对象／ID灰显不可跳转；来源超限提示不生成可点击坐标。
- 原任务解析、解释文字、状态同步、协议与独立 C 相机适配器回归。

`analysis/verify-r27-package.py` 通过：包内相关 Python 源码一致、DLL 字节和协议一致、x64 GUI、文件版本 1.0.19.27、冻结程序离线自检及依赖核对通过。最终 EXE 与完整源码 ZIP 的哈希见交付清单。

## 真实文件与游戏边界

用用户现有《雷克萨之书》战役 `K-ValleyOfTrial.w3x` 只读文件样本核对了扩展关联，能增加任务相关对象、剧情位置及物品来源；没有地点的百科条目保持无位置。样本索引构造约 0.5 秒。

真实文件检查发现了过宽地遍历注册初始化函数、带入其他任务区域的问题；已收紧为当前条件的回调／状态设置路径／显式计时关联，并增加回归用例。没有把出现更多位置就视为正确。

本轮没有操作游戏镜头、单位或任务，也没有逐项在游戏中验收全部新类型。沿用的相机入口此前在本会话 R26 中实际验证，并由用户确认位置正确；该验证不能代替每张地图的对象语义核对。

## 仍需保留的限制

所有地点均为脚本证据；单位只标初始位置，非实时。随机／同 ID 来源是候选；持有关系不是掉落证明。复杂动态数组、缓存、哈希表、随机坐标、自建系统、Lua 或只写在物体编辑器／地图二进制对象数据中的来源可能无法确认，保持无位置。

R27 独立交付，R24／R25／R26 原文件保留；未上传 GitHub。
