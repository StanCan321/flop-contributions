# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| `0.1.x` | Yes |
| Current `main` branch | Yes, for upcoming fixes |
| Older untagged commits and copied scripts | No |

## Report a vulnerability privately

Use GitHub's private vulnerability reporting form:

<https://github.com/StanCan321/flop-contributions/security/advisories/new>

Do not open a public issue for a vulnerability that could expose identity
material, mailbox capabilities, private messages, or a working exploit.

Include only the information needed to reproduce the problem safely:

- affected file and commit;
- security impact;
- sanitized reproduction steps using temporary local state;
- expected and observed behavior; and
- a suggested correction, if available.

Reports will be acknowledged and evaluated as availability permits. No reward,
bounty, eligibility, or disclosure deadline is promised.

## Never submit secrets

Do not include any of the following in a report, issue, pull request, log, or
test fixture:

- `SIGN_SEED`, seed phrases, or private keys;
- GitHub tokens or other credentials;
- mailbox or private-room capability names;
- complete signed-write URLs;
- raw private messages;
- unredacted activity logs; or
- private IP addresses or precise location information.

If a real secret was exposed, stop using it and rotate or replace it where the
underlying system supports that operation. Do not send the exposed value again,
including through the private reporting form.

## Scope

This policy covers the scripts, tests, workflow, and documentation maintained
in this repository.

Vulnerabilities in the hosted Technocore service or its upstream implementation
belong in the upstream project's security process:

<https://github.com/flop-labs/technocore-chat/blob/main/SECURITY.md>

Questions about FLOP eligibility, rewards, wallets, or testnet allocation are
not security reports for this repository.

## Safe research

Use the disposable local fixtures in `tests/` whenever possible. Do not access
another person's mailbox or identity material, test against private rooms
without authorization, degrade the hosted service, or publish exploit details
before the affected maintainer has had a reasonable opportunity to respond.
