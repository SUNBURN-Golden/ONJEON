//! 온톨로지 사례 검증용 실행기. stdin으로 [{ "case_id", "rule_path", "inputs" }] 배열을 받아
//! 규칙 엔진으로 평가하고, 결과(판정·지급·누락 입력·규칙 해시·근거·trace)를 stdout에 JSON으로 낸다.
//! 계산은 규칙 엔진만 한다. 이 실행기는 읽고 넘기기만 한다.
use onjeon_rules_engine::Rule;
use serde_json::{json, Value as J};
use std::io::Read;

fn main() {
    let mut buf = String::new();
    std::io::stdin().read_to_string(&mut buf).expect("stdin");
    let jobs: Vec<J> = serde_json::from_str(&buf).expect("jobs json");
    let mut out = Vec::new();
    for job in jobs {
        let path = job["rule_path"].as_str().expect("rule_path");
        let text = std::fs::read_to_string(path).expect("rule file");
        let rule = match Rule::from_json_str(&text) {
            Ok(r) => r,
            Err(e) => {
                out.push(json!({"case_id": job["case_id"], "load_error": format!("{e:?}")}));
                continue;
            }
        };
        match rule.evaluate(&job["inputs"]) {
            Ok(r) => out.push(json!({
                "case_id": job["case_id"],
                "rule_id": r.rule_id,
                "rule_version": r.rule_version,
                "rule_content_hash": r.rule_content_hash,
                "publication_state": rule.publication_state(),
                "evidence_refs": r.evidence_refs,
                "engine_version": r.engine_version,
                "eligibility": serde_json::to_value(r.eligibility).unwrap(),
                "payout": serde_json::to_value(&r.payout).unwrap(),
                "missing_inputs": r.missing_inputs,
                "input_snapshot_hash": r.input_snapshot_hash,
                "trace_len": r.trace.len(),
                "trace_head": r.trace.iter().take(6).map(|t| json!({"path": t.path, "op": t.op, "result": t.result})).collect::<Vec<_>>(),
            })),
            Err(e) => out.push(json!({"case_id": job["case_id"], "eval_error": format!("{e:?}")})),
        }
    }
    println!("{}", serde_json::to_string_pretty(&out).unwrap());
}
