# Maintenance review — 2026-09-12

## Operational read-only checks

- Fetch timer active; service Result=success and ExecMainStatus=0.
- All 15 installed files matched the existing checksum manifest and required modes.
- Identity file mode 600; private state directory mode 700; mailbox state files
  and activity log mode 600. Activity log was 4,142 bytes; no pruning performed.
- Agent directory mode 775, contrary to the tutorial's required 700. Individual
  file checks do not protect against replacement through a writable directory.
  Recommended remediation: confirm ownership and set this directory to 700.
  Deployment permissions were not changed during this read-only audit.
- No mailbox acknowledgement, message, identity change, or service restart.

## Compatibility tests

Added correctly signed decimal-string nonce rejection cases and rail-alias
rejections with unchanged contract state. These document current restrictions,
not upstream conformance. No production validator, pinned baseline, installed
script, or checksum manifest changed.

## Tutorial review scope and remaining gap

Corrected contradictory language about disabled polling: optional fetch-only
background operation is supported; unattended consumption remains disabled.
The guide still requires an independently reviewed sign.py, which is not shipped
in this repository. Therefore this is not a complete clean-machine installation
reproduction. A future reproducibility change must establish and pin a distributable
signer source before claiming an end-to-end fresh-install result. No existing
identity should be regenerated to test the tutorial.

The local PR template now follows What / Why / Checks while retaining its
security and external-activity disclosures.
