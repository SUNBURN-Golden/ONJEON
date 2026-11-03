//! 온톨로지 사례 검증용 실행기. stdin으로 [{ "case_id", "rule_path", "inputs" }] 배열을 받아
//! 규칙 엔진으로 평가하고, 결과(릴리스·스키마 버전·판정·지급·누락 입력·규칙 해시·근거·trace)를 stdout에 JSON으로 낸다.
//! 작업별 오류는 io_error/load_error/eval_error 행으로 남기고 다음 작업을 계속한다(종료 코드 0).
//! 배치 입력·출력 오류는 stderr에 보고하고 종료 코드 1을 반환한다.
//! 계산은 규칙 엔진만 한다. 이 실행기는 읽고 넘기기만 한다.
use onjeon_rules_engine::Rule;
use serde_json::{json, Value as J};
use std::io::{Read, Write};
use std::process::ExitCode;

fn run(mut input: impl Read, mut output: impl Write) -> Result<(), String> {
    let mut buf = String::new();
    input
        .read_to_string(&mut buf)
        .map_err(|e| format!("stdin: {e}"))?;
    let jobs: Vec<J> = serde_json::from_str(&buf).map_err(|e| format!("jobs json: {e}"))?;
    let mut out = Vec::new();
    for job in jobs {
        let Some(path) = job["rule_path"].as_str() else {
            out.push(
                json!({"case_id": job["case_id"], "io_error": "rule_path missing or not a string"}),
            );
            continue;
        };
        let text = match std::fs::read_to_string(path) {
            Ok(t) => t,
            Err(e) => {
                out.push(json!({"case_id": job["case_id"], "io_error": format!("{path}: {e}")}));
                continue;
            }
        };
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
                "release_id": r.release_id,
                "schema_version": r.schema_version,
                "rule_content_hash": r.rule_content_hash,
                "publication_state": rule.publication_state(),
                "evidence_refs": r.evidence_refs,
                "engine_version": r.engine_version,
                "eligibility": r.eligibility,
                "payout": r.payout,
                "missing_inputs": r.missing_inputs,
                "input_snapshot_hash": r.input_snapshot_hash,
                "trace_len": r.trace.len(),
                "trace_head": r.trace.iter().take(6).map(|t| json!({"path": t.path, "op": t.op, "result": t.result})).collect::<Vec<_>>(),
            })),
            Err(e) => out.push(json!({"case_id": job["case_id"], "eval_error": format!("{e:?}")})),
        }
    }
    serde_json::to_writer_pretty(&mut output, &out).map_err(|e| format!("stdout: {e}"))?;
    writeln!(output).map_err(|e| format!("stdout: {e}"))
}

fn main() -> ExitCode {
    match run(std::io::stdin().lock(), std::io::stdout().lock()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("ontology-case-runner: {e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{self, Cursor};

    #[test]
    fn original_rules_keep_identity_fields_in_every_successful_result() {
        let ontology = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let pins: J = serde_json::from_str(
            &std::fs::read_to_string(ontology.join("rule_content_hashes.json")).unwrap(),
        )
        .unwrap();
        let mut jobs = Vec::new();
        for name in ["hana-2601-3d-cancer-dx.json", "hi2607-2-5-cancer-dx.json"] {
            let path = ontology.join("규칙").join(name);
            let source: J = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
            let mut inputs = json!({
                "contract_date": "2026-01-01", "diagnosis_date": "2027-01-01",
                "policy_end_date": "2046-01-01", "dx_in_category": true,
                "already_paid": false, "insured_amount_krw": 10000001
            });
            if source["inputs"].get("is_initial_contract").is_some() {
                inputs["is_initial_contract"] = json!(true);
                inputs["renewal_date"] = J::Null;
            }
            for gate in [json!(true), json!(false), J::Null] {
                inputs["dx_in_category"] = gate;
                jobs.push(json!({"case_id": name, "rule_path": path, "inputs": inputs}));
            }
        }
        let mut output = Vec::new();
        run(Cursor::new(serde_json::to_vec(&jobs).unwrap()), &mut output).unwrap();
        let rows: Vec<J> = serde_json::from_slice(&output).unwrap();
        assert_eq!(rows.len(), 6);
        for (job, row) in jobs.iter().zip(&rows) {
            let source = std::fs::read_to_string(job["rule_path"].as_str().unwrap()).unwrap();
            let rule = Rule::from_json_str(&source).unwrap();
            let expected = serde_json::to_value(rule.evaluate(&job["inputs"]).unwrap()).unwrap();
            for field in [
                "rule_id",
                "rule_version",
                "release_id",
                "schema_version",
                "rule_content_hash",
                "evidence_refs",
                "engine_version",
                "eligibility",
                "payout",
                "missing_inputs",
                "input_snapshot_hash",
            ] {
                assert_eq!(
                    row.get(field),
                    expected.get(field),
                    "{}: {field}",
                    job["case_id"]
                );
            }
            // get() distinguishes an explicit JSON null release_id from a dropped key.
            assert_eq!(row.get("release_id"), Some(&J::Null));
            assert_eq!(row["schema_version"], "rule-0.1");
            assert_eq!(
                row["rule_content_hash"],
                pins[job["case_id"].as_str().unwrap()]
            );
            assert_eq!(row["publication_state"], "fixture_only");
            assert_eq!(
                row["trace_len"],
                expected["trace"].as_array().unwrap().len()
            );
        }
        assert_eq!(
            rows.iter()
                .map(|row| row["payout"]["kind"].as_str().unwrap())
                .collect::<Vec<_>>(),
            [
                "payable",
                "not_payable",
                "undetermined",
                "payable",
                "not_payable",
                "undetermined"
            ]
        );
    }

    struct Unreadable;

    impl Read for Unreadable {
        fn read(&mut self, _: &mut [u8]) -> io::Result<usize> {
            Err(io::Error::other("input unavailable"))
        }
    }

    struct Unwritable;

    impl Write for Unwritable {
        fn write(&mut self, _: &[u8]) -> io::Result<usize> {
            Err(io::Error::new(io::ErrorKind::BrokenPipe, "output closed"))
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn unreadable_stdin_reports_error_without_output() {
        let mut output = Vec::new();
        assert_eq!(
            run(Unreadable, &mut output),
            Err("stdin: input unavailable".into())
        );
        assert!(output.is_empty());
    }

    #[test]
    fn invalid_utf8_stdin_reports_error_without_output() {
        let mut output = Vec::new();
        let error = run(Cursor::new([0xff]), &mut output).unwrap_err();
        assert!(error.starts_with("stdin:"), "{error}");
        assert!(output.is_empty());
    }

    #[test]
    fn broken_stdout_reports_error() {
        assert_eq!(
            run(Cursor::new(b"[]"), Unwritable),
            Err("stdout: output closed".into())
        );
    }
}
