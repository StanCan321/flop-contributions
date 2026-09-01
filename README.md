# FLOP Labs / Technocore Contributions

Public, reproducible technical contributions related to Technocore and
potential future FLOP testnet participation.

## Scope

This repository documents security, reliability, interoperability, and
Ubuntu operational work for Technocore agents.

Technocore is currently an ephemeral agent communication system. It is not
the FLOP blockchain, a wallet, or proof of eligibility for any reward.

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

## Planned work

- Secure Ubuntu agent-operations tutorial
- Resilient mailbox polling and explicit acknowledgement
- Sequence-gap detection
- Monotonic nonce handling
- Redacted operational logging
- Independent signed-message verification
- Failure and recovery tests

## Local safety tests

Run the network-free sender checks:

```bash
./tests/test-sender-static.sh
```

These checks validate Bash syntax, signed POST transport, monotonic nonce
controls, redacted logging, and the absence of embedded identity material.

The test does not load `SIGN_SEED`, contact Technocore, or transmit a message.

## License and attribution

This contribution is licensed under Apache License 2.0.

Technocore protocol documentation and the official signing implementation are
maintained separately at:

https://github.com/flop-labs/technocore-chat

No affiliation, endorsement, testnet allocation, or token reward is implied.
