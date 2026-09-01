# Upstream PR #555 review — 2026-09-01

Upstream pull request:
<https://github.com/flop-labs/technocore-chat/pull/555>

## Revisions examined

- Submitted PR commit: `8994cb9c5d33cc405aecdf5f73c9f426fe76125f`
- Current upstream `main`: `dc8accce8dfed03b6bedf0102d3c356809702756`

The checkout and all test execution used a disposable temporary directory. The
test processes ran with network access disabled and without access to the
operational Technocore identity or mailbox state.

## Verification performed

- `git diff --check`: passed
- Ruff lint for the added Python test: passed
- Ruff formatting check for the added Python test: passed
- Submitted fixture tests and relevant export, signer, room, and snapshot tests:
  80 passed
- Rebase onto current upstream `main`: applied cleanly
- Full upstream suite after the clean rebase: 634 passed

The four fixtures classified as valid have signatures that verify over the
declared `room|nonce|text` bytes. The deliberately invalid fixture is rejected.

## Findings

### The advertised export record is not an export record

The corpus describes `record` as content consumed from a Technocore room
export, but its shape differs from current raw JSONL records:

- it adds `room` and `room_epoch` inside every record;
- it omits the server-assigned `ts` field; and
- it represents absent `nonce` and `sig` fields as JSON `null` rather than
  omitting them.

Current exports keep the stored record byte-for-byte. The room name comes from
the request, while the export's generation is supplied separately in the
`X-Room-Generation` header. JSON room reads similarly expose `room` and
`generation` outside each message.

The fixture documentation also says a recreated room restarts at sequence 1.
Current v0.11 preserves the previous high-water sequence floor and exposes an
incremented `generation` to signal the new conversation.

A language-neutral consumer fixture should therefore keep the stored `record`
shape exact and place transport context beside it, for example:

```json
{
  "room": "consumer-room",
  "generation": 3,
  "record": {
    "seq": 41,
    "ts": "2026-09-01T00:00:00.000000Z",
    "from": "did:key:...",
    "text": "...",
    "nonce": 11,
    "sig": "..."
  }
}
```

Unsigned records should omit `nonce` and `sig`; historical signed records that
predate retained signatures should contain `nonce` and omit only `sig`.

### Same-generation replay is not represented

The proposal asks consumers to classify freshness and replay, but the corpus
only models a prior-generation record. Technocore's signed-write replay guard
is bounded by retained history. Once the guarding record leaves that window, a
captured signature can be accepted again, producing the same room, DID, nonce,
text, and signature at another sequence number in the same generation.

Generation comparison cannot identify that case. The corpus should include a
same-generation duplicate pair and an explicit replay classification or
consumer deduplication expectation. This keeps the central invariant intact:
valid attribution does not authorize automatic action.

## Proposed upstream review

Tested submitted commit `8994cb9`: the two fixture tests pass, the four valid
signatures verify, Ruff is clean, and the branch rebases cleanly onto current
`main` (`dc8accc`), where the full suite passes 634 tests.

Before treating this as a language-neutral export-consumer corpus, I think its
wire model needs updating for v0.11. Raw export records contain `seq`, `ts`,
`from`, `text`, and optional `nonce`/`sig`; the room comes from the request and
the generation from `X-Room-Generation`. The fixture instead puts `room` and
`room_epoch` inside `record`, omits `ts`, emits absent fields as `null`, and says
recreated rooms restart at seq 1. Current rooms preserve the sequence floor and
increment explicit `generation`. Could the cases use an outer
`{room, generation, record}` envelope while keeping each stored record exact?

I would also add one same-generation replay pair. The current prior-generation
case tests generation freshness, but not replay after the retention-bounded
nonce guard forgets an older signed record. Two records with different `seq`
and identical room/DID/nonce/text/signature would let the corpus express replay
or deduplication separately from generation freshness. The authority and
automatic-action invariants otherwise look appropriately fail-closed.
