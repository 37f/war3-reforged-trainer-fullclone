# R23 Quest Completion and Official Map Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically inspect the active official/custom JASS map and execute a selected, verified quest's original completion flow, including its existing rewards and continuations.

**Architecture:** Reuse the R22 snapshot/parser/analyzer and add source and execution boundaries independently. First prove exact official-resource provenance and the supported build's JASS execution/quest binding; only then enable an execution UI. Keep failed qualification explicit and perform game-side session validation and at-most-once dispatch.

**Tech Stack:** Windows x64, existing Python 3.12/Tk/pytest/PyInstaller, existing LLVM/Capstone/StormLib, persistent native helper, pinned CascLib only if verified necessary for local official resources.

**Spec:** `docs/superpowers/specs/2026-10-25-r23-quest-execution-and-sources-design.md`, approved by the user on 2026-10-25.

## Global Constraints

- Base `821e7cbf450fe15fe6382e33f29c0f53ab483553`; reuse the existing linked worktree on `codex/r23-quest-completion-sources-design`.
- Preserve R22 files, existing operations, native signatures/hashes, unit/resource readers, all old extensions and hotkeys.
- Support the verified Warcraft III 2.0.4.23745 x64 build; JASS first, explicit Lua rejection.
- Operate on the active chapter only. Never select by title similarity, manufacture prerequisite variables, patch map/save files, or silently reduce completion to a setter.
- New helper capabilities must be paired with versioned clients; allocate unused op IDs only after inspecting current constants.
- Runtime discovery is read only until the user has selected a recoverable execution test; do not change chapters or close/start the game on their behalf.
- Deliver separately named R23-Test EXE/source/Chinese guide/evidence/hashes; no automatic GitHub publication.
- Implementation stays in this session; one independent final code review after meaningful verification. No per-task implementation agent fan-out.

## Review Focus

- A localized/overridden official resource: reject ambiguous or unconfirmed effective content instead of showing a plausible installed script (Task 1/2 source tests).
- A quest setter inside an outer reward action: qualify the complete action or refuse; never claim the setter alone preserves rewards (Task 3 tests).
- Same-title quests, recreated instances and recycled handles: bind script key/type/instance and reject stale identities (Task 3/4 tests).
- RPC timeout, GUI double-click and reconnect: persist one dispatch in the helper; report unknown without retrying (Task 4/5 tests).
- Original flow sleeps or changes chapters: distinguish dispatch, observed completion and lost session; never mark all rewards verified from a native return (Task 4/5 tests).

## File Responsibilities

- Existing `source/war3_current_map_script.py`: snapshot/session/file contracts; incrementally route verified storage sources without altering the old MPQ path.
- New `source/war3_casc_source.py` if needed: bounded local CASC resource reader and storage identity. No runtime mutation or GUI access.
- New `source/war3_quest_execution.py`: immutable completion plans and conservative qualification based on the existing JASS AST/report.
- New `source/war3_native_quest.py`: typed runtime client, strictly validated proof/readback models, no Tk.
- New `source/tools/war3_native_quest.h`: build-bound JASS/quest proof and game-side query/dispatch/dedup, only after Task 1 proves the interfaces.
- Existing helper C/main trainer: narrow bridge and versioned operation additions; no unrelated rewrites.
- Existing `source/war3_quest_ui.py`: asynchronous preflight/explicit execute/result UI with current snapshot protection.
- New focused source/plan/native/client/UI tests; existing R22 tests retain their meaning.
- New R23 spec/verifier/guide; reuse the established isolated Tk regression and packaging checks.

## Task 1: Prove official provenance and JASS execution contracts

**Files:** Create `docs/r23-runtime-feasibility.md`; create operator-invoked investigation scripts under `source/analysis/` only when reusable; private process evidence under conversation `outputs/r23-investigation` (excluded from releases).

**Consumes:** `create_current_map_script_client(pid, catalog, memory_factory)`, `read_profiled_map_metadata(read, base, token)`, existing bootstrap table and active-map proof.

**Produces:** Actual supported metadata/storage identity and a build-specific, verified quest/VM/function query and JASS-thread invocation contract. Offsets, ABI, string lifetime, sleeping and dedup semantics must be evidence-backed before implementation, not invented by this plan.

