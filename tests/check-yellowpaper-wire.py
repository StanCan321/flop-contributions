#!/usr/bin/env python3
"""Manual pinned public-corpus audit; no fetching, signing, or settlement."""
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys

root = Path(sys.argv[1]) / 'evidence'
pins = {
    'compute-channel.py': '7a7ad29bffa6a9c3f143eb929225db858a5b9fe56374684f3a1b2d57e9047d28',
    'wire-format-v1.json': '80d4a7e70f984342eb474ae5285a17a6b9348eca887e1689b15e641922051d93',
}
for name, digest in pins.items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('STOP: public artifact differs from reviewed bytes')
spec = importlib.util.spec_from_file_location('reviewed_wire', root / 'compute-channel.py')
wire = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = wire
spec.loader.exec_module(wire)
data = json.loads((root / 'wire-format-v1.json').read_text())


def independent_compact(value):
    if value < 64:
        return bytes([4 * value])
    if value < 16384:
        return (4 * value + 1).to_bytes(2, 'little')
    if value < 1073741824:
        return (4 * value + 2).to_bytes(4, 'little')
    return bytes([3]) + value.to_bytes(4, 'little')


def reject(function, value):
    try:
        function(value)
    except ValueError:
        return
    raise AssertionError('malformed input accepted')


rng = random.Random(20260910)
values = [v['value'] for v in data['codec']['scale_compact_u32']]
values += [rng.randrange(2**32) for _ in range(1000)]
for value in values:
    expected = independent_compact(value)
    assert wire.compact_u32(value) == expected
    assert wire.decode_compact_u32(expected) == (value, len(expected))
for case in data['codec']['scale_compact_u32']:
    assert independent_compact(case['value']).hex() == case['bytes_hex']
for case in data['codec']['malformed_compact']:
    reject(wire.decode_compact_u32, bytes.fromhex(case['bytes_hex']))
for value in (-1, 2**32, 1.5):
    reject(wire.compact_u32, value)

channel = data['compute_channel_v1']
for item in [channel['channel_id'], data['direct_rail_v1']['task_hash'], *channel['leaf_versions']]:
    assert hashlib.blake2b(bytes.fromhex(item['preimage_hex']), digest_size=32).hexdigest() == item['hash_hex']
policy = data['decode_policy_v1']
assert hashlib.sha256(bytes.fromhex(policy['hash_preimage_hex'])).hexdigest() == policy['sha256_hex']

blob = bytes.fromhex(channel['fcc4_transcript_blob_hex'])
identifier, turns = wire.decode_transcript_blob(blob)
assert wire.encode_transcript_blob(identifier, turns) == blob
for length in range(len(blob)):
    reject(wire.decode_transcript_blob, blob[:length])
for suffix in (b'\0', b'\xff', b'extra'):
    reject(wire.decode_transcript_blob, blob + suffix)
for case in data['negative_cases']:
    if case['site'] == 'TranscriptBlob.decode':
        reject(wire.decode_transcript_blob, bytes.fromhex(case['bytes_hex']))

print(f'PASS: {len(values)} independent compact encodings and round trips')
print(f'PASS: public malformed compact cases, overflow, {len(blob)} truncations and trailing bytes')
print('PASS: published channel/task/leaf hashes, policy hash and FCC4 round trip')
print('LIMIT: no signature, runtime, quorum, settlement, or full conformance verification')
