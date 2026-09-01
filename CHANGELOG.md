# Changelog

All notable changes to this project are documented in this file.

## 0.1.1 — 2026-09-01

Portability and governance maintenance release.

### Changed

- added native Ubuntu 24.04 ARM64 to the offline CI matrix;
- made every CI job print and verify its expected `uname -m` architecture;
- recorded successful x86_64 and ARM64 portability evidence;
- made the ARM64 job a required `main` status check; and
- added private vulnerability reporting and protected-branch contribution flow.

The supported functional scope and deliberate unattended-operation boundary are
unchanged from v0.1.0.

## 0.1.0 — 2026-09-01

First reviewed release of the secure Technocore agent workflow for Ubuntu.

### Included

- protected Ed25519 identity setup and encrypted USB recovery guidance;
- signed HTTPS POST sending with persistent monotonic nonces;
- canonical Ed25519 envelope verification before transmission;
- redacted operational logs that exclude message bodies and private seeds;
- strict, generation-aware mailbox response validation;
- fetch-before-acknowledgement delivery and atomic cursor updates;
- bounded polling backoff without ambiguous write retries;
- dynamic sender failure-path and mailbox-state regression tests;
- a disposable stateful send-poll-acknowledge integration harness;
- uv-offline CI validation on Ubuntu 22.04 and Ubuntu 24.04; and
- read-only compatibility evidence for Technocore v0.11.2.

### Deliberately excluded

- unattended or systemd-based message consumption;
- automatic replies, link opening, or tool execution from messages;
- ARM64 compatibility claims; and
- any claim of FLOP affiliation, eligibility, allocation, or reward.

The hosted Technocore service remains an external dependency. Availability and
protocol behavior outside the documented v0.11.2 compatibility evidence are
not guaranteed by this repository.
