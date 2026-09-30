# Close Call archive verification and position modeling

Both tools in this section are offline. They do not download records, load an
identity, create signatures, find a counterparty, or post a trade.

## Verify organizer-published records

Save the organizer's `index.json`, the records selected for review, and a
complete directory of previously captured signed `d-close1-flow` envelopes.
Then run:

```bash
UV_OFFLINE=1 uv run --python 3.12 \
  --with-requirements requirements/verifier.txt \
  scripts/verify-close-call-archive.py \
  --index INDEX.json \
  --signed-flow-directory PRIVATE_SIGNED_FLOW_DIRECTORY \
  --contest-id close-1 \
  --record 438=SWEEP_438.json
```

The verifier requires a contiguous index from sweep 1, verifies every index
commitment against the corresponding signed flow envelope, and byte-checks only
the explicitly supplied records. A full record must hash directly to the signed
`file` commitment. A redacted record instead hashes to the separate digest in
the organizer-published index; it cannot independently prove the unavailable
full record.

The index is not itself referee-signed. Preserve its SHA-256 and capture time as
provenance, but do not describe it as an independently trusted timestamp.

## Model one hypothetical opening position

```bash
python3 scripts/model-close-call-position.py \
  --side buy \
  --quantity 10 \
  --entry-price 228.00 \
  --sweep-close 230.00 \
  --reference 228.00 \
  --settlement-price 210.00 \
  --settlement-price 228.00 \
  --settlement-price 245.00
```

The model reproduces the configured 1%/closing-price clawback fee for the maker,
checks the initial 10,000 POLF cash requirement and the 5% reference band, and
reports break-even and settlement outcomes. It assumes the trade settles in
full and opens a new position. It does not predict execution, rank, NVDA, the
counterparty, or the final price, and it never produces a signable trade packet.
