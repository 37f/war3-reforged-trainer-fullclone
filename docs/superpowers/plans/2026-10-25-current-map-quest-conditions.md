# Current-map Quest Condition Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically locate the active map script and explain its actual quest completion/failure and direct victory/defeat conditions with inspectable evidence.

**Architecture:** Prove source ownership before publication. A bounded JASS parser and conservative analysis module operate only on immutable script/string snapshots; a separate Tk controller runs background work and rejects stale generations. Reuse R21 connection/session/helper serialization and R20 read-only archive access; do not refactor old gameplay features.

**Tech Stack:** Windows x64, Python 3.12 standard library/Tk/pytest, existing StormLib and LLVM/SEH helper only where verified runtime reads require it.

**Spec:** `docs/superpowers/specs/2026-10-25-current-map-quest-conditions-design.md` (user approved 2026-10-25).

## Global Constraints

- Base R21 `48a3158442094e5c1ed4b654b61e10eb8a3f68f7`; retain its delivered EXE and source archive unchanged. Current supported runtime is exact Warcraft III 2.0.4.23745 x64.
- User selected automatic current-map identification, actual script conditions and explicit unknowns; no guessed disk source or silent manual-file fallback.
- JASS first. Lua/encrypted/unavailable or dynamically generated code must not appear as an empty successful analysis.
- Never execute map code, eval expressions, alter quest/game state, install tools, or close/switch the user's game. Helper-owned transport buffers are allowed under existing rules.
- First prove the active script source and same-session ownership; no full product delivery while this gate is unproven. Pure parser work can proceed independently while runtime evidence is pending.
- Preserve old operations/native names/signatures/hash. New helper operations/protocol only if required, in a separate checked handler. No arbitrary caller addresses or foreign-library archive-handle reuse.
- All returned claims retain function/line/path evidence and unresolved reasons. Static initial values are not live progress.
- Bound bytes/tokens/nodes/functions/call depth/paths/elapsed time and cancellation. Fail or mark partial on limits, never silently truncate as complete.
- Independent R22 test EXE/source/docs/checksums. No automatic GitHub publication.

## Review Focus

1. Different chapters with the same name/object IDs must not be confused; source token and hash, not similarity. Task 1/4 rejection and transition tests.
2. Custom wrappers/aliases or shadowed standard BJ names must not invent semantics. Task 3 wrapper/alias/unknown tests.
3. A victory function without an event is not unconditional: trace callers, trigger execution semantics, disable/enable and guards. Task 3/5 path assertions.
4. Script text containing fake calls, reset-to-false mutations, and unsupported scripts must not create successful fake results. Task 2/3 parser and coverage tests.
5. Queued replies after close/map change/delayed Tk ticks must not publish or refresh obsolete reports. Task 4 generation/validation tests; retain R21 race regressions.

## Files and interfaces

- `source/war3_current_map_script.py`: immutable `ScriptSnapshot(identity, session_token, origin, language, script, strings_data, script_sha256, strings_sha256, validated_at, provenance)` and `CurrentMapScriptClient(query, identity).read(cancelled)/check(snapshot)`. The query provider must prove current resource ownership; model/validation cannot manufacture it.
- `source/war3_jass.py`: bounded tokenization/AST with source ranges. `parse_jass(text: str, cancelled=...)->JassProgram`; immutable `Expr`, `Stmt`, `JassFunction`, program globals/functions/diagnostics. No runtime imports.
- `source/war3_quest_analysis.py`: `analyze_quests(snapshot: ScriptSnapshot,cancelled=...)->QuestReport`; immutable task/item/outcome/evidence/issue records, supported/partial state and source identity. Uses parser; no process/archive/Tk calls.
- `source/war3_quest_ui.py`: `QuestAnalysisUI(root,language,source_client_provider)` and `add_controls(tab)`, `detect()`, `invalidate(reason)`, `refresh_language()`. Uses shared source/analysis workers; no Tk in workers.
- `source/analysis/probe-current-map-script.py`, `docs/r22-quest-source-feasibility.md`: scoped runtime investigation/proof and retained manual reference checks. Investigation addresses never become product constants without a validated profile.
- If needed: new `source/tools/war3_native_script.h` included by `war3_native_helper.c`; bridge/constants/UI construction only in `war3_reforged_trainer.py`, new text in `war3_ui_i18n.py`.
- Tests: `test_current_map_script.py`, `test_jass.py`, `test_quest_analysis.py`, `test_quest_ui.py`; native synthetic test only for an implemented native reader. Separate R22 spec/verifier/notes in task 5.

### Task 1: Prove and encapsulate current script ownership

- [ ] Read existing profile/context/lifecycle/archive contracts. Use available REA/static disassembly and read-only runtime probes to locate current script/resource ancestry; record exact game hash, process identity, active-map token, source path/loaded origin, script and string hashes. No assumption that plaintext survives compilation.
- [ ] Compare against an independently read chapter; inspect exact source bytes through an established resource path, not a guessed candidate. Validate that menu invalidates ownership and another chapter has its own script.
- [ ] If locating plaintext is not possible, investigate verified active archive/mount ancestry. If neither proves ownership, record the blocker and continue only independent parser work; do not weaken the gate.
- [ ] Write failing tests for immutable snapshot validation and client identity/token changes, malformed/oversize/truncated data, stale source/proof, cancellation, and unsupported language. `python -m pytest -q test_current_map_script.py` must fail before implementing missing API.
- [ ] Implement the source model/client with limits: 32 MiB script, 16 MiB strings, 60-second read deadline; validate final identity/session/content evidence before returning. Origin is data, never shell code. Keep the runtime provider separate until its evidence is sufficient.
- [ ] Run source model tests plus existing current-map/archive regressions; record outcome and commit. Runtime gate completion requires actual evidence, not mocks alone.

