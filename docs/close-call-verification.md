# Offline Close Call verification

`scripts/verify-close-call.py` verifies a previously downloaded Close Call
package and five complete Technocore referee-room exports without contacting a
network or changing any state.

It fails closed unless:

- the supplied manifest has the exact reviewed SHA-256;
- every listed package artifact is a regular, non-symbolic-link file with the
  recorded size and SHA-256;
- `contest.json` names the expected contest and five distinct referee rooms;
- every export is complete from sequence 1, newline-terminated, signed by one
  Ed25519 `did:key`, and contains only the message types assigned to that room;
- the first price-room message is the signed seed binding the contest, package
  hash and referee-room list;
- sweep numbers are contiguous and every referee room publishes the same file
  commitment for each sweep; and
- a final message, if present, is the final price-room record.

Example using files captured separately by an operator:

```bash
UV_OFFLINE=1 uv run --python 3.12 \
  --with-requirements requirements/verifier.txt \
  scripts/verify-close-call.py \
  --package REVIEWED_PACKAGE_DIRECTORY \
  --expected-manifest-sha256 REVIEWED_64_HEX_SHA256 \
  --contest-id close-1 \
  --room-export d-close1-flow=FLOW_EXPORT.jsonl \
  --room-export d-close1-state=STATE_EXPORT.jsonl \
  --room-export d-close1-price=PRICE_EXPORT.jsonl \
  --room-export d-close1-positions=POSITIONS_EXPORT.jsonl \
  --room-export d-close1-pnl=PNL_EXPORT.jsonl
```

The report contains hashes, counts and sweep coverage, never message bodies or
the referee DID itself.

## Limits

This verifier does not download files, execute the contest fold, register an
owner, sign or post messages, trade, acknowledge anything, or claim a prize.
It cannot recover mint or trade identifiers omitted from the public referee
summaries. A published hash proves nothing about the unavailable sweep-file
bytes until those bytes are obtained and independently checked. Signature
verification proves control of the referee key, not organizer identity,
economic fairness, eligibility, payment, or future token value.
