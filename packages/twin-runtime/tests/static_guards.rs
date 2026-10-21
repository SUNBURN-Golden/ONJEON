//! Static guards for the S0 skeleton:
//!
//! - **skeleton non-exposure**: `src/` carries no `todo!`/`unimplemented!`/`dbg!` markers
//!   and no fixture or golden ids — product code must not ship placeholders or test data.
//! - **no hidden I/O**: the input stage and the link check never touch a database or the
//!   network; file reads happen only in the harness/CLI layer for the files a job names.
//! - **no leaks**: no secrets, credentials or model identifiers in the shipped code.

use std::path::PathBuf;

fn src_files() -> Vec<PathBuf> {
    let src = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut files = Vec::new();
    let mut stack = vec![src];
    while let Some(d) = stack.pop() {
        for e in std::fs::read_dir(d).unwrap() {
            let p = e.unwrap().path();
            if p.is_dir() {
                stack.push(p);
            } else if p.extension().is_some_and(|x| x == "rs") {
                files.push(p);
            }
        }
    }
    files
}

#[test]
fn no_skeleton_markers_or_fixture_data_in_src() {
    const FORBIDDEN: &[&str] = &[
        "todo!",
        "unimplemented!",
        "dbg!",
        "TODO",
        "FIXME",
        "origin\": \"fixture",
        "origin\": \"synthetic",
        "sc:hana_",
        "sc:hi2607",
        "sc:lotte_",
        "cov:hana_",
        "ted:hana_",
        "rel:case-",
    ];
    for f in src_files() {
        let text = std::fs::read_to_string(&f).unwrap();
        for needle in FORBIDDEN {
            assert!(!text.contains(needle), "{}: found `{needle}`", f.display());
        }
    }
}

#[test]
fn no_database_or_network_access_before_the_engine() {
    const FORBIDDEN: &[&str] = &[
        "std::net",
        "TcpStream",
        "reqwest",
        "hyper::",
        "tokio",
        "sqlx",
        "diesel",
        "postgres",
        "mysql",
        "mongodb",
        "redis",
        "rusqlite",
        "sqlite3",
        "http://",
        "https://",
        "std::process::Command",
    ];
    // the input stage itself must not even read files
    for f in src_files() {
        let text = std::fs::read_to_string(&f).unwrap();
        for needle in FORBIDDEN {
            assert!(!text.contains(needle), "{}: found `{needle}`", f.display());
        }
        if !f.ends_with("harness.rs") && !f.ends_with("case-runner.rs") {
            assert!(
                !text.contains("std::fs"),
                "{}: file I/O belongs to the harness layer",
                f.display()
            );
        }
    }
}

#[test]
fn no_secrets_or_model_identifiers_in_src() {
    const FORBIDDEN: &[&str] = &[
        "-----BEGIN",
        "PRIVATE KEY",
        "api_key",
        "apikey",
        "secret_key",
        "password",
        "passwd",
        "bearer ",
        "x-api-key",
        "sk-",
        "AKIA",
    ];
    for f in src_files() {
        let text = std::fs::read_to_string(&f).unwrap().to_lowercase();
        for needle in FORBIDDEN {
            let n = needle.to_lowercase();
            assert!(!text.contains(&n), "{}: found `{needle}`", f.display());
        }
    }
}
