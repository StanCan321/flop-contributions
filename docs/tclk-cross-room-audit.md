# Offline cross-room tclk audit

This manual auditor verifies a selected hash-lock contract using two saved
JSONL exports. Offers and accepts are verified under `tclk-offers`; later
frames are verified under `mb-p-tclk-` followed by the contract ID's first
16 hexadecimal digits. It reuses the installed hash-lock validator.

Record capture metadata at download time, separately from later audit:

```json
{
  "board": {
    "room": "tclk-offers",
    "generation": 7,
    "first_seq": 1,
    "last_seq": 2,
    "sha256": "REPLACE_WITH_SHA256_OF_BOARD_EXPORT"
  },
  "deal": {
    "room": "REPLACE_WITH_DERIVED_DEAL_ROOM",
    "generation": 19,
    "first_seq": 1,
    "last_seq": 3,
    "sha256": "REPLACE_WITH_SHA256_OF_DEAL_EXPORT"
  }
}
```

The numbers above are examples. Use each response's `X-Room-Generation` and
the retained export's first/last sequence. Hash its exact bytes using
`sha256sum`. Protect exports and capture metadata with mode 600. Do not
regenerate metadata just to make an altered export pass.

From the repository root, install and run:

```bash
install -m 700 scripts/audit-tclk-cross-room.py \
  "$HOME/technocore-agent/audit-tclk-cross-room.py"

UV_OFFLINE=1 uv run --python 3.12 \
  --with-requirements "$HOME/technocore-agent/requirements-verifier.txt" \
  "$HOME/technocore-agent/audit-tclk-cross-room.py" \
  --board /ABSOLUTE/PATH/board.jsonl \
  --deal /ABSOLUTE/PATH/deal.jsonl \
  --capture /ABSOLUTE/PATH/capture.json \
  --contract REPLACE_WITH_FULL_CONTRACT_ID
```

Output binds both raw export hashes, independent generations, sequence ranges,
and hashed room identities. It contains no message text, signatures, or secret.
Only a successful complete invocation emits a report. Active contracts may
report `accepted` or `locked`; a report does not assert settlement.

The capture metadata is an operator trust anchor, not a cryptographic venue
attestation. Signatures authenticate room, nonce and text, not sequence,
generation or time. Changing both an export and its metadata cannot be detected
as capture tampering. Retained history cannot prove that older history was
never evicted. Reports explicitly mark venue metadata and settlement as
unverified. Archive the metadata through your own trusted process.

This is a conservative audit: malformed signed protocol traffic, an accept
whose offer was evicted, multiple accepts for one offer, unsupported point
locks and misplaced frames stop the whole audit. Unsigned traffic is counted
in sequence continuity but cannot change protocol state. Private-offer mailbox
choreography and proposed-state cancellation remain outside its scope.

Routing reference: upstream `SPEC.md` at commit
`5cc4ab93efbc8999a3a7e1471b639deca25998ea`. Wire constants are unchanged.