### Task 2: Bounded JASS syntax with exact evidence positions

- [ ] Add failing lexer/parser tests covering strings/comments/fake call text, four-byte rawcodes, escapes/CRLF, globals/locals/arrays, function references/calls, precedence, unary not/minus, if/elseif/else, loop/exitwhen, return, debug, native/type declarations, malformed input and limits.
- [ ] Run `python -m pytest -q test_jass.py`; expect missing module/API failure, then implement `parse_jass` in `war3_jass.py`.
- [ ] Use a lexer plus Pratt expression parser and statement parser; never use regex snippets as the semantic parser. Keep unrecognized constructs and errors with line/column; incomplete parse cannot be full success.
- [ ] Set tested limits: 32 MiB UTF-8, 500000 tokens/nodes, nesting 128, functions 50000, 30-second parse budget. Cancellation checked during tokenization/parse, iterative counters prevent accidental unbounded recursion.
- [ ] Run full parser test file; inspect AST for retained real chapter functions/lines without executing it. Commit.

### Task 3: Quest association and conservative backward condition graph

- [ ] Add failing tests for native/BJ quest creation, last-created aliases and arrays; completion/failure true vs reset false; comment/string false positives; title/WTS resolution; direct victory/defeat not attached to arbitrary tasks; actual numeric comparison operators.
- [ ] Add graph tests: death/region/timer event + registered condition/action, nested AND/OR/early-return conditions, multiple callers, ConditionalTriggerExecute vs TriggerExecute, disabled/enable gates, static counter init/increment and unknown dynamic value; wrappers/shadowed BJ names, recursion, dynamic ExecuteFunc, missing body and custom UI tasks.
- [ ] Run `python -m pytest -q test_quest_analysis.py`; expect failure before implementing analyzer.
- [ ] Implement immutable `QuestReport`/records and static ID/alias association in `war3_quest_analysis.py`. Analyze resolvable task setters and terminal game calls; propagate ambiguity instead of choosing first alias. BJ adapters apply only when not shadowed and their semantics have a verified source.
- [ ] Build caller/trigger graph with branch constraints. Reverse from each relevant mutation to roots; keep path alternatives separate, preserve negations and event/enable gates. Incomplete or unresolved predicates retain expressions and reasons. Do not infer game loss from text/function names.
- [ ] Trace relevant counter assignments and task-item conditions where sound. Unknown paths/loops/aliases are visible; no runtime-current-value claim. Bound depth 64, paths per target 128, tasks 10000, analysis 30 seconds; mark partial if limits prevent coverage.
- [ ] Add retained synthetic tests modeled on chapter 3: `recruits == 3`; guarded region completion; two distinct death losses after delay; victory action reached via another trigger. Independently compare real chapter source occurrences and manually trace evidence, not analyzer counts alone.
- [ ] Run parser/analyzer/source tests, record coverage limitations and commit.

### Task 4: Verified runtime provider and asynchronous task page

- [ ] Require task 1 runtime gate before product provider integration. Add failing transport tests for exact ownership, same-session source read, menu/change/close/reconnect, protocol/version rejection. If C needed, add synthetic bounded-reader tests before its handler; compile with existing SEH wrapper.
- [ ] Implement the verified provider through existing serialized helper; no changes to old read/gameplay methods. Bump protocol and matched verifier/tests only if native operations are added; preserve old meanings.
- [ ] Add failing Tk/controller tests: first visible page starts a read, hidden page avoids continuous analysis, source/read/analysis statuses, unknowns/details/search, old worker and close rejection, map changes clear report, late queue delivery cannot renew validation, Chinese/English labels.
- [ ] Implement `QuestAnalysisUI` and construct a separate task tab in the main GUI. Show source/session/hash/time, task/terminal-outcome list and condition/evidence details; no task mutation buttons. Automatic first read on visible active source plus explicit refresh.
- [ ] Run all new tests and current R21 UI/session/bootstrap/protocol/i18n regressions. Commit only on green.

### Task 5: Runtime/UI/reference proof and independent delivery

- [ ] Read the user's active map through normal connection/source provider. Confirm actual origin and compare script/string hashes to independent file reference; repeat across a user-controlled menu/another chapter transition. Do not request users trigger failure or lose progress.
- [ ] Compare displayed real chapter conditions with manual source paths, including caller chain and unresolved reasons. Verify normal GUI source/search/English display and no old monitoring regression. Preserve campaign/map/save hashes.
- [ ] Run relevant tests and complete suite with existing compiler/runtime PATH. Final fresh whole-branch review per executing-plans; Important/Critical findings get one RED→GREEN fix pass and a green suite; Minor findings recorded.
- [ ] Create separate R22 PyInstaller spec/verifier, actual frozen self-test and package source/DLL parity. Archive final Git source paths with per-command `core.autocrlf=false`; verify CRC/Git blobs, hashes and copied deliverables, retaining all R21 files.
- [ ] Deliver R22 test EXE, source ZIP, Chinese use/verification notes and checksums with supported-build and static-vs-runtime proof boundaries. No upload.

## Execution choice and checkpoint

User explicitly approved the design and starting implementation. Continue inline in the existing linked worktree on `codex/r22-quest-conditions-design`; preserve R21 at its existing commit. Avoid extra implementation agents for shared parser/source/UI contracts; keep one fresh final reviewer. Plan details are implementation decisions under the approved scope, not another permission checkpoint.

The source locator is a research dependency, not a fabricated known interface implementation. Runtime proof and pure parser work may be interleaved; product integration and delivery remain gated by actual ownership/transition evidence. Keep this dependency and every ruling in the per-plan execution ledger.
