## Summary

<!-- Describe the narrowly scoped change and why it is needed. -->

## Safety boundary

<!--
Explain whether this changes identity handling, signing, network transport,
mailbox state, acknowledgement, logging, or message review. State explicitly
when the existing boundary is unchanged.
-->

## Validation

<!-- List the exact local checks performed and their results. -->

## External activity

<!--
State whether this work read from or wrote to Technocore. For any authorized
external activity, describe only the operation and redacted result. Never paste
a capability, signed URL, private message, token, seed, or precise IP address.
-->

- [ ] No real secret, capability, private message, or unredacted activity log
      is included.
- [ ] Tests use only synthetic identity and message fixtures.
- [ ] `./tests/run-all.sh` passes locally, or the reason it could not run is
      documented above.
- [ ] `git diff --check` passes.
- [ ] The change does not enable unattended consumption, automatic replies,
      URL opening, or message-driven tool execution unless that expansion is
      explicitly identified and justified above.
- [ ] The change makes no unsupported claim of FLOP affiliation, eligibility,
      allocation, or reward.
