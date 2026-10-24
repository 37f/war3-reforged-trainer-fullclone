# R21 Runtime Object Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Query all current-map custom/modified unit, item and ability definitions from the existing persistent helper and search them in the three existing ID pages.

**Architecture:** Add two read-only helper operations, a versioned bounded qword wire format, and a separate Python decoder/client. Reuse R20 display/copy rules and offline controls. Map/session validation and request generations prevent stale publication/copy; queries run through the existing serialized helper channel.

**Tech Stack:** Windows x64, C/SEH, Python 3.12, Tkinter, pytest, existing LLVM/MinGW and PyInstaller.

**Spec:** `docs/superpowers/specs/2026-10-24-runtime-object-catalog-design.md` (user approved 2026-10-24).

## Global Constraints

- Support only the validated Warcraft III 2.0.4.23745 profile; no product heap scan, arbitrary-address API or game-field writes.
- Preserve native names/signatures/hash and previous operation meanings; bump helper protocol 77 to 78 in matched source/package references.
- Preserve all R20 and earlier features; independent R21 EXE/source, no automatic GitHub publication.
- Include effective campaign-public plus chapter definitions; full list does not mean live-instance inventory or unchanged vanilla catalog.
- Bound total objects to 100000, response bytes to 32 MiB and each name to 64 KiB; never silently truncate as complete.
- No user game restart, map change, shortcut or save operation without explicit instruction.

## Review Focus

- Recycled roots after a map reload must not keep old rows/copy permissions: lifecycle and content/session validation tests in tasks 1–3; real transition gate in task 4.
- A missing manager in the menu must not be reported as a successful empty map: task 2 context tests.
- Multiple sets/levels with different names must retain candidates and mark partial: task 1 decoder/name tests.
- Same ID in different categories or a campaign-only object must remain correctly scoped: tasks 1/4 wire and live-reference tests.
- Concurrent monitor/refresh and stale queued workers must not overwrite helper files or current UI state: tasks 1/3 cancellation/generation tests.

## File boundaries

- Create `source/war3_current_map_catalog.py`: wire parsing, name resolution, client/state interfaces; no Tk or file archive access.
- Create `source/tools/war3_native_catalog.h`: bounded target reads, profile binding, lifecycle observation and pages; no gameplay mutation.
- Modify `source/tools/war3_native_helper.c`: two op constants/cases, include and protocol version; optional lightweight lifecycle observer only after directory use.
- Modify `source/war3_reforged_trainer.py`: version constants, helper allowlist, current-map client bridge and UI construction only.
- Modify `source/war3_custom_catalog_ui.py`: third source, shared asynchronous current-map state, expiration and search/copy integration.
- Create `source/test_current_map_catalog.py`, `source/test_native_catalog.py`; extend `source/test_custom_catalog_ui.py`.
- Create R21 spec/package verifier/notes, update protocol tests from the previous literal where they assert the matched global version.

### Task 1: Wire decoder, model and bounded client

**Interfaces:** `CatalogPage(token:int, kind:str, total:int, start:int, records:tuple[RuntimeDefinition,...])`; `parse_catalog_header(values:tuple[int,...])->tuple[int,tuple[int,int,int]]`; `parse_catalog_page(values, expected_token, kind, start)->CatalogPage`; `build_runtime_result(records)->CatalogResult`; `CurrentMapCatalogClient(query, identity).read(cancelled)->RuntimeCatalogSnapshot`; `.check(snapshot)->bool`.

Wire v1: header query returns `[0x31544352, 1, token, unit_count, item_count, ability_count]`. A page returns `[magic,1,token,kind_index,total,start,count]`, then each row `[base_id_le,id_le,custom,name_count]` and each candidate `[set_key,level,data_pointer,byte_length,<UTF8 qwords>]`. Rawcodes use four little-endian carrier bytes, not the trainer's textual integer conversion. Zero padding must be validated. Page count at most 16; accept no skipped/duplicate or wrong-kind rows. The final header must match the first.

