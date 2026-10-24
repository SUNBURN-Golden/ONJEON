"""Read-only query of the bucket lock rules (T-OP-04, check F). Prints counts only, never ids."""
import os, json, urllib.request, urllib.error, urllib.parse
acct=urllib.parse.urlparse(os.environ["R2_ENDPOINT"]).hostname.split(".")[0]
tok=os.environ["CLOUDFLARE_API_TOKEN"]
def get(path):
    rq=urllib.request.Request("https://api.cloudflare.com/client/v4/accounts/"+acct+path,headers={"Authorization":"Bearer "+tok})
    try:
        with urllib.request.urlopen(rq,timeout=30) as r: return r.status,json.load(r)
    except urllib.error.HTTPError as e:
        try: return e.code,json.load(e)
        except Exception: return e.code,{}
for b in ("onjeon-budget-ledger","onjeon-raw-sources","onjeon-derived-sources","onjeon-t-op-04-test-ledger"):
    c,d=get(f"/r2/buckets/{b}/lock")
    rules=(d.get("result") or {}).get("rules")
    errs=[e.get("code") for e in d.get("errors",[])]
    print(b,"HTTP",c,"success=",d.get("success"),"rules=",None if rules is None else len(rules),"errors=",errs)
