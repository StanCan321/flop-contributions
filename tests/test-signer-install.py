#!/usr/bin/env python3
"""Offline fresh-directory signer installation; only disposable test identities."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts/install-reviewed-signer.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class SignerInstallation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent = Path(self.temp.name) / "agent"
        self.agent.mkdir(mode=0o700)

    def test_fresh_install_and_independent_signature(self):
        installer.install(self.agent)
        signer = self.agent / "sign.py"
        self.assertEqual(stat.S_IMODE(signer.stat().st_mode), 0o700)
        self.assertEqual(hashlib.sha256(signer.read_bytes()).hexdigest(),
                         installer.EXPECTED_SHA256)
        before = signer.stat().st_mtime_ns
        installer.install(self.agent)
        self.assertEqual(before, signer.stat().st_mtime_ns)
        # Do not source operational environment or use persistent identity state.
        env = {**os.environ, "HOME": self.temp.name, "SIGN_SEED": secrets.token_hex(32)}
        text = "  disposable\u200bUnicode café\nmessage  "
        result = subprocess.run([sys.executable, str(signer), "say", "test-room",
                                 "12345", text], env=env, capture_output=True,
                                text=True, check=True)
        did, sig = result.stdout.splitlines()
        envelope = dict(room="test-room", nonce="12345", text=text, did=did, sig=sig)
        verified = subprocess.run([sys.executable, str(ROOT / "scripts/verify-envelope.py")],
                                  input=json.dumps(envelope), env=env,
                                  capture_output=True, text=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        envelope["text"] = "tampered"
        rejected = subprocess.run([sys.executable, str(ROOT / "scripts/verify-envelope.py")],
                                  input=json.dumps(envelope), env=env,
                                  capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual([p.name for p in self.agent.iterdir()], ["sign.py"])

    def test_existing_different_file_unchanged(self):
        target = self.agent / "sign.py"
        target.write_text("existing signer")
        target.chmod(0o700)
        with self.assertRaises(ValueError):
            installer.install(self.agent)
        self.assertEqual(target.read_text(), "existing signer")

    def test_unsafe_directory(self):
        self.agent.chmod(0o775)
        with self.assertRaises(ValueError):
            installer.install(self.agent)
        self.assertFalse((self.agent / "sign.py").exists())

    def test_symlink_directory(self):
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.agent)
        with self.assertRaises(OSError):
            installer.install(link)

    def test_symlink_signer(self):
        target = Path(self.temp.name) / "original"
        target.write_text("unchanged")
        (self.agent / "sign.py").symlink_to(target)
        with self.assertRaises(OSError):
            installer.install(self.agent)
        self.assertEqual(target.read_text(), "unchanged")

    def test_unsafe_existing_mode(self):
        installer.install(self.agent)
        (self.agent / "sign.py").chmod(0o644)
        with self.assertRaises(ValueError):
            installer.install(self.agent)

    def test_tampered_vendor_refused(self):
        altered = Path(self.temp.name) / "altered"
        altered.write_text("not the reviewed signer")
        with mock.patch.object(installer, "SOURCE", altered):
            with self.assertRaises(ValueError):
                installer.install(self.agent)
        self.assertFalse((self.agent / "sign.py").exists())


if __name__ == "__main__":
    unittest.main()
