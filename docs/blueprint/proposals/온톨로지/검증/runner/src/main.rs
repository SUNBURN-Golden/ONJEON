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
