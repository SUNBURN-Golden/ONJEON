"""Synthetic credential shapes required before T-OP-09 provisions a remote or runs scenarios.

These are repeated test characters, never issued credentials. Construct them at runtime so
source scans do not mistake the corpus for credentials. Return labels only, never values.

The preflight has two sides: every corpus value must match, and every ordinary value in
non_secret() must not match. The negative side rejects an empty or all-matching pattern and
pins the non-detection of digest contexts (Cargo.lock checksums, sha256 lines), which share
the bare 32/64-hex shape with R2 secret keys. Bare R2 keys themselves are positive cases:
the rules exclude a hex value only when its line carries a digest name such as `checksum`,
`sha256`, `content_hash` or `tree_hash`.
"""
import json

from ..core import Rules, secret_scan

# Pinned labels: deleting a format from corpus() must not silently shrink the preflight.
CASES = (
    "r2-env",
    "r2-env-quoted",
    "r2-json",
    "r2-access-id",
    "r2-access-json",
    "bare-r2-key-32",
    "bare-r2-key-64",
    "bare-r2-key-json",
    "s3-secret-key",
    "aws-secret-key-upper",
    "json-token",
    "json-api-key",
    "json-password",
    "single-quoted-token",
    "mixed-case-assignment",
    "aws-long-lived",
    "aws-session",
    "github-classic",
    "github-fine-grained",
    "github-app",
    "bearer-opaque",
    "bearer-jwt",
    "bearer-alphabet",
    "bearer-underscore-leading",
    "bearer-underscore-inside",
    "cloudflare",
    "slack",
    "private-key",
)


def corpus():
    """Provider shapes, not issued credentials (all payloads repeat test characters)."""
    hex32, hex64 = "a1" * 16, "b2" * 32
    opaque = "SyntheticValue" * 3
    return {
        "r2-env": "R2_SECRET_ACCESS_KEY=" + hex64,
        "r2-env-quoted": 'export R2_SECRET_ACCESS_KEY="' + hex64 + '"',
        "r2-json": json.dumps({"R2_SECRET_ACCESS_KEY": hex64}),
        "r2-access-id": "R2_ACCESS_KEY_ID=" + hex32,
        "r2-access-json": json.dumps({"r2_access_key_id": hex32}),
        # R2 keys also appear on their own, without a credential name: a standalone 32-hex access
        # key id and a 64-hex secret access key, plus one as an unlabelled JSON value.
        "bare-r2-key-32": hex32,
        "bare-r2-key-64": hex64,
        "bare-r2-key-json": json.dumps({"value": hex64}),
        "s3-secret-key": "S3_SECRET_ACCESS_KEY=" + hex64,
        "aws-secret-key-upper": "AWS_SECRET_ACCESS_KEY=" + hex64.upper(),
        "json-token": json.dumps({"token": opaque}),
        "json-api-key": json.dumps({"api_key": opaque}),
        "json-password": json.dumps({"password": opaque}),
        "single-quoted-token": "'token': '" + opaque + "'",
        "mixed-case-assignment": 'r2_Secret_Access_Key = "' + opaque + '"',
        "aws-long-lived": "AKIA" + "Z" * 16,
        "aws-session": "ASIA" + "Z" * 16,
        "github-classic": "ghp_" + "z" * 36,
        "github-fine-grained": "github_pat_" + "z" * 22 + "_" + "y" * 59,
        "github-app": "ghs_" + "z" * 36,
        "bearer-opaque": "Authorization: Bearer " + opaque,
        "bearer-jwt": "Bearer " + ".".join(["eyJ" + "z" * 24] * 3),
        "bearer-alphabet": "bearer " + "z" * 20 + ".~+/-_==",
        # RFC 6750 b64token includes "_"; it may lead the payload or sit anywhere inside it.
        "bearer-underscore-leading": "Authorization: Bearer _" + "z" * 20,
        "bearer-underscore-inside": "Bearer " + "abc_defghijklmnopqrstuvwxyz",
        "cloudflare": "cfut_" + "z" * 40,
        "slack": "xoxb-" + "z" * 20,
        "private-key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    }


def non_secret():
    """Ordinary values the rules must leave alone. Digest *contexts* share the hex key shape but
    are not credentials; a bare hex value is a positive case above, not an exception here."""
    hex32, hex64 = "a1" * 16, "b2" * 32
    return {
        "plain-text": "public documentation",
        "empty-r2-assignment": "R2_SECRET_ACCESS_KEY=",
        "short-r2-value": "R2_SECRET_ACCESS_KEY=short",
        "short-json-token": '"token": "short"',
        "bearer-placeholder": "Bearer <redacted>",
        "bearer-shell-variable": "Bearer ${TOKEN}",
        "api-key-variable": "api_key=${API_KEY}",
        "source-identifier": "token = self.credentials.token(name, task_id)",
        "hex-31": "a" * 31,
        "hex-33": "a" * 33,
        "git-oid-40": "a" * 40,
        "hex-63": "a" * 63,
        "hex-65": "a" * 65,
        "hex-128": "a" * 128,
        "hex-in-identifier": "prefix_" + "a" * 32,
        "hex-with-suffix": "a" * 64 + "_suffix",
        "cargo-lock-checksum": 'checksum = "' + hex64 + '"',
        "json-sha256": '"sha256": "' + hex64 + '"',
        "sha256-line": "sha256:" + hex64,
        "tree-hash": 'tree_hash = "' + hex32 + '"',
        "content-hash": '"content_hash": "' + hex64 + '"',
    }


def missing_cases(rules_path):
    with open(rules_path, encoding="utf-8") as source:
        rules = Rules(json.load(source))
    raw_patterns = rules.get("preserve_manifest.secret_patterns.patterns")
    if not isinstance(raw_patterns, list) or not all(isinstance(p, str) for p in raw_patterns):
        raise ValueError("secret_patterns.patterns must be a list of strings")
    pats = secret_scan.patterns(rules)
    failed = []
    if any(not p.strip() for p in raw_patterns):
        failed.append("empty-pattern")
    present = corpus()
    failed += [f"missing-format:{label}" for label in CASES if label not in present]
    failed += [f"missing-format:{label}" for label, value in present.items() if not secret_scan.count(pats, value)]
    failed += [f"non-secret:{label}" for label, value in non_secret().items() if secret_scan.count(pats, value)]
    return failed
