//! Stable rustdoc accepts `compile_fail,E0616` even for unrelated errors.
//! Check the actual doctest diagnostics so I3 cannot pass for the wrong reason.
use std::process::Command;

#[test]
fn immutable_rule_doctests_fail_only_on_private_field_access() {
    // `--doc` avoids recursively running this integration test. Cargo releases
    // its build lock before running tests, so this also works in `cargo test`.
    let output = Command::new(env!("CARGO"))
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .args([
            "test",
            "--locked",
            "--offline",
            "--package",
            "onjeon-rules-engine",
            "--doc",
            "--",
            "--show-output",
            "--color",
            "never",
        ])
        .output()
        .expect("run Rule doctests with diagnostics");
    let report = format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.status.success(), "doctests failed:\n{report}");

    let examples: Vec<_> = report
        .split("\n---- ")
        .skip(1)
        .filter(|block| {
            let header = block.lines().next().unwrap_or_default();
            header.contains(" - rule::Rule (line ") && header.ends_with(" stdout ----")
        })
        .collect();
    assert_eq!(examples.len(), 2, "expected both I3 doctests:\n{report}");

    for example in examples {
        let codes: Vec<_> = example
            .lines()
            .filter_map(|line| line.strip_prefix("error["))
            .filter_map(|line| line.split_once(']').map(|(code, _)| code))
            .collect();
        assert!(!codes.is_empty(), "missing diagnostic code:\n{example}");
        assert!(
            codes.iter().all(|code| *code == "E0616"),
            "I3 must fail only on private field access (E0616), got {codes:?}:\n{example}"
        );
    }
}
