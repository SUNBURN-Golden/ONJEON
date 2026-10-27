//! Audit 2: the README "테스트" table must name every integration test file and nothing else,
//! so a new `tests/*.rs` (as `real_clauses` and `vocabulary` once were) cannot go undocumented.
use std::collections::BTreeSet;
use std::path::Path;

const README: &str = include_str!("../README.md");

/// Backticked names in the first column of the table under `## 테스트`.
fn listed(readme: &str) -> BTreeSet<String> {
    let section = readme
        .split("\n## ")
        .find(|s| s.starts_with("테스트\n"))
        .expect("README has a `## 테스트` section");
    let mut out = BTreeSet::new();
    for line in section.lines().filter(|l| l.starts_with("| ")) {
        let first = line[2..].split(" | ").next().unwrap();
        out.extend(first.split('`').skip(1).step_by(2).map(str::to_string));
    }
    out
}

fn on_disk() -> BTreeSet<String> {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests");
    std::fs::read_dir(dir)
        .unwrap()
        .filter_map(|e| {
            let p = e.unwrap().path();
            (p.extension()? == "rs").then(|| p.file_stem()?.to_str().map(str::to_string))?
        })
        .collect()
}

#[test]
fn readme_test_table_matches_integration_test_files() {
    let disk = on_disk();
    assert!(
        disk.len() >= 20,
        "expected the integration test files, got {disk:?}"
    );
    let table = listed(README);
    let missing: Vec<_> = disk.difference(&table).collect();
    let stale: Vec<_> = table.difference(&disk).collect();
    assert!(
        missing.is_empty(),
        "tests/*.rs missing from README table: {missing:?}"
    );
    assert!(
        stale.is_empty(),
        "README table names no such test file: {stale:?}"
    );
}

#[test]
fn audited_rows_are_present() {
    let table = listed(README);
    for name in [
        "real_clauses",
        "vocabulary",
        "content_hash_scope",
        "readme_test_table",
    ] {
        assert!(table.contains(name), "{name} row missing");
    }
}

#[test]
fn checker_catches_a_dropped_row_and_a_stale_row() {
    let row = README
        .lines()
        .find(|l| l.starts_with("| `real_clauses` |"))
        .unwrap();
    let dropped = README.replace(&format!("{row}\n"), "");
    assert!(!listed(&dropped).contains("real_clauses"));
    assert!(listed(&dropped).len() + 1 == listed(README).len());

    let stale = README.replace("| `vocabulary` |", "| `vocabulary_old` |");
    assert!(listed(&stale).contains("vocabulary_old"));
    assert!(!listed(&stale).contains("vocabulary"));
}

#[test]
fn readme_does_not_call_the_content_hash_normalized() {
    let line = README
        .lines()
        .find(|l| l.contains("`rule_content_hash`는"))
        .expect("README describes rule_content_hash");
    assert!(
        !line.contains("JSON을 정규화") && !line.contains("정규화("),
        "only key order is sorted: {line}"
    );
    for phrase in [
        "키 순서만",
        "값 자체는 정규화하지 않는다",
        "유니코드",
        "release_id",
    ] {
        assert!(line.contains(phrase), "hash contract must mention {phrase}");
    }
}
