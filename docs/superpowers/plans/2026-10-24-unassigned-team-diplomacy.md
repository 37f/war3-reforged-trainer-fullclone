# R19.3 Unassigned Team Diplomacy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. User selected inline execution on 2026-10-24. Tasks 1–3 and Task 4 offline delivery are complete; actual saved-game acceptance remains pending. Final complete regression: 1947 passed, 12 skipped, 113 subtests passed. Keep the dedicated local branch; do not merge, push, or publish under this authorization.

**Goal:** 为原队伍为 `-1` 的普通玩家提供可验证、可还原的外交模板，不更改其原生队伍。

**Architecture:** 保留已有操作号，在 307/308 内增加隔离的未分配队伍分支，由一个小 C 头文件承载扩展快照编码、联盟事务及回读。Python 保存第一次快照，317 提供该分支的完整只读联盟回读；普通队伍路径和 legacy 316 的语义不变。双端协议升级为 77，拒绝旧 helper 混装，独立交付 R19.3-Test。

**Tech Stack:** 现有 Python 3.12、Tkinter、pytest、Microsoft-SEH-capable LLVM-MinGW C、PyInstaller；不增加依赖。

**Spec:** `docs/superpowers/specs/2026-10-24-unassigned-team-diplomacy-design.md`，用户于 2026-10-24 批准。

## Global Constraints

- 原生队伍 `-1` 从始至终保留，不调用 `SetPlayerTeam`，不强写队伍字段或队伍成员表。
- 只处理既有六类联盟关系（类型 0～5），不改变单位归属，不额外修改共享控制权。
- 保留第一次记录；新涉及玩家的原关系在首次涉及时记录；恢复失败保留快照。
- 非负原队伍、现有中立槽位、复制及其他功能不作顺带重构；不改 native 指纹、ABI 或读取模式。
- 不覆盖 R19.2、地图或存档；离线验证不冒充真机验收；本次不自动上传 GitHub。

## Review Focus

- 同一进程中选中单位归属变化或旧快照 owner 不同：写联盟之前拒绝，不覆盖首次记录。（Task 2）
- 其他玩家的原生队伍同样是 -1：快照显式区分 -1、0、63；重复/自指/非法 peer 拒绝。（Task 1、2）
- 地图触发器改变联盟或原生队伍：不显示旧成功状态，恢复拒绝失配且保留快照。（Task 2、3）
- 部分 setter 失败、异常或输出分配失败：不伪报成功；能回滚则核对完整回滚，失败则明确报告。（Task 2）
- 旧 helper、同进程残留 DLL、进程切换：拒绝协议/身份不匹配，不复用旧快照，不覆盖旧 EXE。（Task 1、4）

## Task 1: Versioned, Lossless Unassigned Peer Snapshot

**Files:** create `source/tools/war3_native_unassigned_team.h`, `source/test_fullclone_unassigned_team.py`; modify protocol constants in `source/tools/war3_native_helper.c`, `source/war3_reforged_trainer.py`, and `source/test_fullclone_protocol.py`.

**Interfaces:** Keep fixed header/op layouts and operations 300–317 unchanged; C/Python protocol becomes 77. New C helpers `war3_team_pack_unassigned_peer(const War3TeamPeerSnapshot *) -> uint64_t` and `war3_team_unpack_unassigned_peer(uint64_t, War3TeamPeerSnapshot *) -> int` use existing low 36 bits plus bit 36 as a -1 tag. When tagged, the six-bit team field must be zero; otherwise 0–63 retains its existing meaning. Bits above 36 are invalid. Existing C pack/unpack stay unchanged for legacy paths. Python `_team_relationships_by_player`, base/assigned masks and merge logic preserve the tag with the original portion, not the assigned portion.

- [x] Add RED Python/compiled-C tests: `test_unassigned_peer_roundtrip_distinguishes_minus_one_zero_and_63`, `test_peer_tag_rejects_contradictory_or_high_bits`, `test_merge_keeps_first_peer_tag_and_original_masks`; assert decoded teams `(-1, 0, 63)` remain distinct and duplicate peers are rejected.
- [x] Add protocol test asserting packed version `77`, rejection of versions `75/76`, unchanged author opcode hashes and unchanged extension opcode map.
- [x] Run `python -m pytest test_fullclone_unassigned_team.py test_fullclone_protocol.py -q` from `source`; save expected RED failures.
- [x] Implement only codec/mask/protocol changes and attach the new header at a point where its required types/helpers are declared. Keep legacy 316/307/308 behavior unchanged at this step.
- [x] Re-run both files to GREEN, then commit the codec and tests as one local commit.