- [ ] Rediscover process/build and other trainer instances. Read only active metadata for the user-provided official Orc Prologue chapter 1, “追寻幻象”. Record member, configuration, session and actual storage association.
- [ ] Inspect official local-resource support with the reverse-engineering skill and primary CascLib source. Pin source version if a new reader is necessary. Check loose files, version/locale layers and active overrides before claiming a source.
- [ ] Prove VM global/typed quest identity and function-signature binding in the exact build. Prove an eligible original completion entry and the JASS string/call-thread ABI. A listed ExecuteFunc handler alone does not satisfy this step.
- [ ] Record static versus live evidence separately, read bounds, failure conditions and unproven aspects. If either provenance or invocation is unproven, continue bounded investigation or report the concrete blocker; do not enable guessed execution.
- [ ] Commit only reusable investigation/report additions; retain private map/script/process material outside the source archive.

## Task 2: Add a verified official source provider and custom-map regression

**Files:** Create `source/war3_casc_source.py` if Task 1 requires it; modify `source/war3_current_map_script.py`; create `source/test_official_map_source.py`; extend `source/test_current_map_script.py`; add pinned dependency/license only when needed.

**Interfaces:** `CascArchive(root: Path, identity: object, deadline: float, cancelled: Callable)`, `read(member: str, max_bytes: int) -> bytes | None`, context-manager cleanup; verified provider returns the existing `ScriptSnapshot`. Exact storage-proof model is finalized from Task 1 and documented in the feasibility record.

- [ ] Add failing tests: actual member rather than a same-title file; language/WTS consistency; rejected shadow/ambiguous source; installed storage changed; cancellation/limits; old snapshot checks; unsupported Lua; missing local resource without network download.
- [ ] Run focused tests from `source`; capture failures attributable to missing behavior.
- [ ] Implement bounded local reads and immutable storage stamps; preserve original `bind_owned_source` behavior for `.w3n/.w3x/.w3m`. Do not share game-owned archive handles with a separately loaded library.
- [ ] Verify new tests plus `test_current_map_script.py`, `test_current_map_catalog.py`, `test_campaign_catalog.py` if present. Do not rename an existing test just to match this list; use collected names.
- [ ] Read actual official chapter and compare independent local resource hashes; request user-controlled chapter changes only when needed. Prove standalone custom map and existing campaign source paths without editing them.
- [ ] Commit source/provider tests and validation record.

## Task 3: Build conservative original-completion plans

**Files:** Create `source/war3_quest_execution.py`, `source/test_quest_execution.py`; only narrow changes to `war3_quest_analysis.py` if original AST/source identity is needed.

**Interfaces:** `build_completion_plan(report: QuestReport, quest_key: str, cancelled: Callable = ...) -> CompletionPlan`. Frozen plan fields: snapshot identity/token/hash, quest key/typed binding expression, entry function or none, original-chain evidence, recognized effects, qualification status and concrete rejection reasons. Plans contain no user-provided arbitrary native addresses.

- [ ] Add failing tests for a simple full completion action; setter in reward-owning caller; function-local unmet counter; event-response dependency; dynamic/unknown calls; conflicting quest aliases; same-title distinct objects; wrong function signature; no actual completion setter; multiple ambiguous complete branches; unsafe partial/repeated flow.
- [ ] Run the new tests and observe RED, retaining existing analyzer behavior.
- [ ] Implement AST-based qualification and full original-chain evidence. Keep branch/short-circuit/trigger-instance distinctions from R22. Reject incomplete qualification instead of generating arbitrary effects or prerequisite writes.
- [ ] Run new plan tests plus `test_jass.py` and `test_quest_analysis.py`; verify known R22 chapter anchors remain valid.
- [ ] Commit plan model, qualifier and tests.

## Task 4: Add typed runtime preflight and at-most-once dispatch

**Files:** Create `source/war3_native_quest.py`, `source/tools/war3_native_quest.h`, focused Python/C contract tests; narrow helper/main bridge and paired protocol update only after Task 1.

