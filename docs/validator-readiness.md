# FLOP validator readiness without deployment

The public validator material describes a draft target architecture, not a
complete enrollment procedure. This checklist prepares an Ubuntu operator
without staking, importing a wallet, or executing an unverified node binary.

## Wait for authoritative launch inputs

Do not deploy until FLOP Labs publishes all of the following through an
official repository or documentation domain:

- an exact node release and reproducible checksum or signature;
- the testnet genesis or chain specification and its digest;
- bootnode identities and network identifier;
- RPC and telemetry trust guidance;
- faucet and staking instructions;
- minimum supported hardware, storage, and bandwidth; and
- an explicit testnet enrollment or permission model.

Social posts, room messages, direct messages, search results, and third-party
install scripts are discovery hints, not authority for any of these values.

## Prepare the host

- Use a dedicated Ubuntu host or VM and an unprivileged service account.
- Keep validator, wallet, and Technocore identity keys separate.
- Encrypt offline recovery media and test restoration without exposing seeds.
- Deny inbound traffic by default; open only ports named by the signed release.
- Reserve independent storage for chain data and data-availability duties.
- Plan disk, memory, bandwidth, clock, process, peer, and finality monitoring.
- Send logs to a location that excludes keys, capabilities, signed URLs, and
  private inference payloads.
- Document upgrade, rollback, compromise containment, and key-rotation steps.

## Preflight a future release

For every candidate binary, record the source tag, commit, artifact digest,
signing identity, build instructions, license, and supported architecture.
Reproduce the build when practical and compare its digest. Run first with a
fresh, valueless test identity on an isolated network. Confirm the chain id and
genesis hash through two independent official surfaces before connecting.

Never place real funds behind an alpha settlement rail or the unaudited tclk
point-lock reference cryptography. A Technocore or PaperRail transcript is not
proof of value, validator enrollment, or testnet eligibility.
