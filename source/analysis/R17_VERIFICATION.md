# FullClone R17 验证记录

## 基线与范围

- 基于 R16 提交 `2f1cf8f`，独立目录中实施；未覆盖旧程序或旧源码。
- 新增选中单位所属玩家队伍的手动读取与每秒监视。
- 新增只读持久 helper 操作 `316`，Python/C 协议同步到 `74`。
- 保留既有读取路径、操作号，以及复制、归属、队伍切换和恢复行为。

## 实际执行结果

### 专项回归

```text
python -X utf8 -m pytest -q test_fullclone_protocol.py test_fullclone_team_monitor.py
46 passed in 7.27s
exit_code=0
```

### 完整回归

```text
python -X utf8 -m pytest -q
1765 passed, 12 skipped, 113 subtests passed in 217.77s (0:03:37)
exit_code=0
```

本次编译 C 测试使用支持 Microsoft SEH 的 LLVM-MinGW。新增原生查询测试记录 `SetPlayerTeam` / `SetPlayerAlliance` 的调用数为零；分发器测试验证绑定身份查询交易通过、无绑定交易被拒绝。真实 Tk 控件测试使用模拟游戏响应，验证手动读取、保留目标下拉选择、关闭监视丢弃排队返回和无选择时不弹错误窗。

### 编译与冻结包

```text
LLVM-MinGW: tools/war3_native_helper.c -> tools/war3_native_helper.dll
python -m PyInstaller --noconfirm --clean 魔兽争霸3重制版修改器.spec
python analysis/verify-fullclone-package.py
all exit_code=0
```

- x64 GUI EXE，文件版本 `1.0.19.0`。
- 冻结 EXE 内的主模块、国际化模块、运行时自检模块与本次源码一致。
- 只包含持久 `war3_native_helper.dll`，无旧扩展 helper DLL。
- 离线 `--runtime-self-test` 成功。
- EXE SHA-256：`F9BC124EDB5528BBFB95665FD0C1A1B6B01ED62797677A7C027A5D8C844A493E`。
- helper SHA-256：`B2CCAC7CCF7CFC0393492BFEF08C784A9602F7284C808C9AECA942C42D2B2B46`。

完整冻结包报告见 `r17-package-verification.json`。

## 未验证边界与游戏内验收

本次没有连接实际 Warcraft III 地图进行队伍监视实测，自动化和离线证明不等于游戏行为证明。

建议在单机地图按以下步骤验收：

1. 连接修改器，选中已知队伍的普通玩家单位，点击“读取队伍”，核对队伍编号。
2. 勾选监视，切换到其他玩家单位，确认一秒左右更新且目标队伍下拉值不变。
3. 取消单位选择，确认提示无法读取而不是弹出错误窗。
4. 切换该玩家队伍，再恢复原队伍，确认读数跟随且原队伍快照仍按首次记录恢复。
5. 选中中立敌对/被动单位，确认标记特殊槽位；套用扩展队伍模板后，核对外交模板标签，而不是仅凭原生 `GetPlayerTeam` 编号推断普通队伍。
