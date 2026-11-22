# 魔兽争霸 III 重制版修改器 v2.2.6 FullClone R34

本版以原作者 v2.2.6 源码 `e6051f7d4fd8` 为底，迁入已发布的 v2.2.5 FullClone R33 扩展。适用于 Windows x64 的《魔兽争霸 III》重制版 3.0 系列，具体可用功能取决于游戏构建和地图。

## v2.2.6 原版更新

- 套装方案支持保存和恢复装备、天赋和 30 格扩展背包，也可导入、导出方案。
- 同层天赋效果按原作者 v2.2.6 规则合并，遇到冲突时保留已生效的天赋并提示。
- 全局快捷键、单项勾选、常用输入、栏目顺序及目录筛选可保存。三套界面均可访问作者网站入口。

## FullClone 扩展

- **大象功能**。复制归属、阵型大量复制、替换单位、全军补满生命魔法和冻结／恢复、补给包、鼠标位置技能及地面物品聚集。两个 ID 目录的「生成单位」服从大象面板归属选择，`Ctrl+A` 固定复制给自己。
- **队伍与玩家**。切换游戏中名字和地图配置名、监视玩家与队伍、查看或拖放外交模板、恢复单个或全部玩家原队伍。单位转交记录支持恢复选中单位或当前地图内全部已记录单位的原归属。按住玩家卡片时用鼠标滚轮上下移动名单。
- **任务与条件**。手动检测当前地图，读取主支线任务说明和可解析的完成／失败条件。勾选「触发位置」显示可定位地点，点击对应位置可跳转本地视角。能唯一匹配的 JASS 任务显示实时状态，Lua 提供静态解析，实时状态尚未适配。
- **界面**。支持现代深色、白色标签页和 1.0.19 旧式布局。扩展界面可切换中文或英文，地图文字与玩家名称取自游戏或地图数据。

更早的累计改动与快捷键见 [R33 更新记录](R33_CHANGELOG_ZH.md)。

## 从源码构建

需要 Windows x64、Python 3.12 和 Node.js 22。源码包附已构建的前端和本版桥接组件。运行以下命令前，把第一条 `--from-file` 的值换成作者 v2.2.6 原版 EXE 的实际路径。如修改了前端源码，先运行 `npm ci --prefix frontend` 和 `npm run build --prefix frontend` 更新前端产物。

```powershell
python -m pip install -r requirements-build.txt
python tools/prepare_build_baseline_226.py --from-file 'War3ReforgedTrainer-v2.2.6-4468538AF6A7.exe'
python tools/build_fullclone_release_226.py --bridge-image tools/war3_bridge_24268.dll
python tools/build_fullclone_release_226.py --verify-only
```

构建产物 `War3ReforgedTrainer-v2.2.6-FullClone-R34.exe` 位于 `dist-2.2.6-fullclone-r34-verified`。
