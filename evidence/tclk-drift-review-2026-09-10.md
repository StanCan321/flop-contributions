# Scoped tclk drift review — 2026-09-10

Range: `1459b78e3b981bbac67f845784c885b3b1ad85ba` through
`5cc4ab93efbc8999a3a7e1471b639deca25998ea` in
[flop-labs/tclk](https://github.com/flop-labs/tclk/compare/1459b78e3b981bbac67f845784c885b3b1ad85ba...5cc4ab93efbc8999a3a7e1471b639deca25998ea).
Twelve commits affect 41 files. This is a scoped compatibility review, not a
security audit of every changed source, dependency, example, or MCP handler.

`git diff --exit-code OLD..NEW -- tests/vectors.test.ts` passed: vector bytes
are unchanged. SHA-256 remains
`c60f109ba26547c6be0795b0eb66a861a96a7d68a36885a28f318e69a1cebb96`.

## Relevant changes and disposition

| Area | Observed upstream change | Companion disposition |
| --- | --- | --- |
| Frames and machine | Heartbeats, optional reveal/refund references, late-lock refusal, receipt consistency | Previously incorporated in the restricted hash-lock validator and covered by local tests |
| Rail identifiers | Registry/aliases; normalized matching while preserving signed historical bytes | Local validator still uses exact membership: alias-only matches fail closed |
| Transport records | Room-bound signatures and venue timestamps; decimal-string nonces supported | Separate cross-room auditor exists, but shared local transport verification still requires integer nonces |
| Decode boundaries | Frame-size cap and corrected schema restrictions | Local decoder has a 4096-character cap and strict field validation; no blanket schema-conformance claim |
| Point locks/adaptors | Reject out-of-range scalars and zero extracted witnesses | Unsupported locally; this release does not enable point locks or settlement |
| MCP/export | Exact string nonce posting and different window/export refusal policies | No adoption of upstream MCP as an operational dependency |

Inspected the relevant specification, frame/machine/rail/hex/adaptor/note-code
diffs, transport-record parsing, and signing/client changes. Did not run or
certify the complete upstream TypeScript suite in this review.

## Confirmed local limitations

A synthetic accepted contract offering `paperrail` rejected a `paper` lock
without advancing state. Upstream's normalized membership accepts that alias
relationship. Local `verify_transport` rejects a decimal-string nonce at its
type gate; upstream record parsing preserves it. These are compatibility
restrictions, not proof that a rejected transcript is malicious. Never rewrite
signed offer bytes to work around them.

## Decision

Retain the existing reviewed commit and hash in the drift checker. A passing
vector hash alone cannot justify promoting a broader compatibility baseline.
The checker will continue to fail on this commit difference; that failure is
now reviewed and explained, not an unnoticed maintenance failure. Implementing
and independently testing alias matching and string-nonce handling would be a
separate compatibility change before reconsidering the baseline.

Full local offline suite and installed-file checks passed for this release.
No live Technocore read, write, acknowledgement, or settlement was performed
for this drift review or release preparation.
