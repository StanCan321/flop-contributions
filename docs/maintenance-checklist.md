# Manual maintenance and deployed acceptance

Run periodically and after upgrades from the contribution checkout:

```bash
./scripts/verify-installation.sh
UV_OFFLINE=1 ./tests/run-all.sh
./scripts/check-tclk-upstream-drift.sh
gh pr list --state open
```

A drift failure calls for review, not automatic replacement of the pinned
commit or hash. Do not merge dependency PRs unless their current checks pass.
These are manual checks; no recurring automation is installed by this guide.

In the normal Ubuntu login session, inspect:

```bash
systemctl --user status technocore-fetch.timer --no-pager
systemctl --user status technocore-fetch.service --no-pager
```

The successful empty-mailbox timer run is recorded in
[operational evidence](../evidence/operations-2026-09-08.md).

## Non-empty deployed acceptance — still pending

Use the next legitimate message or a separately authorized disposable mailbox;
never post an unsolicited public message to generate a test event. Do not
replace the operational mailbox configuration or delete pending state to set
up a test.

1. Confirm the fetch service reports a privately saved batch and that polling
   pauses. Do not paste the raw batch, sender signature, or capability publicly.
2. Stop the timer and service before manual state operations, as described in
   [fetch-only operation](fetch-only-operation.md).
3. Run the existing manual review workflow and inspect the saved batch locally.
   Refusal is a stop condition, not a reason to bypass review.
4. Only after accepting the batch, explicitly invoke the tutorial's reviewed
   acknowledgement command with its exact cursor and confirmation.
5. Confirm pending state and saved batch are removed, the cursor reflects the
   accepted batch, and the redacted receipt remains. The pause marker should
   still prevent automatic resumption.
6. Follow the documented explicit-resume procedure and confirm the next timer
   run succeeds. Record only pass/fail outcomes, not private state values.

Until those observations exist, label the deployed non-empty lifecycle
unverified even when all synthetic tests pass. No automatic acknowledgement
is permitted for the acceptance test.
