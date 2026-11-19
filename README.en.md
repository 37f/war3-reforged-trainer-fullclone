[中文](README.md) | [English](README.en.md)

# Warcraft III: Reforged Trainer FullClone

FullClone is an unofficial extension of the [original Warcraft III: Reforged Trainer](https://github.com/dc114154qq/war3-reforged-trainer). The current release builds on the original project's v2.2.5 and includes the cumulative FullClone changes through local build R38.

## Current release · v2.2.5 FullClone R33

- [Release and downloads](https://github.com/37f/war3-reforged-trainer-fullclone/releases/tag/v2.2.5-fullclone-r33)
- [Windows x64 standalone executable](https://github.com/37f/war3-reforged-trainer-fullclone/releases/download/v2.2.5-fullclone-r33/War3ReforgedTrainer-v2.2.5-FullClone-R33.exe)
- [Complete source ZIP](https://github.com/37f/war3-reforged-trainer-fullclone/releases/download/v2.2.5-fullclone-r33/War3ReforgedTrainer-v2.2.5-FullClone-r33-source.zip) · [Browse source](source-v2.2.5/)
- [Cumulative changelog in Chinese](source-v2.2.5/R33_CHANGELOG_ZH.md) · [SHA-256 checksums](releases/v2.2.5-R33/SHA256SUMS-r33.txt)

R33 is the public release number. The Windows file version is `2.2.5.338`.

## R33 update · 2026-11-20

- Bulk alliance restoration processes all recorded players in one game call and keeps records for unverified slots.
- Neutral Hostile, Neutral Passive, and inactive slots can be dragged to diplomacy templates. Optional page memory has returned to Teams and Players.
- Hold a player card and use the mouse wheel to scroll the whole page before dropping it on another team.
- Restore the original owner of selected units or all recorded units. The transfer button and Ctrl+I+U share the records saved before each unit's first transfer in the current map session.

## Changes since the public R32 release

| Local build | Changes included in R33 |
| --- | --- |
| R33 | Moved to the original trainer's v2.2.5. Expanded static Lua quest analysis to recognize more standard callbacks, boolean conditions, and text wrappers. |
| R34 | Added army-wide health and mana refill and item ID filters for gathering ground items. |
| R35 | Added clone formations, army freeze and restore, three supply pack presets, and more spells that can be cast at the cursor. |
| R36 | Improved localized quest text and live state reporting for JASS quests with a unique match. Bound `Ctrl+Space` to army refill and `Ctrl+F2` to the selected cursor spell. |
| R37 | Kept known player names visible during transient read failures. Updated diplomacy cards, counts, and player details as soon as the game confirmed a drag-and-drop change. |
| R38 | Added a switch between in-game player names and map-defined names. Removed page memory from Teams and Players. Extended the English UI to the FullClone controls, hotkeys, player directory, and quest viewer. |

## Using the extensions

- The player directory shows teams, players, and diplomacy templates. Dragging a player to another template applies the corresponding alliance rules. The restore controls use the relationships saved before the first change in the current session.
- `Ctrl+Space` refills the selected unit owner's eligible army according to the panel's scope. `Ctrl+F2` casts the selected spell at the cursor. `Alt+F2` gathers matching ground items according to the item filter.
- The read-only quest viewer shows map-authored objectives, completion and failure conditions that can be resolved, and location links where available. Live status is available for uniquely matched JASS quests. Lua quest analysis is static.
- Choose **English** in **System → Interface language**. Map-authored text and player nicknames retain the language of the source data.

See the [supported game builds and usage limits](source-v2.2.5/R33_CHANGELOG_ZH.md#当前行为和使用范围). This update passed 395 automated tests with one upstream source comparison skipped. Browser tests exercised wheel scrolling, diplomacy, page memory, and the ownership controls in all three layouts with fixture data. Live game writes were outside this verification run. [Verification record](releases/v2.2.5-R33/R33_VERIFICATION.json)

## Older releases

[Reforged release archive](https://github.com/37f/war3-reforged-trainer-fullclone/releases) · [Earlier version notes in Chinese](README.md#以往版本说明) · [Separate Warcraft III Legacy project](https://github.com/37f/war3-legacy-trainer)
