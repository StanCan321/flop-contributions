# Upstream review notes — 2026-09-01

Upstream repository: `flop-labs/technocore-chat`

Current `main` reviewed: `dc8accce8dfed03b6bedf0102d3c356809702756`

No public review, issue, pull request, or Technocore write was created during
this audit. Contributor-controlled tests were executed inside a disposable
bubblewrap sandbox with the network and home directory unavailable.

## PR #502 — room-view schema drift

- Submitted commit: `cf4ab6bf1a782ac309f403c55f7f1a817fde62ef`.
- Submitted targeted tests: 8 passed.
- The branch conflicts with current `main` in `src/manifest.py` because v0.11
  added the optional `wait_held` property in the same schema block.
- A local rebase resolution retaining both `wait_held` and the proposed
  `posted` property passed Ruff checks and 107 targeted schema, contract, and
  documentation tests.
- Assessment: technically sound after rebase; preserve `wait_held` while
  resolving the conflict.

## PR #496 — generation publication consistency

- Submitted commit: `4bcac3165cbdb06173512f19996b94484d7fc054`.
- The source conflicts with current `main` after sequence state was sharded.
- Its tests reference removed helper `_write_seq_state` and fail before testing
  the claimed behavior.
- Porting only the test hook to current `_set_seq_entry` reproduced both races:
  a first message can be visible with generation 0, and a recreated room's new
  message can be visible with the prior generation.
- Assessment: the bug remains reproducible, but the implementation and tests
  require a rebase onto the sharded sequence-state design.

## PR #469 and PR #545 — bridge cursor gaps

- PR #545 provides a stronger retained-export recovery path than PR #469's
  record-only gap handling.
- The reference bridge state still persists only a cursor, not
  `{generation, cursor}`.
- Surrounding text still describes sequence restart at 1 and periodic
  cursor-free detection, which predates v0.11's monotonic floor and explicit
  `generation` field.
- Assessment: prefer PR #545's export recovery, but bind durable bridge state
  to generation and update the stale lifecycle explanation before treating it
  as a safe reference loop.

## PR #470 — resilient poller and KV CLI

- The advertised utilities were deleted from the branch.
- The remaining diff only adds unpinned `portalocker>=2.8.0` to runtime
  dependencies, without corresponding utility code or lockfile evidence.
- Assessment: current branch does not implement its title and should not merge
  in its present form.
