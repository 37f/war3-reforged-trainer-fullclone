# SDD ledger — plan: docs/superpowers/plans/2026-10-23-r19-2-unassigned-team-monitor.md

- User approved the diagnosis report's minimum monitor-only fix; execute inline without another approval cycle.
- Baseline: existing name/team/package tests 68 passed in 17.71s.
- RED: newly added unassigned/invalid-wire cases produced 9 failed, 11 passed, 49 deselected in 5.46s. Actual dispatcher returned (3,13,0) and the formatter invented Team 0, reproducing the observed boundary failure.
- Ruling: reuse the existing dedicated, clean FullClone feature checkout and branch; no new worktree was requested. Keep original releases intact, and do not push/merge. This avoids an unsolicited new checkout; cost is that changes live on the existing local feature branch.
- Ruling: use the native Windows/PowerShell test/build driver and this persistent ledger rather than Bash workspace scripts (Bash is not available in PATH). Evidence stays in the independently named R19.2 output directory. No product behavior changes arise from this bookkeeping adaptation.
- Ruling: retain wire protocol 76 because packet fields/opcodes/signatures are unchanged and -1 is encoded in an existing unsigned result field; older clients reject it safely. A fresh game process is required for the rebuilt helper, avoiding reuse of the old loaded DLL.
- Implementation: gate the -1 fast path solely on status operation 317 and a valid owner ID; no peer alliance snapshot for unassigned status. Keep legacy 316 and setter/restoration bodies unchanged. Python decodes only 0xffffffff in 317, rejects nonempty peer metadata for that state, suppresses cached display assignment without changing restore records, and retains final selection checks.
- GREEN: name/team/player-relations/protocol regressions: 123 passed in 30.32s. Added cache-preservation and malformed-peer guards pass as well. Separate package identity first failed because the verifier still selected R19.1; spec/verifier now target R19.2.
- Final fresh review: no Critical/Important/Minor source findings. Reviewer deliberately did not judge packaged artifacts or actual-game acceptance; those remain separate verification gates, not an implied pass.