- [ ] Write failing tests for malformed/truncated/oversize responses, stale token, unexpected cursors, rawcode preservation, duplicate IDs, name inheritance/ambiguity/TRIGSTR and cancellation.
- [ ] Run `python -m pytest -q test_current_map_catalog.py` and observe missing implementation failures.
- [ ] Implement decoder and immutable models. Resolve names without crossing category boundaries; reuse `CustomObjectEntry`, with current-map source and explicit fallback notes.
- [ ] Implement client through injected serialized query callable, bounded paging/deadline and final session recheck. Fail/discard incomplete enumeration; name failures can produce partial results.
- [ ] Run targeted tests and commit.

### Task 2: Read-only persistent helper operations

**Interfaces:** operation 318 header/check; operation 319 page (`rawcode=kind_index`, `arg0=start`, `arg1=expected_token`, `handler=0`, command unit=0). `war3_catalog_query(cmd,op,&extra,&count)` returns the wire above. `war3_catalog_observe()` retires session tokens after observed invalid/changed context, throttled and inactive before first use.

- [ ] Add native synthetic memory-harness tests for valid original/new arrays, missing context, invalid vtable/count/span/loop, multiple sets, UTF8/long strings, changed session and read-only behavior; first observe failure.
- [ ] Bind exact validated profile: context(13)->state(+0x20), unit/item/ability slots `0x230/0x238/0x338`; validate manager kinds/vtables and definitions arrays. Never call lazy constructors.
- [ ] Implement bounded pages and content/session validation including both context5/context13, relevant root headers and effective ID/name data; use a helper-owned generation and invalidate on observed non-map transitions. Full transition acceptance remains a release gate.
- [ ] Integrate two isolated operation cases and allowed Python op constants. Keep existing handlers unchanged except protocol version/include. Bump matched protocol/version and add explicit old-helper rejection.
- [ ] Compile with existing LLVM/SEH wrapper; run native harness, protocol/bootstrap/legacy tests. Commit only after passing.

### Task 3: Shared UI integration

**Interfaces:** extend `CampaignCatalogUI(..., runtime_client=None)` without breaking its existing constructor callers. Current-map state is independent of offline `CatalogSelection`; rows/render/copy choose the selected source. `set_runtime_client` invalidates old generations. Poll check only for visible current-map source; errors expire results without repeated dialogs.

- [ ] Add failing Tk/state tests for third source, shared categories, switching/reset, queue generation mismatch, old worker completion, disconnect/check failure, language, hidden source no polling and disabled stale copy.
- [ ] Add current-map controls/status/time/details. Worker threads only return payloads; Tk runs on main thread. Do not let a stale job clear busy flags belonging to a new job.
- [ ] Bind current `War3Trainer` via query callable using existing `_native_helper_lock` channel; reject connection identity changes before and after calls. Do not locate selected units for a catalog query.
- [ ] Run source UI/main integration tests, offline regression and no-selection mocks; commit.

### Task 4: Real runtime proof and package

- [ ] Run new helper read-only queries in the user's already-open chapter; compare 64/14/33 rawcodes, 72 explicit names and 90 public-only records with retained reference. Record actual query latency.
- [ ] With user-controlled transitions, test menu/reload/second chapter and old-result expiry; verify current-map lifecycle identity even for reused roots. If unproven or failing, do not claim R21 release-ready; continue independently with remaining checks while requesting only needed transition assistance.
- [ ] Run full relevant suite and final regression, with compiler PATH explicitly set. Review helper read-only boundary and main AST deltas against R20.
- [ ] Fresh final branch reviewer (required by executing-plans), resolve verified findings and rerun affected checks.
- [ ] Build `War3ReforgedTrainer-v1.0.19-FullClone-R21-Test.exe` using a separate spec; verify bundled modules, helper protocol/hash, source ZIP Git-blob parity, CRC and SHA-256. No upload.
- [ ] Deliver separately named EXE/source/Chinese instructions and accurate test boundaries; preserve prior artifacts.

## Execution

This plan follows the user's approved design. Implement inline in the existing linked worktree; no separate implementation agents. A fresh final reviewer is used only when the branch is ready. Routine protocol layout, limits and source file choices above are implementation decisions, not additional user requirements.
