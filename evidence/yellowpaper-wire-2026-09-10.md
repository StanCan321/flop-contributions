# Public wire-format reproduction — 2026-09-10

Source: [FLOP yellowpaper](https://github.com/flop-labs/yellowpaper/tree/3eaf2f25bc46a501df225cae4e4e991975f6b2a9),
v0.5.0 draft, commit `3eaf2f25bc46a501df225cae4e4e991975f6b2a9`.
Upstream text is CC BY 4.0. No upstream source or corpus is vendored here.

Read the public generator and its standalone compute-channel module before
executing. Reproduced the corpus with:

```bash
uv run --no-project --with jsonschema==4.23.0 python -B evidence/generate-wire-format-vectors.py --check
```

Result: `ok: evidence/wire-format-v1.json`. This was a one-off review environment,
not an added operational dependency or a fully hash-locked dependency closure.

Reviewed artifact SHA-256 values:

| Artifact under `evidence/` | SHA-256 |
| --- | --- |
| generate-wire-format-vectors.py | 9a79ed3ce0e0317965edc1c1c58ba921aaad771c3bc4340f542f738f04a5240d |
| compute-channel.py | 7a7ad29bffa6a9c3f143eb929225db858a5b9fe56374684f3a1b2d57e9047d28 |
| wire-format-v1.json | 80d4a7e70f984342eb474ae5285a17a6b9348eca887e1689b15e641922051d93 |
| wire-format-v1.schema.json | 9b3850293d65333cf2a26077cd364fecc7491986a83fddef9d546a010717f743 |

## Independent supplemental checks

From this companion checkout, against a separately obtained pinned upstream checkout:

```bash
python3 -B tests/check-yellowpaper-wire.py /path/to/pinned/yellowpaper
```

The checker hashes the imported public module and corpus before using them.
It performs 1,008 independent compact-integer encodings and upstream decode
round trips, checks public malformed compact cases and overflow rejection,
recomputes channel/task/leaf and policy hashes from published preimages, and
checks an FCC4 round trip plus all 311 strict truncations and trailing bytes.
All these checks passed. No reproducible gap was found in this bounded set,
so no upstream defect report was filed.

The reference decoder is still upstream code, not an independently implemented
full parser. The generator embeds signature bytes: reproducing them is NOT
cryptographic signature verification. No runtime rejection-site, quorum,
settlement, consensus, or full specification-conformance claim follows from
these tests. This check is manual and is not inserted into the network-free
suite because it needs a separately reviewed source checkout.

## Deployed mailbox status

The user service manager reports the operational fetch timer active and the
last fetch service result successful. Only existence checks were made on
private state: no pending batch, saved batch, or pause marker was present.
No mailbox content was read and no message or acknowledgement was sent.
The non-empty deployed lifecycle remains pending a separately authorized
disposable-room test or a legitimate incoming batch.
