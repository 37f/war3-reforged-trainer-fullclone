# R19.2 未分配普通队伍监视兼容：验证记录

2026-10-23，基于 R19.1 提交 `0f8578f3113dd88a16dd330302a76bda58f48d23`。

## 根因与改动范围

用户当前战役选中的 `nkot` 单位，身份操作 136 成功，所属玩家内部编号 6（玩家 7），原生普通队伍值为 -1。旧监视查询在读取名字前用 0～63 范围拒绝了该状态，因而返回错误 13。

生产功能差异仅三处：

1. C：在现有请求校验之后，仅操作 317、合法 owner_id 且 team=-1 时返回 `result=0xffffffff`、所属玩家与零个 peer 快照；后续仍执行原名字读取及身份/owner/id/team 复核。
2. Python：仅 named query 解码该 unsigned sentinel；拒绝该状态附带非空 peer 数据；不使用、也不覆盖缓存恢复快照；保留最后的选择变化检查。
3. 显示：在普通队伍编号换算前显示“未分配普通队伍（原始值 -1）”，并加英文翻译。中立名称提示规则不变。

旧操作 316、全部修改/换队/恢复函数、profile、native 签名/操作号及协议布局均未改动。协议仍为 76，持久 helper 已重新编译，旧 helper 不可作为新版验收依据。新增 EXE 独立命名 R19.2，保留 R19.1。

## 自动化与独立审阅

- 基线：现有名字、队伍和包身份测试 `68 passed in 17.71s`。
- RED：未分配/无效 wire 新测试 `9 failed, 11 passed, 49 deselected in 5.46s`，含实际 C dispatcher `(3,13,0)` 与错误 Team 0 显示。
- GREEN：名字、队伍、玩家关系、协议回归 `123 passed in 30.32s`。
- 独立包名测试先因仍指向 R19.1 失败，再修改 spec/verifier 指向 R19.2。
- 最终完整回归：`1890 passed, 12 skipped, 113 subtests passed in 242.30s`，退出0；12项既有跳过仍是跳过。
- 一次独立只读源码审阅：无 Critical / Important / Minor；明确未将源代码审阅冒充打包或游戏内验收。
- `git diff --check` 通过。

C 测试实际编译并执行生产查询/dispatcher，验证 -1 成功、名字不可用仍保留归属、不调用队伍/联盟 setter、316/307/308 仍拒绝 -1、畸形请求和损坏身份仍失败。Python/Tk 回归覆盖中文/英文、未分配显示、缓存恢复记录保持、非空 peer 拒绝、选择取消/变化及原正常玩家/中立显示。

## 冻结包验证

LLVM-MinGW 20261020 / clang 23.1.4，使用原有 SEH 编译方式：`-fms-extensions -fseh-exceptions -shared -O2 -Wno-microsoft-goto`。PyInstaller 6.22.2 构建独立 R19.2，未覆盖旧 EXE。

`python analysis/verify-fullclone-package.py` 退出0：x64 GUI、文件版本1.0.19.0、协议76，内嵌主模块/国际化/自检源码一致，内嵌 helper 与工作文件字节一致，无旧扩展 DLL，离线冻结运行时自检通过。

- 新 EXE：15,490,765 字节；SHA-256 `7776320F1FF27E8A05171AF6E29DCF50ADEF2B97A93864277AF383A373B54BF1`。
- 新 helper：SHA-256 `9EDB76E2BA02C6A2F5BFD502E314E9A8BD8E5B6F45176F054B928FE4C0397E1C`。
- 保留的 R19.1 EXE：SHA-256 `2564613BED6A8071C1BFFF9B0D0C4A539E8C4A3D0A9DC5B06505EA187FCA2F3C`，与原交付一致。
- 包核对报告：`r19.2-package-verification.json`。

EXE 已独立复制到游戏目录，复制后 SHA-256 一致。源码 ZIP 和交付文件的 CRC/哈希由外部交付报告另外记录，避免把自动化结果当成游戏画面验收。

## 当前游戏读回与界面验收

用户回复“已重开”后，首次尝试仍检测到旧 PID 17824、21:47:52 启动的游戏进程，查询未得到稳定选中单位快照，尚未取得实际 -1 状态成功读回。该次尝试不能算通过，已请用户完整退出主程序并重新进入战役后再核对。

用户随后完整退出主程序并重新进入战役，确认新 PID 为 30088、启动时间 22:50:39。2026-10-23 22:57:52～22:57:53（+08:00），R19.2 源码及已校验新 helper 连续三次执行现有 317 监视查询，均成功返回：

```text
player_slot=6, native_team=-1, assigned_team=None
player_name=None, player_name_error=1168
玩家 7（名称暂无法读取）：未分配普通队伍（原始值 -1）
```

名字不可用在此是独立的可选名字状态，不是原来的整个查询错误；玩家编号和 -1 队伍均正常返回。没有执行换队、控制、归属或单位属性 setter。本次实际读回记录位于交付目录的 `verification-evidence/live-monitor-readback.json`。

随后用户打开 R19.2 正式 EXE、连接当前游戏并核对监视，直接回复“显示正常，无原错误”。因此当前战役/当前单位的监视读回与正式界面已通过，不能外推为所有战役地图和其他功能都重新实测。本次没有上传 GitHub。
