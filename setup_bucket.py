"""
Checks the S3 bucket named in .env.

- With the local emulator (S3_ENDPOINT_URL is set): creates the bucket if missing.
- With real AWS: does NOT create anything. It only checks that the bucket exists,
  that you can reach it, and that "Block Public Access" is ON.
"""
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

bucket = os.environ.get("S3_BUCKET", "").strip()
region = os.environ.get("AWS_REGION", "ap-south-1").strip()
endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip() or None

if not bucket:
    sys.exit("S3_BUCKET is not set in .env")

s3 = boto3.client("s3", region_name=region, endpoint_url=endpoint)

try:
    s3.head_bucket(Bucket=bucket)
    print(f"OK: bucket '{bucket}' exists and is reachable.")
except ClientError as error:
    code = error.response["Error"]["Code"]
    if code in ("404", "NoSuchBucket") and endpoint:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        print(f"Created bucket '{bucket}' in the local emulator.")
    elif code in ("404", "NoSuchBucket"):
        sys.exit(f"Bucket '{bucket}' does not exist. Create it in the AWS Console first.")
    else:
        sys.exit(f"Cannot access bucket '{bucket}' (error {code}). Check your credentials and bucket name.")

if endpoint:
    print("Using the local emulator, so Block Public Access is not checked.")
else:
    try:
        cfg = s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
        if all(cfg.values()):
            print("OK: all four 'Block Public Access' settings are ON (bucket is private).")
        else:
            print("WARNING: some Block Public Access settings are OFF:", cfg)
    except ClientError as error:
        print("Could not read Block Public Access settings:", error.response["Error"]["Code"])
