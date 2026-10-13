"""
Simple end-to-end test.

  python test_roundtrip.py          -> uses a temporary LOCAL S3 emulator (free, no AWS needed)
  python test_roundtrip.py --real   -> uses the real settings from your .env (e.g. real AWS S3)

It uploads a 1 MB file and a 2.5 MB file through the real Flask app, downloads them,
and checks that the downloaded file is byte-for-byte identical to the original.
It also checks that what is stored in S3 is encrypted, and that a damaged block is detected.
"""
import hashlib
import io
import logging
import os
import sys
from pathlib import Path

REAL = "--real" in sys.argv
logging.getLogger("werkzeug").setLevel(logging.ERROR)  # hide emulator request logs
server = None

if not REAL:
    os.environ["STORAGE_BACKEND"] = "s3"
    os.environ["S3_BUCKET"] = "test-encrypted-chunks"
    os.environ["AWS_REGION"] = "ap-south-1"
    os.environ["S3_ENDPOINT_URL"] = "http://127.0.0.1:5055"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"       # dummy values for the emulator only
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"   # dummy values for the emulator only
    from moto.server import ThreadedMotoServer
    server = ThreadedMotoServer(port=5055, verbose=False)
    server.start()
    import boto3
    boto3.client("s3", region_name="ap-south-1", endpoint_url="http://127.0.0.1:5055").create_bucket(
        Bucket="test-encrypted-chunks",
        CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
    )

import app as secure_app  # imported AFTER the settings above

client = secure_app.app.test_client()
storage = secure_app.storage
failures = 0


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(label, ok):
    global failures
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        failures += 1


def newest_manifest(filename):
    for m in storage.list_manifests():
        if m["filename"] == filename:
            return m
    return None


print(f"Storage backend in use: {storage.name}\n")

try:
    for label, size in (("1 MB", 1024 * 1024), ("2.5 MB", int(2.5 * 1024 * 1024))):
        name = f"test_{label.replace(' ', '').replace('.', '_')}.bin"
        original = os.urandom(size)
        print(f"--- {label} file ({size} bytes) ---")

        client.post("/upload", data={"file": (io.BytesIO(original), name)},
                    content_type="multipart/form-data")
        manifest = newest_manifest(name)
        check("upload created a manifest", manifest is not None)
        if manifest is None:
            continue
        expected_blocks = -(-size // secure_app.BLOCK_SIZE)
        check(f"file split into {expected_blocks} block(s)", manifest["blocks"] == expected_blocks)

        stored = storage.get_block(manifest["block_files"][0])
        check("stored block is encrypted (not the plain data)", original[:64] not in stored and stored[:4] == b"gAAA")

        resp = client.get(f"/download/{manifest['id']}")
        downloaded = resp.data
        check("download returned the file", resp.status_code == 200 and len(downloaded) > 0)
        check("SIZE matches the original", len(downloaded) == size)
        check("SHA-256 matches the original", sha(downloaded) == sha(original))
        check("bytes are identical to the original", downloaded == original)
        print(f"      original  SHA-256: {sha(original)}")
        print(f"      downloaded SHA-256: {sha(downloaded)}\n")

    print("--- damaged block test ---")
    name = "tamper_test.bin"
    client.post("/upload", data={"file": (io.BytesIO(os.urandom(300000)), name)},
                content_type="multipart/form-data")
    m = newest_manifest(name)
    block = m["block_files"][0]
    bad = bytearray(storage.get_block(block))
    bad[50] ^= 0xFF
    storage.put_block(block, bytes(bad))
    resp = client.get(f"/download/{m['id']}")
    check("damaged block is detected and NOT returned as a file", resp.status_code == 302)
finally:
    if server:
        server.stop()

print()
if failures:
    print(f"RESULT: {failures} check(s) FAILED")
    sys.exit(1)
print("RESULT: ALL CHECKS PASSED")
