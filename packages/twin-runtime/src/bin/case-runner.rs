//! `case-runner`: reads a job array on stdin, writes the results on stdout.
//!
//! `case-runner [--root DIR]` — `DIR` (default `.`) prefixes the relative `abox` /
//! `rule_path` values in the jobs. Twin jobs run the input stage (selection → link check
//! → fill → engine); legacy `{case_id, rule_path, inputs}` jobs go straight to the
//! engine. Blocked means the engine ran zero times for that job. No database, no
//! network: the only I/O is the files the jobs name.

use onjeon_twin_runtime::harness::run_jobs_str;
use std::io::Read;
use std::path::PathBuf;
use std::process::ExitCode;

fn main() -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--root" => match args.next() {
                Some(d) => root = PathBuf::from(d),
                None => {
                    eprintln!("case-runner: --root needs a directory");
                    return ExitCode::from(2);
                }
            },
            other => {
                eprintln!("case-runner: unknown argument {other} (usage: case-runner [--root DIR] < jobs.json)");
                return ExitCode::from(2);
            }
        }
    }
    let mut buf = String::new();
    if let Err(e) = std::io::stdin().read_to_string(&mut buf) {
        eprintln!("case-runner: stdin: {e}");
        return ExitCode::FAILURE;
    }
    match run_jobs_str(&buf, &root) {
        Ok(out) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&out).expect("results serialize")
            );
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("case-runner: {e}");
            ExitCode::FAILURE
        }
    }
}
