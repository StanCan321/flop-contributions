# Contest recorder validation — 2026-09-13

## Scope

New one-shot local recorder; no installed agent script, signing key, operational
mailbox state, trusted baseline, or running timer changed. The prior maintenance
worktree was left untouched. This is not a contest operator implementation.

## Checks

- Full offline suite passed with the recorder tests included.
- Recorder tests cover append-only snapshots, exact bytes, permissions, persistent
  gaps and recovery, generation mismatch, individual/batched exact receipt matching,
  wrong identity/request/referee, tampering, truncated exports, storage exhaustion,
  interrupted publication, symlinks, redirects, network failure, content-length
  mismatch and bounded reads.
- One live read-only registration-room snapshot was retained privately. Expected
  exit 2 reported a coverage gap and zero matching receipts; no contest decision
  is inferred. The new recorder's own coverage does not include the separately
  preserved legacy captures, so its initial missing interval is broader than the
  known 2,000-record unrecovered interval from the original monitoring session.
- Snapshot files and older local captures remain outside Git. No raw message,
  signature, private capability, key or unredacted log is included in this patch.

## External activity

Read public registration/results exports and upstream issue discussions. Added a
factual case update under the existing durable-status issue:
[sonnet challenge #16](https://github.com/flop-labs/technocore-sonnet-challenge/issues/16#issuecomment-5653209497).
No Technocore writes, role changes, registration retries or acknowledgements were
performed for this change. No claim of eligibility, reward or acceptance is made.

## Limits

No interval can guarantee complete collection from a busy ephemeral ring. A local
hash chain is not an independently trusted timestamp or tamper-proof storage.
The recorder stops rather than prunes at its storage limit; scheduling/alerting
require separate authorization. The original acceptance automation remains paused.
