# Contributing

Contributions should preserve the repository's fail-closed behavior and avoid
placing private Technocore state in Git history.

## Before editing

1. Confirm that the checkout is clean and current:

   ```bash
   git switch main
   git pull --ff-only origin main
   git status --short --branch
   ```

2. Create a narrowly scoped branch. Do not work directly on `main`:

   ```bash
   git switch -c TYPE/SHORT-DESCRIPTION
   ```

3. Read [`SECURITY.md`](SECURITY.md). Use private vulnerability reporting for
   security defects; never include real capabilities, seeds, private messages,
   tokens, or complete signed-write URLs in an issue or pull request.

## Validate changes

Run the complete local suite from the repository root:

```bash
./tests/run-all.sh
git diff --check
```

The suite is network-free after its pinned Python dependency is available. It
must not poll or acknowledge a real mailbox, transmit a message, load a real
`SIGN_SEED`, or open a URL from message content.

Review the staged patch before committing:

```bash
git add PATHS-YOU-REVIEWED
git diff --cached --check
git diff --cached
```

Use synthetic fixtures only. If a test needs identity material, generate a
temporary key inside a private temporary directory and delete it during test
cleanup.

## Pull requests

Push the topic branch and open a pull request against `main`. The repository
requires the following checks against the current branch state:

- `test (ubuntu-22.04)`
- `test (ubuntu-24.04)`
- `test (ubuntu-24.04-arm)`

Resolve review conversations and update the branch if GitHub reports that it
is behind `main`. Merge only after all required checks pass. The repository
accepts squash merges only and automatically deletes merged topic branches.

Pull requests should state:

- what changed and why;
- the safety boundary affected by the change;
- the local validation performed; and
- whether any external Technocore read or write occurred.

Do not claim FLOP affiliation, eligibility, allocation, or reward.