## Task 2: Bound Unassigned Diplomacy Transaction and First Snapshot

**Files:** modify `source/tools/war3_native_unassigned_team.h`, narrow delegation/validation in `source/tools/war3_native_helper.c`, team controller/parser in `source/war3_reforged_trainer.py`; extend `source/test_fullclone_unassigned_team.py`, `source/test_fullclone_player_relations.py`.

**Interfaces:** `war3_ext_unassigned_team(NativeCommand *, NativeOp *, uint32_t, const uint64_t *, uint32_t, uint64_t **, uint32_t *) -> DWORD`; preserve public Python `set_selected_owner_team(team_index)` and `restore_selected_owner_team(snapshot=None)` return tuple shapes. Extend 307's request binding to optional `handler=expected_owner`, `arg0=expected_slot`, `arg1=0`, using the candidate's attached immutable `native_snapshot.owner/owner_id`. Check this binding before any setter; old zero-binding requests retain old nonnegative behavior. The -1 branch requires a bound ordinary owner (index 0–23).

For 308/-1 only: `rawcode=0xffffffff`, `handler=assigned_template`, `arg0=expected_slot`, `arg1=expected_owner`, with existing maximum 28 peer extras. Other 308 requests retain existing field meanings. New join response keeps `result=assigned_template`, metadata's original-team byte `0xff` plus virtual bit; decode as -1 only for this valid combination. Restore response `result=0xffffffff`, metadata previous-team byte = last assigned template. Extended peer codec is confined to the new branch; legacy restores do not accept its tagged peers.

- [x] Add RED compiled-C tests for join to ordinary targets 0/1/11 and neutral targets 12/13, repeated switches and restore: native team remains -1; `SetPlayerTeam` count is zero; only alliance types 0–5 are written; all original forward/reverse masks match after restoration. Run through actual command dispatcher with guard 136 as well as the helper fixture.
- [x] Add preflight tests for wrong expected owner/slot, non--1 owner, recycled unit, duplicate/self/invalid peer, invalid target and allocation failure; assert zero writes. Include a peer whose team is -1 and unchanged ordinary/neutral legacy regression cases.
- [x] Add failure injection at first/middle/last setter, failed readback, SEH, and failed rollback. Track touched peers and prove return-to-pre-operation relationships when possible. On failure encode `result=(0x554e4153ULL << 32) | phase` (phases 1 preflight, 2 apply, 3 verify, 4 rollback), put rollback error in `reserved`, and add narrowly gated parser details `team_phase`/`team_rollback_error`; do not label it a clone phase.
- [x] Add Python tests asserting first `original_team == -1` survives all switches, expected owner is pinned from the candidate's snapshot, mismatched old snapshots reject before transport, restore failure retains the exact snapshot, and only verified full restoration removes it. Use `(process_id, player_slot)` existing keys and require matching owner handles.
- [x] Run focused tests RED, then implement new transaction: resolve validated native getters/setters, preallocate response storage and validate all input/peers before writes, reuse existing template/reference and peer-selection rules, verify identities/native -1/relations, apply with per-step checks, and rollback the touched relationships on failure. Never delegate this branch to the native team setter. Native registry signatures and existing neutral repair guards remain unchanged.
- [x] Implement Python binding, sentinel decoding, safe merge and restore validation. Never overwrite a previous owner's first snapshot; do not add a separate timer or background setter.
- [x] Run `python -m pytest test_fullclone_unassigned_team.py test_fullclone_player_relations.py test_fullclone_protocol.py -q` to GREEN, then commit transaction/controller/tests.

## Task 3: Honest Read-only Monitor and UI Feedback

**Files:** modify `source/tools/war3_native_unassigned_team.h`, status-317 delegation in `source/tools/war3_native_helper.c`, `source/war3_reforged_trainer.py`, `source/war3_ui_i18n.py`; extend `source/test_fullclone_unassigned_team.py`, `source/test_fullclone_player_name_monitor.py`, `source/test_fullclone_team_monitor.py`, `source/test_fullclone_ui_hotkeys.py`.