**Interfaces:** `QuestRuntimeClient.inspect(plan: CompletionPlan) -> QuestRuntimeProof`; `execute(plan: CompletionPlan, proof: QuestRuntimeProof, request_id: str) -> QuestExecutionResult`; results distinguish rejected-before-dispatch, dispatched/pending, observed-completed and unknown/session-changed. Proof binds exact connection, token, VM, function signature, source version, quest type/instance and current status.

- [ ] Add failing contract tests for stale map/VM/source/quest, wrong type/signature, uncreated/destroyed/completed/failed quest, double-click, reconnect, reused request identity, helper state loss and late response. Test timeouts after possible dispatch without automatic retry.
- [ ] Implement only Task-1-proven native/profile operations. Recheck all execution proof inside the game-thread serialized handler immediately before dispatch; persist dedup before starting the original flow. Do not accept raw script/address APIs.
- [ ] Preserve old op semantics and bootstrap validation. Use a managed JASS context with verified string lifetime; do not call bytecode as C or pass C strings as JASS strings.
- [ ] Execute focused helper/client/profile regression tests. Verify sleep/async status and map transition results. Acknowledgment is not proof of completed rewards.
- [ ] Only after explicit user test preparation, execute one selected recoverable original quest and record before/after task, reward and continuation evidence. No force retry after partial/unknown results.
- [ ] Commit helper/client/tests and exact runtime validation record.

## Task 5: Integrate explicit task execution UI

**Files:** Modify `source/war3_quest_ui.py`, `source/war3_reforged_trainer.py`, `source/war3_ui_i18n.py`; extend/create focused quest UI tests.

**Consumes:** Task 3 plan, Task 4 client/proof/results and existing source snapshot controller.

- [ ] Add failing UI/controller tests: static row not live quest, same-title selection, preflight enabling only eligible target, no execution from selection/refresh/language changes, asynchronous calls off Tk, two-second expiry, old generations, double-click and cancellation after dispatch.
- [ ] Add “检查完成入口” and “完成此任务（原流程）” with evidence/effects/refusal/result display. Non-task rows never enable execution. Keep explicit pending/unknown rather than incorrectly claiming rollback or success.
- [ ] Bind current client in a narrow main bridge; preserve old tabs and hotkeys. Add ordinary Chinese/English strings.
- [ ] Run focused UI and i18n tests in isolated Tk processes, then manual source GUI checks when the user is not operating another window.
- [ ] Commit integrated UI/tests.

## Task 6: Verify, review and deliver R23 separately

**Files:** New `source/War3ReforgedTrainer-FullClone-R23.spec`, R23 package verifier/selfcheck additions, R23 Chinese guide and verification document.

- [ ] Run relevant and full regression using R22's documented source cwd/toolchain and disjoint Tk isolation. Keep actual passed/skipped/subtest counts and unexplained failures visible.
- [ ] Obtain one independent final whole-branch review; fix important findings with meaningful regression tests, rerunning impacted checks.
- [ ] Build a separate R23-Test frozen EXE; verify embedded modules/helper/dependencies/licenses, offline startup and feature capabilities. Do not imply frozen offline verification proves gameplay.
- [ ] Archive only committed source/docs/README with per-command `core.autocrlf=false`; CRC and compare every archive entry to its Git blob. Exclude private game/script/save/process evidence and historical releases.
- [ ] Copy separately named EXE/source/guides/hashes to the game and backup-source directories without overwriting different files. Verify destination hashes and preserve R22 hashes.
- [ ] Report actual supported map/task structures, runtime tests and unresolved boundaries. Update conversation handoff only as a task artifact if needed; do not alter permanent memories.

## Plan Self-Review and Execution Record

All design sections map to Tasks 1–6. Unknown runtime structures are explicit feasibility outputs, not guessed product contracts. All later typed interfaces consume the models owned by the earlier task; existing snapshot/parser types are retained. The five Review Focus failures each have an owning test step. No gameplay mutation is required for initial provenance/ABI discovery.

User approved the R23 design; execution continues natively in the current session to avoid repeated approvals and per-task agent overhead. A new request for game preparation will name the exact target and effect when that evidence is needed.
