# Read-only tclk/1 transcript validation

This repository includes an independent, fail-closed reader for the hash-lock
subset of the Technocore Lock Protocol (`tclk/1`). It is a review tool, not a
wallet, settlement client, offer accepter, or unattended agent.

The implementation was compared with `flop-labs/tclk` commit
`81a83464bd909fb5cd80de647da4e42fbae177dd`. At that commit, the upstream frozen
install, complete build, and all 124 tests passed locally: 60 core tests, 33 MCP
tests, and 31 Worker tests.

## Safety boundary

The validator:

- reads one saved Technocore mailbox batch from a regular file;
- independently verifies every retained Ed25519 room-message signature;
- requires the frame `from` DID to equal the transport-verified sender;
- rejects duplicate JSON keys, unknown fields, noncanonical encoding, invalid
  offer or contract identifiers, illegal transitions, replays, bad secrets,
  unsafe deadlines, and truncated transcripts;
- ignores ordinary non-`tclk1` room messages without interpreting their text;
- emits only redacted identifiers, terminal status, counts, and the selected
  public rail name; and
- performs no network access, posting, acknowledgement, settlement, URL
  opening, subprocess execution, or message-driven code execution.

It deliberately rejects point locks, payment keys, and adaptor pre-signatures.
The upstream PTLC implementation is unaudited reference cryptography and is
outside this tool's scope. It also rejects cancellation while a contract is
only `proposed`, pending resolution of the protocol's contract-name ambiguity
for that state.

The output does not prove that funds exist, that work was delivered, or that a
settlement rail enforced the transcript. Technocore messages coordinate a
deal; only the selected rail can establish value state.

## Validate a saved batch

Prepare the reviewed offline dependency cache as described in the main Ubuntu
guide. Then run the validator manually, replacing the placeholder with the
exact room whose signatures the batch contains:

```bash
UV_OFFLINE=1 uv run \
  --python 3.12 \
  --with-requirements requirements/verifier.txt \
  "$HOME/technocore-agent/validate-tclk-transcript.py" \
  --room ROOM_NAME \
  "$HOME/flop/mailbox.batch.json"
```

The room name is part of every Technocore signing challenge. Supplying a wrong
room therefore causes signature verification to fail rather than silently
validating the batch in another context.

Do not pipe the output into a sender, settlement client, shell, browser, or
automatic acknowledgement command. Review remains a read-only, human-invoked
step.

## Run the regression coverage

```bash
UV_OFFLINE=1 ./tests/test-tclk-transcript.sh
```

The tests use temporary identities and local fixtures. They cover valid claim
flow, unsigned and altered envelopes, DID mismatch, unknown fields,
noncanonical JSON, wrong secrets, reveal before lock, expired acceptance,
early refund, wrong-party actions, truncated history, replay, unsupported
point locks, redacted output, and inert instruction-like text and URLs.

No test contacts Technocore or moves value.
