"""Synthetic credential shapes required before T-OP-09 provisions a remote or runs scenarios.

These are repeated test characters, never issued credentials. Construct them at runtime so
source scans do not mistake the corpus for credentials. Return labels only, never values.
"""
import json

from ..core import Rules, secret_scan


def corpus():
    """Provider shapes, not issued credentials (all payloads repeat test characters)."""
    hex32, hex64 = "a1" * 16, "b2" * 32
    opaque = "SyntheticValue" * 3
    return {
        "r2-env": "R2_SECRET_ACCESS_KEY=" + hex64,
        "r2-env-quoted": 'export R2_SECRET_ACCESS_KEY="' + hex64 + '"',
        "r2-json": json.dumps({"R2_SECRET_ACCESS_KEY": hex64}),
        "json-token": json.dumps({"token": opaque}),
        "json-api-key": json.dumps({"api_key": opaque}),
        "json-password": json.dumps({"password": opaque}),
        "single-quoted-token": "'token': '" + opaque + "'",
        "mixed-case-assignment": 'r2_Secret_Access_Key = "' + opaque + '"',
        "r2-access-bare": hex32,
        "r2-secret-bare": hex64,
        "r2-upper-hex": hex64.upper(),
        "r2-delimited": "key (" + hex32 + ")",
        "aws-long-lived": "AKIA" + "Z" * 16,
        "aws-session": "ASIA" + "Z" * 16,
        "github-classic": "ghp_" + "z" * 36,
        "github-fine-grained": "github_pat_" + "z" * 22 + "_" + "y" * 59,
        "github-app": "ghs_" + "z" * 36,
        "bearer-opaque": "Authorization: Bearer " + opaque,
        "bearer-jwt": "Bearer " + ".".join(["eyJ" + "z" * 24] * 3),
        "bearer-alphabet": "bearer " + "z" * 20 + ".~+/-_==",
        "cloudflare": "cfut_" + "z" * 40,
        "slack": "xoxb-" + "z" * 20,
        "private-key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    }


def missing_cases(rules_path):
    with open(rules_path, encoding="utf-8") as source:
        pats = secret_scan.patterns(Rules(json.load(source)))
    return [label for label, value in corpus().items() if not secret_scan.count(pats, value)]
