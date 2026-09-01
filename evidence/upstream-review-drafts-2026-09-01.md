# Upstream reviews posted — 2026-09-01

These reviews were posted by `StanCan321`. They are based on the isolated
review recorded in `upstream-review-2026-09-01.md`.

## PR #502

Posted at <https://github.com/flop-labs/technocore-chat/pull/502#issuecomment-5495258060>.

Tested against submitted commit `cf4ab6b`: all 8 targeted tests pass in an
isolated, network-disabled sandbox. The branch now conflicts with current
`main` (`dc8accc`) in `_ROOM_VIEW_SCHEMA`, where v0.11 added the optional
`wait_held` property. I manually rebased the commit by retaining `wait_held`
and adding the proposed `posted`, required `generation`, and
`additionalProperties: false`; Ruff passed and 107 targeted room-schema,
contract, and documentation tests passed. The schema fix looks sound after a
rebase, provided the conflict resolution preserves `wait_held`.

## PR #496

Posted at <https://github.com/flop-labs/technocore-chat/pull/496#issuecomment-5495258306>.

The reported publication race still reproduces on current `main` (`dc8accc`),
but this branch conflicts after the sequence-state sharding refactor and its
two new tests reference removed helper `_write_seq_state`. I ported only the
test hook to current `_set_seq_entry`; both assertions then fail for the
intended reason: a first record is observable with generation 0, and a
recreated room's first new record is observable with the prior generation.
This remains a valid bug, but the implementation and tests need rebasing onto
the sharded `_seq_field`/`_set_seq_entry` design.

## PR #545

Posted at <https://github.com/flop-labs/technocore-chat/pull/545#issuecomment-5495258572>.

The export-based recovery is stronger than simply recording and stepping over
a gap, but the reference loop persists only `cursor`, not
`{generation, cursor}`. It checks generation only between the triggering poll
and export snapshot, so it does not detect a room-generation change between
ordinary polls. The surrounding epoch guidance also still says a recreated
room restarts at sequence 1 and requires a periodic cursor-free read; v0.11
preserves the sequence floor and exposes `generation` directly. Before this is
used as a reference bridge, please consider loading/saving generation with the
cursor, stopping or explicitly resyncing when `view["generation"]` differs,
and updating the stale lifecycle explanation.
