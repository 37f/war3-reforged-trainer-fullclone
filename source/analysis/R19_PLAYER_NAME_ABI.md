# R19 玩家名字读取 ABI 证据

## 目标身份及采集边界

- 2026-10-23，本机游戏文件版本 `2.0.4.23745`。
- 文件：`E:\Games\Warcraft III 2.0.4.23745\_retail_\x86_64\Warcraft III.exe`，48526544 字节。
- 文件 SHA-256：`682c12552ca05e43c5fed2340ea132d3b06fe068e676db7d1f5623d8d4633229`。
- 磁盘及本次运行 PE 时间戳 `0x69e54471`，SizeOfImage `0xdd20000`；与原 profile 一致。
- 工具：`analysis/probe-player-name-abi.py`。仅以 `PROCESS_VM_READ | PROCESS_QUERY_INFORMATION` 读运行中的代码，不创建 trainer、注入 DLL、下断点、调用游戏函数或写入进程。主模块头在运行时不能仅依赖 MEM_IMAGE 类型筛选，因此用操作系统报告的主模块地址，并重新核对 PE 身份。
- REA doctor 报告旧注册及无 native engine；没有修复客户端配置。使用本地 PE/Capstone 的有界代码证据，不声称做过反编译器或原生名字接口执行验证。

## 实际观测

`GetPlayerName` 的 profile 签名是 `(Hplayer;)S`，不是已证明的 `char *` 返回值。其 RVA `0xc52f40` 首 64 字节 FNV-1a 为 `09e408dac8b22767`，与原 profile 一致；`GetPlayerId` RVA `0xc52ef0` 的 hash 为 `c76e6cf4beaf31a0`，同样匹配。

运行代码显示：

1. `GetPlayerName+4` 调用 player resolver（RVA `0xa0ee90`）；输入为原 player handle，RAX 返回玩家对象。`GetPlayerId+4` 调用同一 resolver 后使用对象的虚表，独立证实此返回值是对象，而非字符串。
2. `GetPlayerName+0x18` 调用玩家名字 getter（RVA `0x9c3c60`，首64字节 FNV `b1a49ce378624016`）；调用前 RCX=玩家对象、DL=1。
3. getter 的 `+0x24` 是 `add rcx,0x70`，`+0x28` 调用字符串 accessor（RVA `0x313000`）。该 accessor 的完整15字节主体为 `48 8b 41 10 48 85 c0 74 05 48 8b 40 38 c3 c3`，只读取 `[string+0x10]`，非空时再读取 `[storage+0x38]`。
4. 名字 getter 中还有“名字为空则构造默认名字并写回”的路径；不能把这个 getter 直接当作纯读取调用。
5. `GetPlayerName` 随后跳转到独立 JASS 字符串转换/驻留路径（RVA `0xc39da0`），其中包含保护代码。本次没有把其返回值假设成 C 字符串地址，也不需要执行这条路径。

## 因而采用的最小只读路径

- 在原 bootstrap 的完整镜像及 native 签名/代码校验之后，按需查询原 profile 已含的 `GetPlayerName`；不把它加入所有功能必需的 bootstrap 绑定列表。
- 从校验过的 `GetPlayerName` 相对调用取得 player resolver 和名字 getter；核对 getter 首64字节 fingerprint、上述字符串 accessor 的完整主体，并确认 resolver 与原已校验 `GetPlayerId` 的首个调用相同。
- 仅调用这条已验证的 player resolver；不调用名字 getter、JASS 字符串驻留函数或任何写名字路径。
- 对经验证的玩家对象，逐段检查并只读取 `player+0x80 -> storage`、`storage+0x38 -> bytes`；有界复制最多512字节，另检查终止字节，严格验证 UTF-8。不凭文件名/堆中字符串相似度猜玩家。
- 复制后复核 player resolver、storage、data 指针及单位/所属玩家身份。空值、不可读、过长、编码异常或上下文变化均不使用旧名字。
- UTF-8 编码及真实目标名字的游戏中读回结果在功能实现后另行记录；上述反汇编只证明调用及存储路径，不声称已经验收最终界面。

## 与原功能的边界

只读操作317组合原队伍快照和名字结果；316保持原样。名字读取失败写入名字专属错误码，不破坏已成功读取的当前队伍。协议同步76，原 profile 文件、签名/哈希和必需 native 列表保持不变。C夹具及完整回归仍须实际运行，不能以本证据记录替代测试。
