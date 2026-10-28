"""Resolve design-validation rule fixtures and explicit, hash-pinned replacements.

Superseded shared JSON is historical input, not an active rule. Missing or stale
replacements fail rather than silently selecting the historical rule again.
"""
import hashlib
import json
from pathlib import Path

MANIFEST = Path("packages/rules-engine/fixtures/rules/replacements.json")


def content_hash(rule):
    value = {key: value for key, value in rule.items() if key != "release_id"}
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_rules(root):
    rules = {}
    for path in sorted((root / "packages/fixtures/rules/real").glob("*.json")):
        if not path.name.endswith(".cases.json"):
            rules[str(path.relative_to(root))] = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    for rule_id, entry in manifest["replacements"].items():
        old = rules.pop(entry["supersedes"])
        source = entry["source"]
        path = Path(source)
        if path.parent != Path("packages/rules-engine/fixtures/rules/real"):
            raise ValueError(f"{rule_id}: replacement must live in the engine fixture directory")
        new = json.loads((root / path).read_text(encoding="utf-8"))
        if (old["rule_id"] != rule_id or new["rule_id"] != rule_id
                or new["publication_state"] != "fixture_only"
                or content_hash(old) != entry["previous_content_hash"]
                or content_hash(new) != entry["content_hash"]):
            raise ValueError(f"{rule_id}: replacement identity, state or hash mismatch")
        if source in rules:
            raise ValueError(f"{rule_id}: duplicate replacement source")
        rules[source] = new
    return rules
