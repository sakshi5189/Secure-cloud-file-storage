"""
Storage layer for the Secure Cloud File Storage System.

Two backends with the same methods:
  - LocalStorage : keeps encrypted blocks in the local "storage" folder (original behaviour)
  - S3Storage    : keeps encrypted blocks and manifests in a PRIVATE AWS S3 bucket
                   (or in a local S3-compatible emulator for testing)

The backend is chosen with the STORAGE_BACKEND setting in the .env file.
No access keys are ever written in this source code.
"""
import json
import os
from pathlib import Path


class LocalStorage:
    name = "local"

    def __init__(self, base_dir):
        self.blocks_dir = Path(base_dir) / "storage" / "blocks"
        self.manifests_dir = Path(base_dir) / "storage" / "manifests"
        self.blocks_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def put_block(self, name, data):
        (self.blocks_dir / name).write_bytes(data)

    def get_block(self, name):
        return (self.blocks_dir / name).read_bytes()

    def delete_block(self, name):
        (self.blocks_dir / name).unlink(missing_ok=True)

    def put_manifest(self, file_id, manifest):
        (self.manifests_dir / f"{file_id}.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def get_manifest(self, file_id):
        path = self.manifests_dir / f"{file_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete_manifest(self, file_id):
        (self.manifests_dir / f"{file_id}.json").unlink(missing_ok=True)

    def list_manifests(self):
        for path in sorted(self.manifests_dir.glob("*.json"), reverse=True):
            try:
                yield json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue


class S3Storage:
    name = "s3"

    def __init__(self, bucket, region, endpoint_url=None):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        # Credentials are NOT passed here. boto3 finds them by itself from
        # environment variables or the AWS credentials file on your computer.
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url or None,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}),
        )

    def _put(self, key, data, content_type):
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",  # S3 encrypts the object again at rest
        )

    def _get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def put_block(self, name, data):
        self._put(f"blocks/{name}", data, "application/octet-stream")

    def get_block(self, name):
        return self._get(f"blocks/{name}")

    def delete_block(self, name):
        self.client.delete_object(Bucket=self.bucket, Key=f"blocks/{name}")

    def put_manifest(self, file_id, manifest):
        self._put(
            f"manifests/{file_id}.json",
            json.dumps(manifest, indent=2).encode("utf-8"),
            "application/json",
        )

    def get_manifest(self, file_id):
        from botocore.exceptions import ClientError

        try:
            return json.loads(self._get(f"manifests/{file_id}.json").decode("utf-8"))
        except ClientError as error:
            if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    def delete_manifest(self, file_id):
        self.client.delete_object(Bucket=self.bucket, Key=f"manifests/{file_id}.json")

    def list_manifests(self):
        paginator = self.client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix="manifests/"):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    keys.append(obj["Key"])
        for key in sorted(keys, reverse=True):
            try:
                yield json.loads(self._get(key).decode("utf-8"))
            except Exception:
                continue


def make_storage(base_dir):
    """Build the storage backend from environment settings."""
    backend = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        return LocalStorage(base_dir)
    if backend == "s3":
        bucket = os.environ.get("S3_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 but S3_BUCKET is not set in .env")
        return S3Storage(
            bucket=bucket,
            region=os.environ.get("AWS_REGION", "ap-south-1").strip(),
            endpoint_url=os.environ.get("S3_ENDPOINT_URL", "").strip() or None,
        )
    raise RuntimeError("STORAGE_BACKEND must be 'local' or 's3'")
