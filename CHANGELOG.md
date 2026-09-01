# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Changed

- enabled Dependabot alerts and security-update pull requests;
- added weekly, review-required GitHub Actions dependency updates;
- added a safety-focused pull-request template covering validation, external
  activity, private data, and unattended-operation boundaries;
- added a compromised-identity containment and replacement runbook; and
- recorded a fail-closed live availability check and three upstream security
  reviews without retaining private message data;
- recorded a single failed signed public-message attempt by hash, status, and
  reserved nonce without retaining its body or signature.

## 0.2.1 — 2026-09-01

Integrity and governance maintenance release.

### Added

- fail-closed verification of installed script ownership, modes, file types,
  and recorded checksums; and
- protected contribution, validation, and private-data handling guidance.

### Changed

- avoided duplicate branch-push and pull-request CI runs;
- canceled superseded workflow runs for the same branch or pull request; and
- aligned repository and ruleset configuration on squash-only merges with
  automatic topic-branch cleanup.

The v0.2.0 manual-consumption safety boundary is unchanged. No unattended
operation, automatic reply, link opening, or message-driven tool execution is
enabled by this release.

## 0.2.0 — 2026-09-01

Manual trusted-consumption release.

### Added

- a fail-closed, manually invoked mailbox review workflow;
- strict saved-batch schema, ownership, permission, sequence, and generation checks;
- independent Ed25519 verification of every retained message signature;
- explicit operator confirmation before transactional acknowledgement;
- redacted review receipts without message bodies, DIDs, signatures, or capabilities;
- same-generation signature replay detection against archived receipts; and
- offline regression coverage on Ubuntu 22.04, Ubuntu 24.04, and native ARM64.

### Safety boundary

- messages are treated as untrusted data and are never executed;
- URLs are counted for review but are never opened automatically;
- polling and acknowledgement remain separate manual actions;
- unattended consumption and automatic replies remain deliberately excluded; and
- this release makes no claim of FLOP affiliation, eligibility, allocation, or reward.

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
