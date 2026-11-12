//! Only this crate (the gateway adapters) may depend on a provider SDK.
//! The deny list is by crate name; extend it when a new SDK is considered.
//! (The same rule in the CI dependency rules file belongs to the deps task.)

use serde_json::Value;
use std::process::Command;

const SDKS: &[&str] = &[
    "anthropic",
    "anthropic-sdk",
    "anthropic-ai-sdk",
    "async-openai",
    "openai",
    "openai-api-rs",
    "openai_dive",
    "genai",
    "gemini-rust",
    "google-generative-ai-rs",
    "ollama-rs",
    "mistralai-client",
    "cohere-rust",
    "rig-core",
    "llm",
    "aws-sdk-bedrockruntime",
    "vertexai",
    "groq",
    "litellm",
    "misanthropic",
    "async-anthropic",
    "mistralai_azure",
    "google_generative_ai",
    "google-genai",
    "google-generativeai",
    "cohere",
    "mistralai",
    "ollama",
];
const GATEWAY: &str = "onjeon-ai-gateway";

/// Names of workspace crates (other than the gateway) with a direct SDK dependency.
fn offenders(meta: &Value) -> Vec<String> {
    let members: Vec<&str> = meta["workspace_members"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(Value::as_str)
        .collect();
    let mut out = Vec::new();
    for p in meta["packages"].as_array().unwrap() {
        let id = p["id"].as_str().unwrap();
        let name = p["name"].as_str().unwrap();
        if !members.contains(&id) || name == GATEWAY {
            continue;
        }
        for d in p["dependencies"].as_array().unwrap() {
            let dn = d["name"].as_str().unwrap();
            if SDKS.contains(&dn) {
                out.push(format!("{name} -> {dn}"));
            }
        }
    }
    out
}

/// Where the workspace scan runs. Cargo sets CARGO_MANIFEST_DIR for the test process at
/// runtime; prefer it over the compile-time path, which goes stale when a shared target
/// dir reuses a binary built in another (possibly deleted) worktree — spawning with a
/// vanished working directory fails with NotFound before cargo even runs.
fn scan_dir(runtime: Option<String>) -> String {
    runtime.unwrap_or_else(|| env!("CARGO_MANIFEST_DIR").to_string())
}

#[test]
fn provider_sdk_only_here() {
    let cargo = std::env::var("CARGO").unwrap_or_else(|_| "cargo".into());
    let out = Command::new(cargo)
        .args([
            "metadata",
            "--format-version",
            "1",
            "--no-deps",
            "--offline",
        ])
        .current_dir(scan_dir(std::env::var("CARGO_MANIFEST_DIR").ok()))
        .output()
        .expect("cargo metadata runs");
    assert!(out.status.success(), "cargo metadata failed");
    let meta: Value = serde_json::from_slice(&out.stdout).unwrap();
    let names: Vec<&str> = meta["packages"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|p| p["name"].as_str())
        .collect();
    assert!(
        names.contains(&GATEWAY) && names.contains(&"onjeon-contracts"),
        "workspace scan too narrow"
    );
    assert_eq!(offenders(&meta), Vec::<String>::new());
}

#[test]
fn detector_flags_a_foreign_crate_with_an_sdk() {
    let meta = serde_json::json!({
        "workspace_members": ["a 0.1.0", "g 0.1.0"],
        "packages": [
            {"id": "a 0.1.0", "name": "other-crate", "dependencies": [{"name": "async-openai"}, {"name": "serde"}]},
            {"id": "g 0.1.0", "name": GATEWAY, "dependencies": [{"name": "async-openai"}]},
            {"id": "x 1.0.0", "name": "registry-only", "dependencies": [{"name": "openai"}]}
        ]
    });
    assert_eq!(
        offenders(&meta),
        vec!["other-crate -> async-openai".to_string()]
    );
}

#[test]
fn scan_dir_prefers_the_runtime_manifest_dir() {
    assert_eq!(
        scan_dir(Some("/runtime/worktree/services/ai-gateway".into())),
        "/runtime/worktree/services/ai-gateway"
    );
    assert_eq!(scan_dir(None), env!("CARGO_MANIFEST_DIR"));
}
