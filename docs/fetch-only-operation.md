# Restricted unattended fetch-and-save

Approved policy: periodically fetch the configured mailbox, save one private
batch, then pause. A human must review and explicitly acknowledge it. This is
not unattended consumption. No message can authorize a reply, shell command,
URL visit, signing operation, acknowledgement, or settlement.

The user timer checks every five minutes with up to 30 seconds of jitter.
There is one poll per activation; transient HTTP failures wait for the next
interval. Terminal failures, crashes, and saved batches leave
`~/flop/mailbox.fetch.halted`, which prevents further network polling. Pending
or saved batches also prevent polling. No login linger is enabled: the timer
depends on the user's service manager being available.

## Install and enable

First run the full offline test suite and installed-file integrity check. Use
the existing configured mailbox; do not create or change identities here.
From the repository root:

```bash
install -m 700 scripts/fetch-mailbox-once.py "$HOME/technocore-agent/fetch-mailbox-once.py"
mkdir -p "$HOME/.config/systemd/user"
install -m 644 systemd/technocore-fetch.service systemd/technocore-fetch.timer "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now technocore-fetch.timer
systemctl --user status technocore-fetch.timer
```

The service limits output-file size to 16 MiB, runtime to 60 seconds, and
writes to the private state directory and temporary files. It hides the seed
environment file and curl configuration, sets restrictive permissions, and
logs only fixed status messages. Raw poll output goes to a mode-600 file;
poll errors are not sent to the journal. This protects against accidental
disclosure, not a hostile process running as the same Unix user.

## Review, acknowledge, and explicitly resume

Stop the timer before manual state operations. Do not run manual polling
concurrently with the fetch service.

```bash
systemctl --user stop technocore-fetch.timer technocore-fetch.service
"$HOME/technocore-agent/review-mailbox.sh"
```

Follow the tutorial's manual inspection and exact reviewed-acknowledgement
procedure. Never acknowledge a missing, incomplete, or rejected batch. If a
failure or crash left pending state without a saved batch, use the tutorial's
deliberate recovery procedure; do not delete pending state blindly.

After successful manual acknowledgement, confirm both `mailbox.pending` and
`mailbox.batch.json` are absent. Inspect and resolve any error first. Only then
remove the fixed pause marker and resume:

```bash
test ! -e "$HOME/flop/mailbox.pending" &&
test ! -e "$HOME/flop/mailbox.batch.json" &&
rm -f -- "$HOME/flop/mailbox.fetch.halted" &&
systemctl --user start technocore-fetch.timer
```

Retention: keep the single unacknowledged batch until deliberately processed;
never rotate it automatically. The existing reviewed-acknowledgement command
removes the saved batch and retains a redacted receipt. Crash remnants named
`.mailbox.fetch.*` are private and require manual recovery review before
deletion. No automated private-data deletion or receipt-retention change is
introduced. Inspect service failures with `systemctl --user status`; this
timer does not configure a separate notification service.

Disable permanently with `systemctl --user disable --now technocore-fetch.timer`
and stop any active fetch using `systemctl --user stop technocore-fetch.service`.
