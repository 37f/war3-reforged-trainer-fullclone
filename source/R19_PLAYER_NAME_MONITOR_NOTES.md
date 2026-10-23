# R19：在原队伍监视中显示实际玩家名字

基于已发布 R18 提交 `75b8a868f435ef198c5a8394378f5fd63f6d3279`。保留 R18 原功能，只扩展原监视栏；不包含改单位名/英雄名功能，不重加游戏速度或每秒推进建造等已撤销功能。

## 使用

先保存进度，关闭旧修改器、退出并重开游戏，再运行 `War3ReforgedTrainer-v1.0.19-FullClone-R19.exe` 并连接。选中单位后，在“大象功能 → 功能面板 → 目标单位”点击原“读取队伍”，或勾选原“监视队伍（每秒刷新）”。

显示形式：`玩家 5（石塔赛特斯）：队伍 2`。这是本次游戏真实中文读回示例；不保证每张地图都有同名玩家。中立槽位保留原提示。名字随单位所属玩家读取，不使用目标玩家下拉框，也不会修改目标队伍下拉框。

- 仍只有一个后台读取任务，共用原操作锁。
- 读取名字和队伍是同一次、同一所属玩家的已验证事务。
- 无选择、断开、换进程或旧后台结果晚到时，不沿用旧名字。
- 名字不可用时，显示“名称暂无法读取”并保留本次有效队伍，不每秒弹错误窗口。
- 中文玩家名字在英文界面保持原样；仅周围标签翻译。
- 这项监视不修改名字、单位归属、队伍、外交、控制权或原队伍快照。

## 实现与兼容边界

Python/C 协议从 75 同步到 76；原 300～316 操作号保持不变，旧队伍查询 316 的默认入口/数据语义不变。仅 GUI 请求新只读查询 317。未修改 native profile、签名/哈希或必需 native 名称列表。

`GetPlayerName` 是 JASS 字符串返回接口，不能当作任意 C 字符串指针。名字读取通过原 profile 按需校验其代码以及它与 `GetPlayerId` 共用的玩家对象解析器，再读取已经存在的名字存储；不执行会初始化默认名的 getter、不调用 JASS 字符串驻留路径。依据和精确代码指纹见 `analysis/R19_PLAYER_NAME_ABI.md`。

最多复制 512 字节并要求完整 UTF-8；空名、超长、非法编码和不可读指针均拒绝，不切断中文、不展示随机内存。版本/布局或名字绑定不符合时只降级为名字不可用，不放宽其他 native 校验。

## 验证范围

- 新名字 C 读取器、真实 C 分派器和真实 Tk 控件回归覆盖长度/编码/失效上下文/语言切换及监视开关。
- 本机已对用户重开后的游戏实际查询，连续三次返回 `玩家 5（石塔赛特斯）：队伍 2`，名字错误码 0。
- 该游戏读回尚未由用户独立核对；不声称所有地图、中立槽位或最终冻结 EXE 界面均已实测。R18 其他功能也不能因名字读取成功而视为完成游戏验收。
- 包校验验证 EXE 内源码、helper DLL、版本与离线冻结启动；它不会打开游戏或修改游戏数据。

## 从源码重建

Python 3.12.10、Capstone 5.0.7、PyInstaller 6.22.2、pytest/pefile；C 夹具要求支持 Microsoft SEH 的 LLVM-MinGW clang。

```powershell
clang -fms-extensions -fseh-exceptions -shared -O2 -s -Wno-microsoft-goto tools/war3_native_helper.c -o tools/war3_native_helper.dll -luser32 -lkernel32
python -m pytest -q
python -m PyInstaller --noconfirm --clean '魔兽争霸3重制版修改器.spec'
python analysis/verify-fullclone-package.py
```

Windows 消息循环夹具使用 `wmain`，当前 LLVM-MinGW 环境需在可执行程序链接时提供 `-municode`（DLL 不加）。未找到编译器导致的跳过不能算 C 测试通过。详细结果和构建身份记录见 `analysis/R19_VERIFICATION.md`。
