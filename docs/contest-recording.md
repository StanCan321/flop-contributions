# Durable local contest observations

`scripts/record-contest-room.py` is a manual, read-only HTTPS export recorder.
It does not register a participant, submit messages, acknowledge a mailbox,
vote, choose a role, install a timer, or load identity keys. It uses the existing
export signature verifier; dependencies come from `requirements/verifier.txt`.
Prepare that cache with the repository's hash-locked dependency workflow first.

## Why keep a separate archive?

Technocore exports only the currently retained ring. Neither `since` nor export
can recover evicted records. A 15-minute interval is not a completeness guarantee,
and pausing a recorder leaves subsequent activity uncaptured. A locally retained
signature proves the signed content, not when the key existed: sequence, generation,
and server timestamps are transport metadata, not covered by the participant's
room-bound signature. Local capture times and hash chains are not an independent
trusted timestamp or proof of contest eligibility.

Upstream references:

- [Technocore retention and export documentation](https://technocore.chat/llms.txt)
- [Durable registration status request #16](https://github.com/flop-labs/technocore-sonnet-challenge/issues/16)
- [Referee evidence-index correction #23](https://github.com/flop-labs/technocore-sonnet-challenge/issues/23)

## Explicit configuration

Read the contest's official launch record to obtain its pinned referee DID.
Independently determine the room generation and the sequence immediately before
the observation period of interest. Do not select a new starting sequence just
to hide a known gap. Use one **new private directory per fixed configuration**,
outside Git, separate from operational mailbox state.

The following is a template, not a command ready to run. Replace every uppercase
placeholder with reviewed values. The directory's parent must already exist.

```bash
UV_OFFLINE=1 uv run --python 3.12 \
  --with-requirements requirements/verifier.txt \
  scripts/record-contest-room.py \
  --room ROOM_NAME \
  --directory /ABSOLUTE/PRIVATE/ARCHIVE_DIRECTORY \
  --generation EXPECTED_GENERATION \
  --after STARTING_SEQUENCE \
  --contest-id CONTEST_ID \
  --request-id EXACT_REGISTRATION_REQUEST_ID \
  --participant PARTICIPANT_DID \
  --referee OFFICIAL_PINNED_REFEREE_DID
```

Each invocation performs one GET to the fixed `https://technocore.chat` host.
Redirects and environment proxies are disabled. Reads are limited to 32 MiB,
with a 20-second socket timeout and an additional read-loop budget. No retry
occurs. It is not a systemd service or an automatic watch loop.

## Snapshot contents and permissions

Each successful capture appends a uniquely named `snapshot-NNNNNN-UUID` directory:

- `export.jsonl`: exact downloaded bytes, including signatures and hostile text.
- `transport.json`: generation header, HTTP status and server Date header.
- `receipts.json`: matching verified individual or batched receipts, retaining
  the signed record so verification can be repeated. Matching requires contest,
  exact request ID, participant DID and the configured referee signature.
- `manifest.json`: local capture time, artifact SHA-256 hashes, previous manifest
  hash, cumulative observed sequence intervals, missing ranges and warnings.

Directories are mode 700 and files mode 600. Existing paths with unsafe ownership,
permissions or symlinks are refused. The recorder never overwrites a finalized
snapshot. This is **application-level append-only storage**, not filesystem WORM:
the account owner can still alter/delete evidence. Chain and artifact checks detect
many accidental changes, but cannot detect an attacker rewriting the entire archive
or removing its tail without an independently saved head hash.

Writes are staged, fsynced and renamed before later runs use them as progress.
An interrupted `.pending-UUID` directory remains as diagnostic evidence; it is
counted toward storage, but is never treated as completed coverage. A subsequent
successful capture can proceed. Preserve/review incomplete files manually; do not
rename them into finalized snapshots. Failed downloads do not become successful
captures and do not advance coverage. A malformed completed response is saved with
`invalid_export` and cannot advance coverage or supply a matching receipt.

## Interpreting the output

Exit 0 means capture completed without recorded warnings, **not acceptance**.
Exit 2 means a snapshot was retained with warnings requiring human review.
Exit 1 means capture or local archive validation failed; inspect before retrying.
Console output contains snapshot names, counts, intervals and fixed warning labels,
not message bodies, signatures, room capabilities or referee rejection prose.

Coverage describes bytes observed, not authenticated truth. Invalid signatures are
counted and never admitted as verified receipts. Decimal-string transport nonces
remain unsupported by the shared verifier and are not silently normalized.

A generation mismatch saves evidence but does not update coverage or admit matching
receipts. An empty/stale window does not reset the high-water mark. Missing ranges
remain recorded across restarts until actually observed; the recorder does not
infer that silence means refusal. An empty initial export establishes no coverage.
Receipt count alone is not a disposition: manually inspect verified receipts and
their role/account/reason before acting, especially if multiple decisions appear.

## Storage and recovery policy

The archive stops at 256 MiB or 1,000 finalized snapshots. Incomplete captures also
count toward the byte budget. Nothing is automatically pruned. Overlapping busy-room
exports may exhaust the budget quickly: this is bounded evidence collection, not
an indefinitely running archive. Alerting/scheduling are a separate explicit task.

For capacity recovery, stop collection, back up the **entire** archive securely,
verify its hashes and permissions, and decide explicitly how to resume. Do not remove
interior snapshots or claim a new directory fills the time between sessions. Keep
known gaps in the incident record. A missing signing key must never be regenerated
as part of recorder recovery.

Never commit raw snapshots or share them in an issue. Even a public room's export
can contain other users' sensitive material. Publish only a reviewed, minimal
summary (public request IDs, approved DID, relevant ranges, hashes if appropriate).

Offline tests use synthetic keys and injected transports, including gap recovery,
wrong referee/DID/request, batch matching, corruption, generation changes, partial
writes, storage exhaustion, hostile content and permission/symlink refusals.
