#!/usr/bin/env python3
"""Fetch and save only. Never review, acknowledge, sign, or execute content."""
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


def main():
    os.umask(0o077)
    home = Path.home()
    state = home / 'flop'
    if state.is_symlink():
        raise ValueError('unsafe state')
    state.mkdir(mode=0o700, exist_ok=True)
    info = state.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('unsafe state')
    fd = os.open(state / 'mailbox.fetch.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        halt = state / 'mailbox.fetch.halted'
        batch = state / 'mailbox.batch.json'
        # Existence includes broken symlinks: never overwrite retained evidence.
        if any(os.path.lexists(p) for p in (halt, batch, state / 'mailbox.pending')):
            print('Paused: operator review required.')
            return
        for name in ('mailbox.txt', 'mailbox.cursor', 'mailbox.poll.lock'):
            if (state / name).is_symlink():
                raise ValueError('unsafe state file')
        # Persist pause BEFORE fetching. Crashes and terminal failures stay paused.
        with halt.open('x') as out:
            out.write('Operator review required before resuming fetch.\n')
        poll = home / 'technocore-agent' / 'poll-mailbox.sh'
        if poll.is_symlink() or not poll.is_file():
            raise ValueError('unsafe poller')
        temp_fd, temp_name = tempfile.mkstemp(prefix='.mailbox.fetch.', dir=state)
        try:
            with os.fdopen(temp_fd, 'wb') as out:
                result = subprocess.run(
                    [str(poll)], stdout=out, stderr=subprocess.DEVNULL,
                    timeout=45, env={'HOME': str(home), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                )
                out.flush()
                os.fsync(out.fileno())
            if result.returncode == 75 and not os.path.lexists(state / 'mailbox.pending'):
                halt.unlink()
                print('Transient failure: retry on next timer interval.')
                return
            if result.returncode != 0:
                raise ValueError('poll failed')
            with open(temp_name, encoding='utf-8') as source:
                data = json.load(source)
            if (not isinstance(data, dict) or data.get('status') != 'ok'
                    or type(data.get('count')) is not int or data['count'] < 0):
                raise ValueError('invalid batch')
            if data['count'] == 0 and not os.path.lexists(state / 'mailbox.pending'):
                halt.unlink()
                print('No pending messages.')
                return
            # Exclusive publication: do not replace a concurrent manual saved batch.
            os.link(temp_name, batch)
            print('Batch saved privately. Fetch paused for manual review and acknowledgement.')
        finally:
            os.unlink(temp_name)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        print('Fetch stopped. Inspect private state before explicitly resuming.')
        raise SystemExit(1)
