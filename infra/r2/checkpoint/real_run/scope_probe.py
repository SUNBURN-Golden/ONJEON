"""Scope probes of the current credential (T-OP-04, check C), limited to test scope.

The approved scope is test prefixes/buckets only, so no probe here addresses a production bucket.
"Other bucket" is probed with a name that does not exist: a bucket-scoped token would be refused
before existence is checked, while an account-wide token gets as far as a 404. ListBuckets is an
account-level metadata call (names only, no keys) and is the minimal check of account-wide scope.
This script is NOT read-only: one probe sends DeleteObject for a key that does not exist in the
test bucket, to learn whether the delete verb is permitted without touching any real object.
"""
import os, boto3
from botocore.exceptions import ClientError
ep = os.environ["R2_ENDPOINT"]
s3 = boto3.client("s3", region_name="auto", endpoint_url=ep,
                  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
T = "onjeon-t-op-04-test-archive"
NOPE = "onjeon-t-op-04-no-such-bucket"          # a bucket name nothing uses: tests scope, not data
calls = []


def t(name, f):
    try:
        f()
        r = "ALLOWED"
    except ClientError as e:
        r = f"HTTP {e.response['ResponseMetadata']['HTTPStatusCode']} {e.response['Error']['Code']}"
    except Exception as e:
        r = type(e).__name__
    calls.append(name)
    print(f"{name}: {r}")


t("ListBuckets (account-level metadata, names only)", lambda: s3.list_buckets())
t("HeadBucket nonexistent bucket (scope, not data)", lambda: s3.head_bucket(Bucket=NOPE))
t("ListObjectsV2 nonexistent bucket (scope, not data)",
  lambda: s3.list_objects_v2(Bucket=NOPE, MaxKeys=1))
t("DeleteObject nonexistent key in test bucket (mutating verb, nothing real)",
  lambda: s3.delete_object(Bucket=T, Key="t-op-04/does-not-exist"))
t("GetBucketLifecycleConfiguration (read) test bucket",
  lambda: s3.get_bucket_lifecycle_configuration(Bucket=T))
t("GetBucketCors (read) test bucket", lambda: s3.get_bucket_cors(Bucket=T))
print("requests:", len(calls))
