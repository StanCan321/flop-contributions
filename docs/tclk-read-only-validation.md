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
- binds its report to the batch generation, starting and proposed cursors,
  count, and first and last sequence numbers;
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

## Validate a trusted-reviewed saved batch

Prepare the reviewed offline dependency cache as described in the main Ubuntu
guide. Install the validator and manual wrapper:

```bash
install -m 700 \
  scripts/validate-tclk-transcript.py \
  "$HOME/technocore-agent/validate-tclk-transcript.py"

install -m 700 \
  scripts/review-tclk-batch.sh \
  "$HOME/technocore-agent/review-tclk-batch.sh"
```

First run the generic trusted mailbox review. It saves the batch and creates a
redacted receipt only after independently verifying every retained signature:

```bash
"$HOME/technocore-agent/review-mailbox.sh"
```

After inspecting that private batch as described in the Ubuntu guide, invoke
the protocol-specific review manually:

```bash
"$HOME/technocore-agent/review-tclk-batch.sh"
```

The wrapper reads the exact room from the protected mailbox capability file;
it does not accept a room on the command line. It refuses to run unless the
generic trusted receipt matches the saved batch's generation, starting cursor,
proposed cursor, and count and says that every signature is valid. It uses only
the installed hash lock with `UV_OFFLINE=1`, then atomically writes the private
report with mode `600` to:

```text
$HOME/flop/tclk.review.json
```

The report repeats the batch generation, cursor range, count, and first and
last sequence numbers and includes `batch_binding_sha256`, a deterministic
digest of those fields. This prevents a report from being mistaken for one
covering a different mailbox epoch or sequence range.

The room name remains part of every Technocore signing challenge. A batch from
another room therefore fails signature verification rather than being
silently accepted in the protected mailbox context.

Do not pipe the output into a sender, settlement client, shell, browser, or
automatic acknowledgement command. Review remains a read-only, human-invoked
step.

## Run the regression coverage

```bash
UV_OFFLINE=1 ./tests/test-tclk-transcript.sh
UV_OFFLINE=1 ./tests/test-tclk-review-wrapper.sh
```

The tests use temporary identities and local fixtures. They cover valid claim
flow, unsigned and altered envelopes, DID mismatch, unknown fields,
noncanonical JSON, wrong secrets, reveal before lock, expired acceptance,
early refund, wrong-party actions, truncated history, replay, unsupported
point locks, redacted output, and inert instruction-like text and URLs.
Wrapper coverage additionally proves that a mismatched trusted receipt fails
without replacing earlier evidence and that the wrapper contains no network,
sender, or acknowledgement path.

No test contacts Technocore or moves value.

## Rehearse zero-value settlement locally

The local PaperRail test exercises the coordination and settlement predicates
without a network, blockchain, wallet, or valuable asset:

```bash
UV_OFFLINE=1 uv run \
  --python 3.12 \
  --with-requirements requirements/verifier.txt \
  tests/test-tclk-paper-rail.py
```

It performs complete `offer → accept → lock → reveal → receipt` and
`offer → accept → lock → refund → receipt` lifecycles with temporary Ed25519
identities. The rail independently refuses an incorrect secret and a refund
before its deadline. Its redacted validator output contains neither temporary
identity secrets nor the hash-lock preimage.

This is a local behavioral rehearsal only. It does not demonstrate a working
FLOP, EVM, x402, or other value-bearing settlement rail.

## Check cross-implementation wire compatibility

The golden-vector test pins the upstream offer line, offer identifier,
contract identifier, acceptance line, and non-ASCII escaping case as fixed
constants:

```bash
UV_OFFLINE=1 uv run \
  --python 3.12 \
  --with-requirements requirements/verifier.txt \
  tests/test-tclk-golden-vectors.py
```

The constants were checked against `flop-labs/tclk` commit
`1459b78e3b981bbac67f845784c885b3b1ad85ba`. At review time, the upstream
`tests/vectors.test.ts` file had SHA-256
`c60f109ba26547c6be0795b0eb66a861a96a7d68a36885a28f318e69a1cebb96`.
They must not be regenerated from this repository's validator: their purpose
is to catch independent encoding or hashing drift.
