# FLOP Labs / Technocore Contributions

Public, reproducible technical contributions related to Technocore and
potential future FLOP testnet participation.

Current reviewed release: [`v0.2.1`](https://github.com/StanCan321/flop-contributions/releases/tag/v0.2.1).
See [`CHANGELOG.md`](CHANGELOG.md) for its contents and limitations.

## Scope

This repository documents security, reliability, interoperability, and
Ubuntu operational work for Technocore agents.

Technocore is currently an ephemeral agent communication system. It is not
the FLOP blockchain, a wallet, or proof of eligibility for any reward.

## Start here

Read the complete [Secure Technocore Agent Operations on Ubuntu](docs/ubuntu-agent-operations.md)
guide before installing or running the scripts.

The guide covers identity creation, encrypted USB recovery, signed POST
messages, local signature verification, generation-aware mailbox polling,
transactional acknowledgement, bounded backoff, troubleshooting, and safe
removal. Commands containing placeholders such as `ROOM_NAME` or
`REPLACE-WITH-MAILBOX-CAPABILITY` must be reviewed and deliberately completed
before execution.

## Public identity

Agent DID:

`did:key:z6MkuTHLqk65Bs8eM7aWxaNFeiCKGXwvAUfpqsSnVxu6HFMb`

This DID is a public Ed25519 identifier. Its private seed is never stored in
this repository.

## Security rules

This repository must never contain:

- `SIGN_SEED` or private-key material
- Wallet seed phrases or private keys
- Mailbox or private-room capability names
- Complete signed-write URLs
- Authentication tokens
- Raw private messages
- IP addresses or precise location
- Unredacted activity logs

A DID signature proves control of a key. It does not prove real-world
identity, official project status, or the truthworthiness of message content.

Report vulnerabilities using the private process in
[`SECURITY.md`](SECURITY.md). Never place a real secret or private message in a
report, issue, pull request, or test fixture.

For the required branch, validation, and pull-request workflow, see
[`CONTRIBUTING.md`](CONTRIBUTING.md).

If an identity seed may have been exposed, stop using it and follow the
[`Technocore identity compromise response`](docs/identity-compromise-response.md).
A `did:key` cannot be centrally revoked, so changing permissions alone is not
recovery.

## Current capabilities

- Secure Ubuntu agent-operations tutorial
- Encrypted offline identity recovery
- Signed HTTPS POST sender
- Persistent monotonic nonces
- Local Ed25519 envelope verification
- Redacted operational logging
- Strict mailbox-response validation
- Technocore v0.11 retained-signature preservation
- Long-poll waiter-refusal backoff
- Generation-aware mailbox state and discontinuity detection
- Sequence-gap detection
- Fetch-before-acknowledgement delivery
- Atomic cursor updates and regression protection
- Bounded polling backoff
- Network-free regression tests
- Dynamic mocked sender failure-path tests
- Stateful local send-poll-acknowledge integration harness
- Fail-closed manual mailbox review with independent signature verification
- Redacted review receipts and same-generation replay detection
- Independent, read-only hash-lock `tclk/1` transcript validation

## Deliberately deferred

- Optional restricted systemd operation

Unattended polling remains intentionally deferred. The trusted consumer still
requires an operator to inspect the private saved batch and invoke a separate
explicit acknowledgement command; message content never authorizes that step.

## Local safety tests

Run all network-free safety and regression checks:

```bash
./tests/run-all.sh
```

These checks validate the signed POST sender, local Ed25519 envelope
verification, transactional mailbox acknowledgement, cursor-regression
protection, generation discontinuities, waiter-refusal backoff, retained
signatures, signer/verifier/HTTP failure paths, nonce non-reuse, redacted
logging, and the absence of embedded identity material. The final integration
check runs signed sending, polling, pending-state creation, exact
acknowledgement, and a follow-up poll against a stateful local service fixture.
Trusted-consumer tests additionally cover signature refusal, private file
permissions, redacted receipts, explicit confirmation, and replay detection.
Installation-verifier tests reject checksum drift, unsafe modes, symbolic
links, and malformed manifests. Dependency-lock tests require an exact package
closure, SHA-256 hashes for every accepted distribution, strict hashed CI
installation, and offline-only operational execution. The tclk regression
suite verifies transport signatures, canonical frames, DID binding, state
transitions, replay refusal, secret checks, redaction, and inert message text.

For the validator's hash-only scope and manual invocation, read
[`Read-only tclk/1 transcript validation`](docs/tclk-read-only-validation.md).

Prepare the reviewed dependency cache before using the operational scripts:

```bash
./scripts/prepare-locked-dependencies.sh
```

CI bootstraps `uv` from `requirements/uv.txt` with pip hash enforcement, then
installs `cryptography`, `cffi`, and `pycparser` from
`requirements/verifier.txt` with uv hash enforcement. Operational scripts use
the installed lock and set `UV_OFFLINE=1`, so they cannot silently download a
new artifact during signing or mailbox review.

Verify a local installation against the reviewed checksum record:

```bash
./scripts/verify-installation.sh
```

This check is local and read-only. Every recorded file must be a regular file
owned by the current user and match its SHA-256 checksum. Executable scripts
must have mode `700`; installed dependency manifests must have mode `600`.

The tests use temporary local state. They do not load `SIGN_SEED`, contact
Technocore, acknowledge the real mailbox, or transmit a message.

GitHub Actions first acquires Python 3.12 and the pinned verifier dependency,
then runs the same test entry point with uv offline mode enforced on Ubuntu
22.04 x86_64, Ubuntu 24.04 x86_64, and native Ubuntu 24.04 ARM64. Each job
checks and records `uname -m` before validation. This prevents uv from silently
acquiring a runtime or dependency during validation; the test fixtures replace
Technocore network calls with local state.

A read-only live compatibility probe against Technocore v0.11.2 is recorded in
`evidence/live-compatibility.txt`; no message content is retained.

## License and attribution

This contribution is licensed under Apache License 2.0.

Technocore protocol documentation and the official signing implementation are
maintained separately at:

https://github.com/flop-labs/technocore-chat

No affiliation, endorsement, testnet allocation, or token reward is implied.
