# Custom Object Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only campaign/chapter object discovery to the existing item, ability and unit ID pages.

**Architecture:** A bounded binary parser resolves scoped strings and overlays chapter fields on campaign definitions. An isolated StormLib adapter reads only the needed MPQ entries; a shared background UI controller supplies results to the existing catalog tables without touching game/native code.

**Tech Stack:** Python 3.12, Tk/ttk, ctypes, official x64 StormLib, pytest, existing PyInstaller build.

**Spec:** `docs/superpowers/specs/2026-10-24-custom-object-catalog-design.md` (approved by user).

## Global Constraints

- Read-only `.w3n` plus manually selected chapter; no automatic game/chapter identity claim.
- Preserve native protocol 77, game functions, general catalogs and previously tested R19.3 behavior.
- Distinguish new objects, modified vanilla objects, missing entries, partial parsing and unsupported formats.
- Scope WTS references to their own layer; merge fields, not whole object records.
- Only load a bundled, verified official StormLib; do not depend on the user's installed game DLL.
- Independent test EXE and source; preserve old artifacts; no GitHub publication in this task.

## Review Focus

- A source campaign changes between listing and detection: reject stale chapter identity and clear old results.
- Same TRIGSTR number in two layers: resolve each against its original layer.
- A malformed/huge inner map: stop bounded reads, close handles, retain truthful partial/failure state.
- Duplicate/conflicting rawcodes or inheritance cycles: report an issue instead of silently selecting a name.
- A scan completes after the user changes chapters: never display results under the new chapter.

### Task 1: Bounded object and string parser

**Files:** create `source/war3_custom_objects.py`, `source/test_custom_objects.py`.

**Interfaces:** `parse_object_data(data: bytes, kind: str) -> tuple[ObjectDefinition, ...]`; `parse_wts(data: bytes) -> dict[int,str]`; `merge_objects(campaign, chapter, campaign_strings, chapter_strings, kind) -> tuple[CustomObjectEntry,...]`. Entry fields: `rawcode`, `name`, `base_id`, `object_type`, `source`, `note`, `copyable`.

- [ ] Write synthetic binary tests for object v1/v2/v3 (including v3 sets), extended skill fields, new/modified IDs, scoped WTS, field overlays, inheritance/cycles, invalid ID bytes, unknown versions, duplicate records and malformed bounds. Hand-derived names/counts are expected values.
- [ ] Run `python -m pytest test_custom_objects.py -q`; expected missing-feature failures first.
- [ ] Implement strict readers and merge logic. Use limits 32 MiB/object file, 1 MiB/string, 100000 objects, 1000000 total modifications, 64 inheritance hops; report any limit rather than silent truncation.
- [ ] Run the same tests plus `test_id_catalog.py`; expected pass. Commit parser and tests.

### Task 2: Archive discovery and read-only detection

**Files:** create `source/war3_campaign_catalog.py`, `source/test_campaign_catalog.py`; add `source/tools/StormLib.dll` and `source/third_party/StormLib/` provenance/license.

**Interfaces:** `list_campaign(path: Path) -> CampaignInfo` (path, file identity, chapters, issues); `detect_campaign(info: CampaignInfo, chapter: Chapter) -> CatalogResult` (entries by kind, per-file status, issues). `StormArchive` exposes only context manager and `read(name, max_bytes) -> bytes | None`.

- [ ] Write actual nested MPQ fixture tests for chapter titles/order, missing listfile fallback, per-kind partial failure, changed source, archive size limit and source SHA preservation. Use StormLib creation calls only in test fixture tooling, never the production adapter.
- [ ] Observe tests fail, then implement read-only adapter with exact ABI, W3F v1 parsing and listfile supplement, temporary inner map with generated safe filename, per-source diagnostics, and a 60-second cooperative deadline/entry bounds.
- [ ] Obtain official release asset, verify published digest and PE x64, pin DLL hash/version/license in source, prove dependency load and nested MPQ tests.
- [ ] Run `python -m pytest test_campaign_catalog.py test_custom_objects.py test_id_catalog.py -q`; expected pass. Commit.

### Task 3: Shared offline UI integration

**Files:** create `source/war3_custom_catalog_ui.py`, `source/test_custom_catalog_ui.py`; narrow edits to existing `source/war3_reforged_trainer.py` ID-table functions and i18n dictionary.

**Interfaces:** `CampaignCatalogUI(root, on_change, language)` owns shared path/chapter/result; `add_controls(tab, kind)`, `is_custom(kind)`, `rows(kind, query)`, `can_copy(rawcode)`. All Tk operations on main thread; workers return through queue, generation tokens reject stale work.

- [ ] Write controller tests for source selection invalidation, out-of-order results, searching and copying real rawcodes, partial/failure display, language switch and shared results across kinds. Expected old response ignored and new chapter empty until explicitly detected.
- [ ] Observe failure, implement controls and table integration without touching trainer/native methods.
- [ ] Run controller/parser/catalog tests. Open actual UI offline and inspect source/general switching, detection and clipboard using a controlled fixture. Expected displayed names/counts agree with fixture and old catalog remains intact. Commit.

### Task 4: Independent package and final verification

**Files:** update PyInstaller spec to separately named `War3ReforgedTrainer-v1.0.19-FullClone-R20-Test`; add `source/R20_CUSTOM_CATALOG_NOTES.md` and usage-guide section.

- [ ] Run full project pytest, preserve log and inspect result; any failure must be explained/fixed before completion.
- [ ] Run final independent review against approved spec and changed files; fix important findings with regression tests.
- [ ] Build EXE, inspect packaged modules/DLL/third-party notices and native helper identity. Run frozen offline smoke check. Create exact-source ZIP, hashes and verification report under `outputs/v1.0.19-FullClone-R20-Test`, retaining all old versions.
- [ ] Real campaign/editor name cross-check requires user's sample path/chapter; if unavailable, explicitly separate controlled-fixture validation from real-campaign acceptance. No game launch or process writes needed.

## Execution rulings and progress

- Native app worktree tool returned `Not a git repository` because chat cwd is above this nested repo. A sibling Git linked worktree was created with Git at `work/v19-migration/fullclone-r20-custom-catalog`; all implementation commands use that path explicitly.
- The user approved implementation; execute inline without another plan-approval round. The design is the binding scope.
- Task 1 complete: bounded object versions 1/2/3, WTS and field-scoped overlays; 40 focused tests currently pass including downstream UI/runtime tests.
- Task 2 complete: real nested MPQ fixtures and verified official x64 DLL; source hashes are checked before/after reads. Additional real tests use three campaigns in the user-provided folder.
- Task 3 complete: shared offline controls and generation-token stale-result rejection, actual Tk widgets tested; general ID catalog retained.
- Ruling: original-table chapter rows may modify campaign-created IDs, so preserve the campaign's true template rather than classify this as a conflicting redefinition. A dedicated regression test fails without this rule.
- Ruling: actual old campaigns and the upstream `Modification.u1` reader show the four-byte field trailer is opaque, not necessarily zero/base/new ID. Consume and bounds-check it without imposing false equality; reject truncation, invalid types and unparsed tails. Falsely requiring equality excluded a valid chapter's unit definitions.
- Ruling: World Editor inserts `//` comments between WTS headers and braces. Use a bounded line parser, preserving literal comments inside string bodies. Actual campaigns exposed and regression tests pin this behavior.
- Verification environment: first full-suite attempt had 71 setup errors because clang was absent from PATH (852 passed, 1067 skipped). With existing SEH clang paths restored, the affected player-name test file passes 71 tests; final full suite must run with this toolchain before shipping.
