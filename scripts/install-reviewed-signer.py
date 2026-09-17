#!/usr/bin/env python3
"""Install the pinned signer without replacing an existing different file."""
import hashlib
import os
from pathlib import Path
import stat
import sys

EXPECTED_SHA256 = "fe742f2ac22cebab80d8b3cd3cd8987d68709c6929ac315fee0b85dff9f92a2a"
SOURCE = Path(__file__).resolve().parents[1] / "vendor/technocore/sign.py"


def install(directory):
    payload = SOURCE.read_bytes()
    if hashlib.sha256(payload).hexdigest() != EXPECTED_SHA256:
        raise ValueError("vendored signer checksum mismatch")
    # Pin the directory descriptor; refuse symlinks and group/other access.
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("agent directory must be owned by you with mode 700")
        try:
            existing = os.open("sign.py", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                               dir_fd=fd)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            with os.fdopen(existing, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o700):
                    raise ValueError("existing signer must be a regular owned file with mode 700")
                if stream.read(len(payload) + 1) != payload:
                    raise ValueError("existing signer differs; refusing to overwrite it")
            print("Reviewed signer already installed; unchanged.")
            return
        out = os.open("sign.py", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o700, dir_fd=fd)
        try:
            with os.fdopen(out, "wb") as stream:
                os.fchmod(stream.fileno(), 0o700)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            os.unlink("sign.py", dir_fd=fd)
            raise
        os.fsync(fd)
        print("Reviewed signer installed with mode 700; no identity created.")
    finally:
        os.close(fd)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 scripts/install-reviewed-signer.py AGENT_DIRECTORY")
    try:
        install(sys.argv[1])
    except (OSError, ValueError) as error:
        sys.exit(f"ERROR: {error}")
