# Pinned Technocore signer

Source: [flop-labs/technocore-chat scripts/sign.py](https://github.com/flop-labs/technocore-chat/blob/1de76f7e1919ae50714a87df3ad8a5dc590ef60a/scripts/sign.py)

- Upstream commit: `1de76f7e1919ae50714a87df3ad8a5dc590ef60a`
- Original SHA-256: `667e3d6cf48301d1b43f44c9b328d73ec1dbf413ddc89fcb740baf86f6406c15`
- Vendored SHA-256: `fe742f2ac22cebab80d8b3cd3cd8987d68709c6929ac315fee0b85dff9f92a2a`
- License: Apache-2.0; see the repository LICENSE and NOTICE.

Modification by StanCan321: the PEP 723 dependency is pinned from
`cryptography` to `cryptography==50.0.1`. No signing or key-derivation logic
was changed. This is the historical signer used by the reviewed sender, not a
claim that the latest upstream delegation commands are supported.

Upstream's docstring describes legacy signed GET routes. Do not use those
routes: this repository's sender uses signed POST and preflight verification.
The signer itself makes no network requests. Its legacy passphrase fallback
is preserved for compatibility, but the tutorial requires a random 64-hex seed.
Never supply an operational seed on a command line or use keygen over an
existing identity. Prepare hash-locked dependencies before operational use.

The installer verifies the vendored digest, requires an owned mode-700 target
directory, refuses a different existing signer, and never creates an identity.
Digest verification detects accidental drift, not malicious replacement of
both code and constants; review and trust the repository revision first.
