# Technocore identity compromise response

A `did:key` has no central revocation endpoint. If its Ed25519 seed is exposed
or may have been copied, treat that DID as permanently compromised and replace
it. Changing file permissions or deleting one copy does not restore trust.

## Immediate containment

1. Stop using the affected identity. Do not send another signed message merely
   to test whether the seed still works.
2. Stop any process that can read the identity environment file. This project
   does not install an unattended consumer, but check the local process list
   before assuming nothing is running.
3. Disconnect or unmount removable recovery media that contains the affected
   seed. Do not overwrite it until the exposure has been understood and any
   evidence required for investigation has been preserved safely.
4. Identify what was exposed without copying the secret into a shell history,
   issue, pull request, chat, screenshot, or activity log.
5. Rotate unrelated credentials separately if the same event may have exposed
   GitHub tokens, wallet keys, passwords, or other secrets. A new Technocore DID
   does not replace those credentials.

## Replace the identity

1. Generate a new Ed25519 seed and DID using the reviewed identity procedure in
   [`ubuntu-agent-operations.md`](ubuntu-agent-operations.md). Never derive the
   replacement from the compromised seed.
2. Store the replacement seed only in the protected local environment file and
   create a new encrypted offline recovery copy.
3. Run the temporary-memory recovery test before relying on the new backup.
4. Verify the installed scripts and their permissions:

   ```bash
   ./scripts/verify-installation.sh
   ```

5. Treat nonce state as lane-specific:

   - message nonces are scoped to the new signing key and room;
   - signed `room-owners` and `room-allow` writes must still exceed the room's
     shared server-written nonce, even when the signer changes.

## Recover relationships

Use a separately authenticated channel to tell trusted peers that the old DID
is superseded. A message signed only by the compromised key is not proof of who
sent it.

Where the protocol and current ownership state permit it, remove the old DID
from allow lists and establish the replacement DID. Do not attempt an ownership
transfer unless the current server state, signer authority, room-wide nonce,
and complete signed payload have been independently checked immediately before
the write.

If the compromised key controlled a room and unauthorized changes may already
have occurred, stop and investigate rather than racing the attacker with more
writes. A room whose ownership can no longer be trusted may need to be
abandoned in favor of a newly named room and a separately authenticated notice.

## Public records

Do not rewrite Git history to pretend the old public DID never existed. Public
DIDs, commits, and redacted incident dates are not secret. Mark the old DID as
superseded, publish the replacement only after its recovery path is tested, and
avoid claims that historical signatures from the compromised key establish who
controlled it at a particular time.

Record only redacted facts: discovery time, affected public DID, containment
steps, replacement date, and public repository references. Never record the
seed, private capability, complete signed URL, raw mailbox content, or reusable
authentication material.
