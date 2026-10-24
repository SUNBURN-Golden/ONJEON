"""Shared-contract conformance of docproc ids and roles. Test-only helper; every input is fixture_only.

Shapes come from packages/schemas: json/common.schema.json (SegmentRef, ClauseRef, EvidenceRef regexes)
and json/vocabulary.schema.json (doc_role enum). Where cargo exists, the same ids are also judged by the
shared Rust parser onjeon_contracts::evidence_ref::validate and the DocRole enum of crate onjeon-contracts.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Inside the container ROOT is /app, so the repository root is resolved without indexing parents.
REPO = ROOT.parent.parent
DEFAULT_SCHEMA_DIR = REPO / "packages" / "schemas" / "json"
SCHEMA_FILES = ("common.schema.json", "vocabulary.schema.json")

RUST_MANIFEST = """[package]
name = "docproc-shared-contract-check"
version = "0.0.0"
edition = "2021"
publish = false

[workspace]

[dependencies]
onjeon-contracts = { path = %s }
serde_json = "1"
"""

RUST_MAIN = r"""use std::io::Read;

fn main() {
    let mut text = String::new();
    std::io::stdin().read_to_string(&mut text).expect("stdin");
    let input: serde_json::Value = serde_json::from_str(&text).expect("json input");
    let mut verdicts = Vec::new();
    for item in input["refs"].as_array().expect("refs") {
        let s = item.as_str().expect("ref string");
        verdicts.push(match onjeon_contracts::evidence_ref::validate(s) {
            Ok(parsed) => serde_json::json!({"ref": s, "ok": true, "kind": format!("{:?}", parsed.kind()),
                                             "round_trip": parsed.to_string() == s}),
            Err(e) => serde_json::json!({"ref": s, "ok": false, "error": e.to_string()}),
        });
    }
    for item in input["doc_roles"].as_array().expect("doc_roles") {
        verdicts.push(match serde_json::from_value::<onjeon_contracts::DocRole>(item.clone()) {
            Ok(role) => serde_json::json!({"doc_role": item, "ok": true, "code": role.as_str()}),
            Err(e) => serde_json::json!({"doc_role": item, "ok": false, "error": e.to_string()}),
        });
    }
    println!("{}", serde_json::Value::Array(verdicts));
}
"""


def schema_dir():
    return Path(os.environ.get("DOCPROC_SCHEMA_DIR") or DEFAULT_SCHEMA_DIR)


def load_schema(directory=None):
    """Compiled shared regexes and the doc_role enum. Raises OSError when the schema files are absent."""
    directory = Path(directory) if directory else schema_dir()
    common = json.loads((directory / "common.schema.json").read_text(encoding="utf-8"))["$defs"]
    vocabulary = json.loads((directory / "vocabulary.schema.json").read_text(encoding="utf-8"))["$defs"]
    return {"SegmentRef": re.compile(common["SegmentRef"]["pattern"]),
            "ClauseRef": re.compile(common["ClauseRef"]["pattern"]),
            "EvidenceRef": re.compile(common["EvidenceRef"]["pattern"]),
            "doc_role": tuple(vocabulary["doc_role"]["enum"])}


def check_output(output, schema):
    """Return (segments, clauses) counts; raise ValueError when an id or role is outside the shared contract."""
    segments = {}
    for segment in output["segments"]:
        sid = segment["id"]
        if not (schema["SegmentRef"].fullmatch(sid) and schema["EvidenceRef"].fullmatch(sid)):
            raise ValueError("Segment id rejected by SegmentRef")
        if segment["doc_role"] not in schema["doc_role"]:
            raise ValueError("Segment doc_role is not a vocabulary doc_role code")
        expected = (f"seg:{output['raw_sha256'][:12]}:p{segment['page_from']}-{segment['page_to']}"
                    f":{segment['doc_role']}:{segment['seg_rule_ver']}")
        if sid != expected:
            raise ValueError("Segment id does not restate its fields")
        segments[sid] = segment
    for clause in output["clauses"]:
        cid, sid = clause["id"], clause["segment_id"]
        if not (schema["ClauseRef"].fullmatch(cid) and schema["EvidenceRef"].fullmatch(cid)):
            raise ValueError("Clause id rejected by ClauseRef")
        segment = segments.get(sid)
        if (segment is None or not cid.startswith(f"clause:{sid}/")
                or not cid.endswith(f"#p{clause['page']}:{clause['extraction_edition']}")):
            raise ValueError("Clause id does not restate its segment, page and edition")
        if not segment["page_from"] <= clause["page"] <= segment["page_to"]:
            raise ValueError("Clause page outside its segment")
    return len(segments), len(output["clauses"])


def rust_parser_verdicts(refs, doc_roles, cargo=None):
    """Judge refs with the shared Rust parser and doc_roles with the DocRole enum; returns verdict dicts."""
    cargo = cargo or shutil.which("cargo")
    if not cargo:
        raise FileNotFoundError("cargo")
    with tempfile.TemporaryDirectory(prefix="docproc-shared-contract-") as tmp:
        crate = Path(tmp) / "crate"
        (crate / "src").mkdir(parents=True)
        (crate / "Cargo.toml").write_text(RUST_MANIFEST % json.dumps(str(REPO / "packages" / "schemas")))
        (crate / "src" / "main.rs").write_text(RUST_MAIN)
        if (REPO / "Cargo.lock").exists():
            shutil.copy(REPO / "Cargo.lock", crate / "Cargo.lock")
        env = {**os.environ, "CARGO_TARGET_DIR": os.environ.get("DOCPROC_CARGO_TARGET_DIR") or str(Path(tmp) / "target")}
        payload = json.dumps({"refs": list(refs), "doc_roles": list(doc_roles)}, ensure_ascii=False)
        command = [cargo, "run", "--quiet", "--manifest-path", str(crate / "Cargo.toml")]
        result = subprocess.run([*command, "--offline"], input=payload, capture_output=True, text=True, env=env, timeout=900)
        if result.returncode != 0:
            result = subprocess.run(command, input=payload, capture_output=True, text=True, env=env, timeout=900)
        if result.returncode != 0:
            raise RuntimeError("Shared Rust parser build or run failed:\n" + result.stderr[-4000:])
        return json.loads(result.stdout)
