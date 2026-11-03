# R29 验证与范围记录

日期：2026-11-03。基线 R28：`9bfffcc`。本地分支：`codex/r29-quest-location-display-toggle`。

本次只调整任务页展示：默认关闭“触发位置”；开启后才显示关联区域、坐标、触发前分组和导航链接。任务说明、目标、条件及状态保留。详情中原说明始终位于触发前线索之前。取消勾选后不接受新的位置跳转，异步旧导航提示不会再次显示。

生产代码改动：`war3_quest_ui.py`。测试改动：`test_quest_ui.py`、`test_quest_readable.py`。另有独立 R29 spec、版本信息、冻结包校验脚本及文档。

保护文件检查覆盖主程序、脚本来源校验、原条件分析器、位置及触发前解析、状态接口、JASS 解析与文字说明、native 参数表、helper 源码／DLL、独立相机和状态头文件、离线运行检查。检查结果记录在 `R29-preservation-verification.json`，同时核对 R28 已交付源码 ZIP 的逐文件字节。

最终检查：**191 passed in 11.39s**。测试命令：

```powershell
python -m pytest source/test_quest_camera.py source/test_quest_locations.py source/test_quest_location_types.py source/test_quest_pretrigger.py source/test_quest_ui.py source/test_quest_readable.py source/test_quest_status.py source/test_native_quest_status.py source/test_fullclone_protocol.py source/test_quest_analysis.py source/test_quest_runtime_check.py -q --tb=short
```

冻结包检查：`analysis/verify-r29-package.py`，确认打包源码、DLL、协议 82、文件版本 1.0.19.29 和冻结程序离线运行自检；记录于 `R29-package-verification.json`。

本轮不调用游戏单位、任务或相机操作，不修改注册表。沿用此前已验证的相机入口；测试验证开关和导航路由，不构成新增地图位置的游戏内验收。独立交付，R28 及更早文件保留，未发布 GitHub。
