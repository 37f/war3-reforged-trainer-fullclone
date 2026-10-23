# R19.2 Unassigned Team Monitor Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; one fresh whole-change review after implementation. Steps use checkbox syntax.

**Goal:** Display valid selected players with native team -1 without failing the existing name/team monitor.

**Architecture:** Keep operation 316 and every setter unchanged. Operation 317 alone accepts the uint32 -1 sentinel, reports no alliance snapshot for that unassigned state, and continues bounded name reading and final identity checks. Decode the sentinel only in the named status reader and display it explicitly in Chinese/English, never as team zero or a neutral template.

**Tech Stack:** Existing Python/Tk, C persistent helper, pytest/compiled SEH fixtures, LLVM-MinGW and PyInstaller.

**Spec:** `source/R19_2_UNASSIGNED_TEAM_NOTES.md`, recording the user's approval of the preceding minimum-scope diagnosis proposal. Runtime observation: selected nkot belongs to internal player 6, native team -1, identity guard succeeds.

## Global Constraints

- Preserve R19.1 and all older artifacts; deliver a separately named R19.2 EXE/source ZIP.
- No changes to native signatures, profiles/hashes, opcode numbers, unit reads, team setters/restoration, control, ownership, cloning or maps/saves.
- Existing wire layout/protocol 76 remains unchanged; new helper build requires a clean game process before real-map acceptance.
- Do not publish GitHub without a new request.

## Review Focus

- -1 must not appear as team 0 or be accepted by setters/restoration.
- Normal native teams and neutral labels keep existing behavior.
- Missing name must not destroy valid player/team data.
- Cleared/changed selection must not revive an old name/status.
- Other invalid team values or malformed requests must remain rejected.

## Task 1: Minimal Monitor Compatibility and Independent Package

**Files:** `source/tools/war3_native_helper.c`, `source/war3_reforged_trainer.py`, `source/war3_ui_i18n.py`; existing player-name/team/protocol tests; spec/package verifier and release verification docs.

**Interfaces:** Existing `query_selected_owner_team(include_player_name=True) -> PlayerTeamStatus`; native operation 317 stores -1 as zero-extended uint32 `0xffffffff` in result with peer_count=0. No signature/layout change. Legacy 316 continues rejecting -1.

- [ ] Run existing name/team/package regression baseline.
- [ ] Add RED tests: real compiled C operation 317 with owner team -1 succeeds, produces result 0xffffffff and bounded name payload with zero setters; legacy 316 and setters still reject -1; malformed other teams fail. Python sentinel decode retains name/slot, no restore snapshot, stale selection rejected; formatter shows explicit unassigned value in both languages.
- [ ] Run those tests and retain actual expected RED failures.
- [ ] Implement narrowly gated C acceptance and empty peer snapshot only for 317/-1; Python sentinel handling, display and translations. Preserve unknown-value rejection and final identity checks.
- [ ] Run focused and complete pytest suite; use existing SEH compiler and dependencies.
- [ ] Rebuild helper and independent R19.2 EXE; verify embedded source/DLL, offline frozen self-test, source ZIP CRC and delivery hashes.
- [ ] Fresh whole-change review; address important findings with RED/GREEN tests. Record any deliberate deviations.
- [ ] Leave a local commit and separately named delivery; describe real-game test boundary and required restart. No merge/push/release.
