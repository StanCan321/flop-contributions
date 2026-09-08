#!/usr/bin/env python3
"""Disposable, network-free tests for the fetch-only supervisor."""
import os
from pathlib import Path
import subprocess
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/fetch-mailbox-once.py'
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    state = root / 'flop'
    state.mkdir(mode=0o700)
    agent = root / 'technocore-agent'
    agent.mkdir()
    poll = agent / 'poll-mailbox.sh'
    halt = state / 'mailbox.fetch.halted'
    batch = state / 'mailbox.batch.json'
    pending = state / 'mailbox.pending'
    cursor = state / 'mailbox.cursor'
    cursor.write_text('1')
    def run(body):
        poll.write_text('#!/bin/bash\nset -eu\n' + body)
        poll.chmod(0o700)
        return subprocess.run(['/usr/bin/python3', str(SCRIPT)], env={'HOME': str(root)},
                              capture_output=True, text=True)
    assert run('echo \'{"status":"ok","count":0}\'').returncode == 0
    assert not halt.exists() and not batch.exists()
    assert run('exit 75').returncode == 0 and not halt.exists()
    assert run('echo PRIVATE >&2; exit 4').returncode == 1 and halt.exists()
    assert 'PRIVATE' not in run('exit 99').stdout
    halt.unlink()
    pending.write_text('3')
    assert run('exit 99').returncode == 0
    pending.unlink()
    assert run('echo 3 > "$HOME/flop/mailbox.pending"\necho \'{"status":"ok","count":1,"messages":[{"text":"PRIVATE"}]}\'').returncode == 0
    assert halt.exists() and batch.exists() and pending.read_text().strip() == '3'
    assert batch.stat().st_mode & 0o777 == 0o600
    saved = batch.read_bytes()
    assert run('exit 99').returncode == 0 and batch.read_bytes() == saved
    pending.unlink()  # Simulate explicit manual acknowledgement and archive.
    batch.unlink()
    assert run('exit 99').returncode == 0  # Pause persists after acknowledgement.
    halt.unlink()
    assert run('echo invalid').returncode == 1 and halt.exists()
    halt.unlink()
    batch.symlink_to(root / 'missing')
    assert run('exit 99').returncode == 0 and batch.is_symlink()
    assert cursor.read_text() == '1'
print('PASS: fetch-only empty/retry/failure/pending/save/privacy/resume/symlink cases')
