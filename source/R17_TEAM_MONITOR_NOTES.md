# v1.0.19 FullClone R17：选中玩家队伍监视

基于已发布 R16 源码提交 `2f1cf8f`，添加只读的选中玩家队伍查询。

## 使用方法

1. 启动游戏、进入地图并连接修改器。
2. 在游戏中选中需要确认队伍的玩家任意一个单位。
3. 在“大象功能 → 功能面板 → 目标单位”的队伍操作下点击“读取队伍”；勾选“监视队伍（每秒刷新）”可持续读取。
4. 确认显示的队伍后，选择目标队伍并点击加入或按 `Ctrl+F1`。

监视读取的是当前选中单位所属玩家，与转让单位用的“目标玩家”下拉框无关。多选时按现有队伍功能的主选单位读取。目标队伍下拉框保持用户选择，不会被监视刷新覆盖。

## 显示规则

- 普通玩家：`玩家 8：队伍 4`，界面队伍从 1 开始编号。
- 特殊中立槽位：显示中立敌对/中立被动槽位与原生 `GetPlayerTeam` 数值，不把特殊中立编号当作大厅普通队伍。
- 外交模板：本次进程有切换快照，并且当前双向联盟关系与上次成功应用的模板一致，才显示模板队伍；同时保留原生队伍编号供区分。
- 关系被地图脚本或其他操作更改后，不再显示过期模板为当前队伍，显示“关系已变化”。
- 仅通过联盟关系无法唯一判断地图自行定义的“队伍”；没有本修改器的匹配快照时，按游戏原生编号显示。

## 实现边界

- 在现有持久 native helper 增加只读操作 `316 / EXT_QUERY_SELECTED_OWNER_TEAM`，协议提升到 `74`，防止旧 DLL 被当作包含新功能的 helper 使用。
- 现有操作号、读单位路径、复制和队伍切换/恢复函数保持原逻辑。查询不会写入队伍、联盟、归属，也不会建立或覆盖原队伍快照。
- 监视与其他操作共用已有互斥锁，每秒最多请求一次；关闭监视或重新连接后丢弃过期返回。读失败仅更新队伍提示栏。

## 验证方式

新增测试覆盖普通队伍读取、中立槽位、外交模板读回核对、地图关系变化、跨进程快照拒绝、无选择与异常元数据；编译 C 测试记录队伍/联盟 setter 调用次数，确认查询为零写入；真实 Tk 控件测试覆盖手动读取、保留目标队伍选择、关闭监视后拒绝过期返回和无选择时不弹窗。

完整回归结果与冻结包检查结果随本次发布附带。上述自动化与离线测试不等同于游戏地图内实测。

本次完整回归：**1765 passed, 12 skipped, 113 subtests passed**；专项测试：**46 passed**。EXE 离线启动与内置源码/DLL 一致性检查通过，详情见 `analysis/R17_VERIFICATION.md` 和 `analysis/r17-package-verification.json`。

## 从源码重新打包

本次使用 Python 3.12.10、Capstone 5.0.7、PyInstaller 6.22.2。源码已包含编译好的 `tools/war3_native_helper.dll`，未修改 C 源码时可以直接打包：

```powershell
python -m pip install capstone==5.0.7 pyinstaller==6.22.2
python -m PyInstaller --noconfirm --clean '魔兽争霸3重制版修改器.spec'
python analysis/verify-fullclone-package.py
```

如修改了 helper C 源码，需要使用支持 Windows x64 Microsoft SEH 的 LLVM-MinGW 编译器重新生成 DLL，保持 Python/C 协议版本一致，再打包：

```powershell
clang -fms-extensions -fseh-exceptions -shared -O2 -s -Wno-microsoft-goto tools/war3_native_helper.c -o tools/war3_native_helper.dll -luser32 -lkernel32
```

打包结果为 `dist/War3ReforgedTrainer-v1.0.19-FullClone-R17.exe`。不要把 R16 的旧 helper DLL 与 R17 源码或程序混用。
