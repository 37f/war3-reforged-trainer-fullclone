# v1.0.19 FullClone R16 迁移审计

审计日期：2026-09-24（Asia/Shanghai）

## 来源与边界

| 项目 | 值 |
| --- | --- |
| 作者精确源码 | `4124cd582ed624eeb85d665484755fa8cae65697` |
| 作者应用版本 | `1.0.19` |
| 作者原 helper 协议 | `69` |
| 作者原 helper DLL SHA-256 | `6161315B505F454476F7D346391EA976F06E3D02E1C15C803DAA9923C4F49DCD` |
| FullClone helper 协议 | `73` |
| 目标游戏版本 | `Warcraft III 2.0.4.23745` |
| 输出形态 | 单一 FullClone EXE；无备用读取版 |

本迁移从作者精确源码建立隔离分支，没有用通用 1.0.19 ZIP 覆盖主文件，也没有把 v1.0.16/v1.0.18 扩展源码整文件覆盖到新版本。作者的玩家资源、28 玩家槽、选择快照、绑定身份、native 失败日志和持久 helper 路径均保留。

明确排除：选中玩家的建造/研究/造兵/建筑升级“每秒约推进 20 秒”；单位显示名称和英雄专有名称修改。

## 持久 helper 扩展操作号

| 操作号 | 名称 |
| --- | --- |
| 300 | `EXT_VALIDATE_PLAYER_TARGET` |
| 301 | `EXT_SET_UNIT_OWNER_PLAYER` |
| 302 | `EXT_CREATE_UNIT_PLAYER` |
| 303 | `EXT_CLONE_SELECTED_WITH_OWNER` |
| 304 | `EXT_SHARE_SELECTED_OWNER_CONTROL` |
| 305 | `EXT_REVIVE_SELECTED_OWNER_HEROES` |
| 306 | `EXT_FILL_UNIT_VITALS` |
| 307 | `EXT_SET_SELECTED_OWNER_TEAM` |
| 308 | `EXT_RESTORE_SELECTED_OWNER_TEAM` |
| 309 | `EXT_SET_UNIT_COLOR` |
| 310 | `EXT_SET_SELECTED_OWNER_COLOR` |
| 311 | `EXT_REPLACE_UNIT` |
| 312 | `EXT_CAST_INFERNAL` |
| 313 | `EXT_ADD_HERO_ATTRIBUTES` |
| 314 | `EXT_GOLD_MINE` |
| 315 | `EXT_LOCAL_VICTORY` |

操作号 316～320 保留但未实现。作者既有操作号未重排，旧扩展与作者 `121` 的冲突不再存在。

## 迁移功能

- 玩家 1～24、中立敌对、中立被动目标；单位转让、选中玩家增援。
- 面板复制归属开关；复制、大量复制、`Ctrl+B` 和呼叫增援统一路由。
- 共享控制切换、首次原队伍快照、多次队伍切换、原关系恢复、中立外交模板。
- 单位显示颜色和玩家颜色。
- 替换单位事务、选中玩家阵亡英雄复活、生命/魔法全满、碰撞切换。
- 英雄等级每次 +1、永久三围每次各 +2、自定义模式的灰色可读禁用输入框。
- 金矿剩余黄金、玩家直接胜利、R12 完整临时施法载体事务在鼠标位置释放 `AUin` 地狱火。
- R15 已完整移除实机无效的游戏速度功能及其持久 native 依赖。
- R16 修复批量复制的 `preserve_owner` 参数不匹配，将归属选择传递到每次作者复制事务；helper 与协议 `73` 未变。
- 修复英雄升级布尔返回值高位噪声、默认大量复制原归属路由。
- R12 已发布快捷键、中文/英文界面和无效目标静默规则均保留。

## 变更文件

- `war3_reforged_trainer.py`
- `war3_ui_i18n.py`
- `tools/war3_native_helper.c`
- `tools/war3_native_helper.dll`
- `魔兽争霸3重制版修改器.spec`
- `test_fullclone_protocol.py`
- `test_fullclone_owner_routing.py`
- `test_fullclone_player_relations.py`
- `test_fullclone_unit_transactions.py`
- `test_fullclone_special_actions.py`
- `test_fullclone_ui_hotkeys.py`
- `analysis/verify-fullclone-package.py`
- 本使用说明和审计文件。

## Helper 身份

| 文件 | SHA-256 |
| --- | --- |
| `tools/war3_native_helper.c` | `48401D48B97CEE41A073EECC008CDE0A111B84468B92BB4F18FB4F2D0ADFD11A` |
| `tools/war3_native_helper.dll` | `40D9EC350CF049666DABB7197CAE50919C2552FE8641AF07265FBBCE3B0A649F` |

DLL 使用 LLVM-MinGW Clang、目标 x86-64 Windows、`-fms-extensions -fseh-exceptions -shared -O2 -s` 从上述 C 源码重新编译。

## 自动化验证

- 最终发布树完整源码/native 回归：`1747 passed, 12 skipped, 113 subtests passed in 224.52s`；完整摘要记录在 `analysis/fullclone-regression.txt`。
- 包验证器将确认：应用版本 `1.0.19`、协议 `73`、操作号 300～315、冻结源码身份、唯一持久 helper、无旧 helper、PE x64 GUI/文件版本、离线 frozen 自检和 helper 哈希。

## 游戏速度功能移除依据

在 Warcraft III `2.0.4.23745`、PID `41784` 的地图中进行过可逆探测：原始速度档位为 `2`，`MAP_LOCK_SPEED` 初始读回为 `1`；尝试解除后仍读回 `1`，随后请求档位 `4` 仍读回 `2`。用户再次实测确认速度功能无效，因此 R15 删除界面入口、Python 方法、helper 操作号和专用持久 native 名称，不保留不可用功能。

## 构建包离线验证

构建产物：`War3ReforgedTrainer-v1.0.19-FullClone-R16.exe`

当前构建审计结果：

- EXE 大小：`15465014` 字节。
- EXE SHA-256：`7D5D095C0BE48A87BEB7503CBDC38F21EC8F34D5721EE5EE5B2195FD260B930F`。
- 冻结包内 Python 主模块、`war3_ui_i18n`、`war3_runtime_check` 与当前源码语义一致。
- 包内 `tools/war3_native_helper.dll` 与协议 73 重编译 DLL 完全一致。
- 包内其他 `*helper.dll`：无。
- 离线 `--runtime-self-test`：`ok=true`、`frozen=true`；Capstone 指令边界检查通过；未连接游戏。

最终发布目录仍以 `SHA256SUMS.txt` 和包验证器输出为准。

## 未声称的验证

本审计没有把自动化测试、DLL 编译或离线 frozen 自检描述为游戏内验证。以下项目仍需要用户在 Warcraft III 2.0.4.23745 的实际地图中复核：

- 普通玩家与中立玩家的控制、队伍切换和原关系恢复；
- 各类自定义地图中的复制字段完整性、替换事务和地图脚本覆盖；
- `AUin` 陨石动画、眩晕与召唤物归属；
- 复活位置、直接胜利、自定义战役结束流程；
- 全局快捷键与用户本机其他程序的冲突情况。
