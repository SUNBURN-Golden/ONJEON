"""Wire-level order and count of the requests of one budgeted status run (client side, via botocore events)."""
import os, sys, json, tempfile, collections
from pathlib import Path
REPO=Path(os.environ["ONJEON_REPO"]); sys.path.insert(0,str(REPO/"tools"))
import boto3, r2_budget as b
ops=[]
orig=boto3.client
def client(*a,**k):
    c=orig(*a,**k)
    c.meta.events.register("before-call.s3",lambda params,model,**kw: ops.append((model.name, "/".join(params["url_path"].strip("/").split("/")[1:3]))))
    return c
boto3.client=client
s=b.start(f"{REPO}/infra/r2/jobs/initial-119.json#status", os.environ["R2_ENDPOINT"], gate_dir=tempfile.mkdtemp())
try: s.ledger.read()
finally: summ=b.finish("ok")
print("first 3 ops:",ops[:3])
print("op counts:",dict(collections.Counter(o for o,_ in ops)),"total",len(ops))
print("meter requests:",summ["requests"],"used",summ["used"])
