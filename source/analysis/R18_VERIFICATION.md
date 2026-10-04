# FullClone R18 验证记录

## 范围和基线

- R17 基线 `67f905c`；独立 R18 目录，不覆盖原附件或旧程序。
- 修复范围：全光环、全被动、获得 6 个神器、全屏群星陨落。
- Python/C 协议同步为 75；原有操作号和 native 绑定 profile 未改。
- 追加已有等级查询 native 到名称表末尾，保留原名称索引；读取函数、队伍监视和其他扩展无功能改动。

## 实际运行结果

### 修复前基线

```text
python -m pytest -q
1765 passed, 12 skipped, 113 subtests passed in 202.67s
exit_code=0
```

### 先失败、再通过的专项测试

- 背包与预设：修复前 12 failed / 17 passed；修复后连同原有技能、物品批处理、协议回归，202 passed in 27.44s。
- 群星：修复前 10 failed / 11 passed；修复后连同其他效果生命周期及直接法术回归，111 passed in 15.64s。
- 测试运行实际 C 命令分派器，仅游戏对象/native 由受控 fixture 提供；不把模拟数据误称为游戏实测。
- 背包覆盖已有/新增、容量非法、基础组件删除/重置/等级仍受保护。
- 预设覆盖上限 1/3/112/200、非法上限、缺失 native、单位/技能身份回收和普通手动设置不钳制。
- 群星覆盖新命令、地图第三值、临时/原有技能、游戏线程定时清理、再次释放、真实停止失败、对象回收与清理重试。

### 最终完整回归

```text
python -u -X utf8 -m pytest -q --tb=short
1815 passed, 12 skipped, 113 subtests passed in 218.51s (0:03:38)
exit_code=0
```

相对基线增加 50 项测试；12 项原有跳过不算通过，测试汇总保留了跳过数量。当前环境提供支持 Microsoft SEH 的 LLVM-MinGW，新增 C 回归均实际运行。

## DLL 和冻结包

```text
LLVM-MinGW: tools/war3_native_helper.c -> tools/war3_native_helper.dll
python -m PyInstaller --noconfirm --clean 魔兽争霸3重制版修改器.spec
python -X utf8 analysis/verify-fullclone-package.py
all exit_code=0
```

- EXE：x64 GUI，文件版本 1.0.19.0；大小 15470866 字节。
- EXE 主模块、国际化和运行时自检模块与当前源码一致。
- 内置持久 helper DLL 与本次重编译文件字节一致；没有旧扩展 helper DLL。
- 冻结 EXE 的离线 `--runtime-self-test` 通过，Capstone 解码及 helper 哈希校验通过。
- EXE SHA-256：`CAF3B3FA2BC74D5FE4C81EB32D5392B4D8FCCFD07F300C4094AB326DA4DC6D2C`。
- helper SHA-256：`97855F11E9A8DA552B9A86B62D2E15D9995A7A9F99A06B95A66B630DE6AC903E`。
- 详细包报告：`r18-package-verification.json`。

## 全分支自审

按照已确认计划“不启用子代理”，本轮由实施者单独做第二遍自审，没有独立审阅者。检查了相对 R17 的完整功能 diff、计划五类风险输入、错误分支、协议及产物；未发现需修复的 Critical/Important 项，未列出延期 Minor 项。自审不等同于独立评审或游戏测试。

确认：基础组件共用检查未放宽；仅 AInv 的安全添加分支开放。普通手动等级动作保持原有严格请求。群星兼容判断限定为 AEsb，其他技能原有严格清理测试仍通过。对象失效时仍保留错误而非丢弃记录继续写入。

## 实施取舍记录

1. 复用独立 R18 本地副本，不再创建第二个 worktree；原 R17 不受影响。
2. Windows 上用 apply_patch 维护同等计划账本而非 Bash-only 记账脚本；代价是记账自动化较少。
3. 遵守确认计划的不启用子代理约束，改为全分支自审；代价是没有独立的第二位审阅者。
4. 把已有 `BlzGetAbilityIntegerField` 追加到同步名称表，profile 签名和哈希不变；若该 native 在目标环境无法解析，预设会明确失败，不继续越界设置。
5. Task 2 与打包任务共用同一最终全套回归作为验收门槛；没有再修改功能源码。若后续改动功能代码须重跑。
6. 按确认的独立本地交付保留 R18 分支和源码，不合并、不推送、不发布到 GitHub；后续发布需要另行指示。

## 未完成的真实地图验收

此次没有通过实际游戏操作验证 R18 四项效果。原游戏日志只是定位证据，不能当作新版本已通过验收。请先存档并重启游戏，避免常驻的旧 helper/失败 token 干扰；按照 `R18_ELEPHANT_REPAIR_NOTES.md` 逐项检查技能/物品/群星伤害和连续释放。
