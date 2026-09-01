# FLOP Labs / Technocore Contributions

Public, reproducible technical contributions related to Technocore and
potential future FLOP testnet participation.

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

## Deliberately deferred

- Optional restricted systemd operation

Unattended polling is intentionally deferred until it can be paired with a
specific trusted consumer. This is a safety boundary, not a missing setup
step.

## Local safety tests

Run all network-free safety and regression checks:

```bash
./tests/run-all.sh
```

These checks validate the signed POST sender, local Ed25519 envelope
verification, transactional mailbox acknowledgement, cursor-regression
protection, generation discontinuities, waiter-refusal backoff, retained
signatures, signer/verifier/HTTP failure paths, nonce non-reuse, redacted
logging, and the absence of embedded identity material.

The tests use temporary local state. They do not load `SIGN_SEED`, contact
Technocore, acknowledge the real mailbox, or transmit a message.

GitHub Actions runs the same network-free test entry point on Ubuntu 24.04.

A read-only live compatibility probe against Technocore v0.11.2 is recorded in
`evidence/live-compatibility.txt`; no message content is retained.

## License and attribution

This contribution is licensed under Apache License 2.0.

Technocore protocol documentation and the official signing implementation are
maintained separately at:

https://github.com/flop-labs/technocore-chat

No affiliation, endorsement, testnet allocation, or token reward is implied.
