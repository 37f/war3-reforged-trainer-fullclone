# R25 本地构建与核对记录

日期：2026-11-03。基于 R24 恢复提交 `876ec2ef55350ea4f2f174506a66c183caacbcfe`，独立分支 `codex/r25-live-quest-status`。本版未推送或发布 GitHub，未替换 R24。

## 完成内容

- 新增只读操作 324；Python/helper 协议 81。
- 请求只携带当前会话令牌和有界的 JASS 全局名称。helper 在游戏线程内重新绑定当前 VM、名称、具体 quest 对象和完整身份，再调用 `IsQuestCompleted`／`IsQuestFailed`。布尔结果取低 8 位。
- 任务页可见且来源有效时，每轮间隔约 1 秒异步同步；行状态、详情、最近成功读取时间自动更新。状态错误保留静态报告。
- 数组、局部任务变量、BJ 临时变量、重复／冲突别名、未创建或销毁对象均不猜测。不同定义指向同一实例也不猜测。完成／失败同时为真显示未确认。
- 取消、隐藏、断开、换图、来源过期会清除旧状态；旧 worker 结果无法重新发布。自动刷新保留当前选择及阅读滚动位置。
- 操作 320–322 仍被 Python 和 C 分派器拒绝，没有重新增加任务执行。

## 离线检查

最终相关检查：**135 passed in 8.90s**，范围为：

```powershell
python -m pytest source/test_native_quest_status.py source/test_fullclone_protocol.py source/test_quest_status.py source/test_quest_ui.py source/test_quest_readable.py source/test_quest_analysis.py source/test_quest_runtime_check.py -q --tb=short
```

包括实际 C 任务绑定适配器的本地夹具：故意让布尔 getter 的寄存器高位非零，确认 false 不会误读为 true；另覆盖重复符号、无效句柄、失效完整身份、类型不匹配。该夹具未连接游戏。

初次检查暴露了本机缺少 Capstone、旧测试桩没有新增状态字段、旧协议测试仍期待 80，以及 C 测试编译命令未显式启用 Microsoft SEH。这些环境／测试合约已修正后再运行最终集合；未将初次失败或跳过记录当作通过。

本地 DLL 使用固定 LLVM-MinGW 20261020 编译：

```text
clang -fms-extensions -fseh-exceptions -shared -O2 -s -Wno-microsoft-goto tools/war3_native_helper.c -o tools/war3_native_helper.dll -luser32 -lkernel32 -ladvapi32
```

编译器来自 `mstorsjo/llvm-mingw` 固定版本资产；下载包 SHA-256 为 `fd5462b7f5d93b2ff981fcd3f9c7e427e47f3203c64ea91c27bcc444eebd74cd`。本地构建依赖未写入系统安装或交付源码包。

`analysis/verify-r25-package.py` 已通过：冻结包源代码一致，helper 字节及协议一致，依赖／许可证存在，EXE 为 x64 GUI，文件版本 1.0.19.25，冻结程序离线自检成功。源码中保留 R24 包校验器，其默认期望没有改变。

## 实际游戏只读核对

- 游戏磁盘 EXE SHA-256：`682c12552ca05e43c5fed2340ea132d3b06fe068e676db7d1f5623d8d4633229`。
- 对旧进程被动读取三个任务绑定相关代码段，指纹均与 R23 已验证记录一致。磁盘文件与运行中展开代码不同，核对使用运行中代码指纹，没有把磁盘指纹误报为相同。
- 用户关闭 R24 并重开游戏后，新进程正式使用 R25 的当前来源和只读状态接口。
- 当前来源为《雷克萨之书》战役的 `K-ValleyOfTrial.w3x`，读到 12 项定义。其中“萨科斯”为已完成，“入侵者”和“塔兹利尔的镐”为进行中；“邪恶的威胁”和“回音群岛”无有效任务句柄，返回状态未确认。连续三次直接查询一致。
- 用户明确核对上述完成／未完成状态与游戏一致。
- 使用产品的 `QuestAnalysisController` 再连续三轮自动轮询，12 项状态正常，未出现接口错误，静态报告保留。

本轮没有修改任务标志、调用地图触发器或推进游戏任务。**尚未在实际游戏观察从进行中变为完成／失败的瞬间；失败状态分支已通过离线 C 与 Python 检查，实际地图的失败状态仍待用户后续验证。** 官方战役覆盖策略和换图现场未在本轮重做游戏验收。

## 交付

独立 EXE：`War3ReforgedTrainer-v1.0.19-FullClone-R25-Test.exe`。另附完整源码 ZIP、中文说明、机器可读包核对结果及 SHA-256 清单。构建工具、缓存、游戏资源和私有原始调查日志不纳入交付源码。
