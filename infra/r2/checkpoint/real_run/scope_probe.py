"""Read-only scope probes of the current credential (T-OP-04, check C). Nothing is changed or deleted."""
import os, json, boto3, urllib.parse, urllib.request
from botocore.exceptions import ClientError
ep=os.environ["R2_ENDPOINT"]
s3=boto3.client("s3",region_name="auto",endpoint_url=ep,aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
T="onjeon-t-op-04-test-archive"
def t(name,f):
    try: f(); r="ALLOWED"
    except ClientError as e: r=f"HTTP {e.response['ResponseMetadata']['HTTPStatusCode']} {e.response['Error']['Code']}"
    except Exception as e: r=type(e).__name__
    print(f"{name}: {r}")
t("ListBuckets (account-wide)", lambda: s3.list_buckets())
t("HeadBucket other bucket (onjeon-raw-sources)", lambda: s3.head_bucket(Bucket="onjeon-raw-sources"))
t("ListObjectsV2 other bucket (onjeon-raw-sources, 1 key)", lambda: s3.list_objects_v2(Bucket="onjeon-raw-sources",MaxKeys=1))
t("DeleteObject nonexistent key in test bucket", lambda: s3.delete_object(Bucket=T,Key="t-op-04/does-not-exist"))
t("GetBucketLifecycleConfiguration (read) test bucket", lambda: s3.get_bucket_lifecycle_configuration(Bucket=T))
t("GetBucketCors (read) test bucket", lambda: s3.get_bucket_cors(Bucket=T))
