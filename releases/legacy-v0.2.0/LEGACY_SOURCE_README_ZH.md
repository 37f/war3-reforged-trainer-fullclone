# Warcraft III Legacy Trainer v0.2.0-Test

独立适配本机 Warcraft III Legacy **1.29.2.9231 x86**，在v0.1.0基础上增加复制单位、大量复制、归属选择、替换单位。第一版和Reforged 3.0项目各自保留。

使用步骤、快捷键与边界见[使用说明](使用说明.md)。Windows x64外壳内含独立x86助手。游戏文件、接口签名及进程身份必须匹配，不能跨补丁套用地址。

- `ui.py`：三页白色Tk界面、串行工作队列、游戏前台按键边沿。
- `legacy_backend.py`：精确路径/EXE身份、快照、请求与边界校验、部分操作保护。
- `legacy_protocol.h`、`legacy_core.c`：基础资源/英雄/补满功能，原操作号0～5保留。
- `legacy_clone.c`：新复制/替换核心；最终归属直接创建、技能与物品读回、替换最后移除原单位。
- `legacy_bridge32.c`、`legacy_host32.c`、`guard32.h`：目标消息线程调度与x86异常保护。
- `profile.json`、`profile_native.h`、`extract_profile.py`：由用户提供的精确PE只读提取并核对接口/技能链布局；属性修改调用本版native。
- `core_fixture.c`、`clone_fixture.c`、`guard_fixture.c`、`test_legacy.py`：独立测试，8项Python测试、361项基础断言、117项复制断言。
- `build.py`：编译、测试、冻结及内嵌源码/组件逐项核对。
- `legacy_test_support.h`、`live_v2_check.py`、`live_v2_acceptance.py`：本次授权测试地图工具，会修改测试对象。仅单独定义LEGACY_TEST_ONLY的测试DLL有专用命令，**正式EXE不含该入口**。
- `VERIFICATION.json`、`evidence/`：验证边界和结果；失败记录不算通过。

没有打包原游戏、地图或存档。换图、读档后重新连接。不安装服务、不改注册表。复制不迁移任意地图脚本变量、触发器或旧单位引用，不承诺跨地图的无损复制。