**Interfaces:** `war3_query_unassigned_team_peers(NativeCommand *, NativeOp *, uint32_t, uint64_t **, uint32_t *) -> DWORD` returns -1 as uint32 `0xffffffff`, bounded extended peer records and existing owner/count metadata. Existing name wrapper appends its bounded payload after those records and keeps final identity checks. Legacy 316 remains unchanged. `query_selected_owner_team(include_player_name=True) -> PlayerTeamStatus` may verify an existing virtual -1 snapshot, but never create/overwrite/delete it.

- [x] Add RED tests: matching native -1 plus complete assigned masks shows `队伍 2（外交模板）；原生队伍编号 -1`; mismatched masks show unassigned plus `关系已变化`; absent snapshot still shows `未分配普通队伍（原始值 -1）`; another process/owner is never verified. Verify ordinary/neutral labels, missing names, bounded name payloads and stale selection behavior in Chinese/English.
- [x] Add compiled query test proving zero setter calls with -1 peer extras; keep legacy 316 rejecting -1. Add real Tk harness checks that button/shortcut feedback never says `队伍 0` or claims true team mutation/restoration, including neutral target labels and first-original display after repeated switches.
- [x] Run those tests RED, then replace only 317/-1's empty-peer shortcut with the bounded reader. Update Python matching/formatting precedence and action messages, including the original -1 display; do not change existing monitor timing or other hotkeys.
- [x] Run `python -m pytest test_fullclone_unassigned_team.py test_fullclone_player_name_monitor.py test_fullclone_team_monitor.py test_fullclone_ui_hotkeys.py -q` to GREEN; commit monitor/UI/tests.

## Task 4: Regression, Independent R19.3-Test Package and Saved-game Acceptance

**Files:** modify `source/魔兽争霸3重制版修改器.spec`, `source/analysis/verify-fullclone-package.py`, `source/test_fullclone_package_identity.py`, `source/V19_FULL_USAGE_GUIDE_ZH.md`; create `source/R19_3_UNASSIGNED_DIPLOMACY_NOTES.md`, `source/analysis/R19_3_VERIFICATION.md`; generate new delivery under `outputs/v1.0.19-FullClone-R19.3-Test` and separately named game-folder EXE/source backup.

**Interfaces:** package name `War3ReforgedTrainer-v1.0.19-FullClone-R19.3-Test.exe`, source archive `war3-reforged-trainer-v1.0.19-fullclone-r19.3-test-source.zip`. Author `APP_VERSION` remains `1.0.19`, protocol 77 is checked in source, DLL and frozen startup. No upload, merge or release without a new request.

- [x] Inherit existing isolated checkout/toolchain; read `using-git-worktrees` and detect git/common-dir/branch before execution. Preserve clean published R19.2 source/artifacts; use a dedicated new branch for implementation. Set task shell `PATH` to the existing `.codex-tools/r19-bin` SEH wrapper and `PYTHONPATH` to `.codex-tools/capstone-local`; use existing Python 3.12 and no dependency installs.
- [x] Run the complete `python -m pytest -q` suite from `source`, retain exit code/counts/skips/subtests/logs, and investigate every regression. A skip is not native coverage. Require a fresh whole-change review after implementation and add regression tests for material findings.
- [x] Back up the existing helper DLL, rebuild with existing SEH compiler flags, build the separately named PyInstaller EXE, run frozen offline self-test/package verifier, and verify embedded source/modules/DLL, source ZIP CRC/content, delivery hashes and unchanged R19.2 hashes. No package pass may be claimed before these commands succeed.
- [x] Document exact UI semantics, map-trigger limitation, first-snapshot lifetime, process-restart requirement and rollback-failure recovery. Commit verified code/docs locally; do not replace old delivered files or publish.
- [ ] Request a fresh saved-game test: close other trainers, completely restart game to remove protocol-76 helper, load the original campaign, select player 7. With user authorization verify `-1 → 模拟队伍 2 → 模拟队伍 3 → 恢复` and a neutral template; record native -1 throughout, actual bilateral relations, selected owner and user-visible effects. If a setter/restore fails, stop, report readback and load the saved game as needed; no raw team-write fallback.
- [x] If the real-game test is unavailable, deliver explicitly as offline-verified/test pending. Do not call it accepted or publish it automatically.

## Plan Self-review

All approved spec sections map to Tasks 1–4. The five Review Focus conditions have explicit tests above. Fixed transport sizes and existing operation numbers remain intact; the version bump and tagged peer encoding prevent silent -1→63 reinterpretation. This plan adds no unrelated functions or dependency work. Actual in-game alliance behavior remains an acceptance gate, not an assumption.
