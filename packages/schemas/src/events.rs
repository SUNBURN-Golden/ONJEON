//! Domain event index (02_구현계약 §3.1, C-21): `packages/schemas/events/`.
//!
//! One `events/<name>.schema.json` per event and `events/index.json` listing them with
//! publisher, consumers, queue and an example. The schemas are the contract; this module
//! only loads the index. The schema checks are tests (`events::tests`), which run the
//! stdlib validator of `codegen/validate.py` because the crate has no regex engine.

use serde::Deserialize;
use serde_json::Value;

const INDEX: &str = include_str!("../events/index.json");

#[derive(Debug, Clone, Deserialize)]
pub struct Index {
    pub contracts_version: String,
    pub events: Vec<EventEntry>,
    pub not_sent: Vec<NotSent>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EventEntry {
    pub event: String,
    pub schema: String,
    /// `domain` or `personal` (the personal queue never leaves the personal area).
    pub queue: String,
    pub publisher: String,
    pub consumers: Vec<String>,
    pub example: Value,
}

#[derive(Debug, Clone, Deserialize)]
pub struct NotSent {
    pub event: String,
}

/// The index compiled into the crate.
pub fn index() -> Index {
    serde_json::from_str(INDEX).expect("events/index.json matches the index types")
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::collections::BTreeSet;
    use std::io::Write;
    use std::path::PathBuf;
    use std::process::{Command, Stdio};

    /// The events of 02 §3.1 with `/` pairs and `.opened/.resolved` groups expanded.
    const CONTRACT_EVENTS: [&str; 21] = [
        "data.raw.archived",
        "data.source.changed",
        "data.segment.extracted",
        "data.clause.extracted",
        "knowledge.assertion.proposed",
        "knowledge.review.decided",
        "knowledge.assertion.superseded",
        "knowledge.conflict.opened",
        "knowledge.conflict.resolved",
        "knowledge.release.candidate",
        "knowledge.release.published",
        "knowledge.release.withdrawn",
        "twin.shadow.compared",
        "knowledge.gap.opened",
        "knowledge.gap.updated",
        "knowledge.task.updated",
        "ops.circuit_breaker.tripped",
        "ops.circuit_breaker.reset",
        "personal.import.completed",
        "personal.import.confirmed",
        "personal.deletion.step",
    ];

    fn root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
    }

    fn schema(name: &str) -> Value {
        let text = std::fs::read_to_string(root().join("events").join(name)).unwrap();
        serde_json::from_str(&text).unwrap()
    }

    /// Validates each (schema title, document) with `codegen/validate.py`; returns the
    /// error list per case. Event schemas are copied next to `common` and `vocabulary`
    /// so their `$ref`s resolve the way they do in `json/`.
    fn validate(cases: &[(String, Value)]) -> Vec<Vec<String>> {
        const SCRIPT: &str = r#"
import json, pathlib, shutil, sys, tempfile
codegen, events, jsondir = sys.argv[1:4]
sys.path.insert(0, codegen)
import validate
tmp = pathlib.Path(tempfile.mkdtemp())
for f in pathlib.Path(events).glob("*.schema.json"):
    shutil.copy(f, tmp)
for n in ("common.schema.json", "vocabulary.schema.json"):
    shutil.copy(pathlib.Path(jsondir) / n, tmp)
v = validate.Validator(tmp)
cases = json.load(sys.stdin)
print(json.dumps([v.validate(inst, title) for title, inst in cases]))
shutil.rmtree(tmp)
"#;
        let mut child = Command::new("python3")
            .arg("-I")
            .arg("-c")
            .arg(SCRIPT)
            .arg(root().join("codegen"))
            .arg(root().join("events"))
            .arg(root().join("json"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .expect("python3 is required to validate event schemas");
        child
            .stdin
            .take()
            .unwrap()
            .write_all(serde_json::to_string(cases).unwrap().as_bytes())
            .unwrap();
        let out = child.wait_with_output().unwrap();
        assert!(out.status.success(), "validator failed");
        serde_json::from_slice(&out.stdout).unwrap()
    }

    fn title_of(entry: &EventEntry) -> String {
        schema(&entry.schema)["title"].as_str().unwrap().to_string()
    }

    #[test]
    fn events_index_lists_every_event_of_the_contract() {
        let idx = index();
        assert_eq!(idx.contracts_version, crate::CONTRACTS_VERSION);
        let listed: BTreeSet<&str> = idx.events.iter().map(|e| e.event.as_str()).collect();
        let expect: BTreeSet<&str> = CONTRACT_EVENTS.into_iter().collect();
        assert_eq!(listed, expect);
        assert_eq!(idx.events.len(), CONTRACT_EVENTS.len());
        // The denominator signal is deliberately not sent: no schema, no index entry.
        assert_eq!(idx.not_sent.len(), 1);
        assert_eq!(idx.not_sent[0].event, "personal.denominator_signal");
        assert!(!listed.contains("personal.denominator_signal"));
    }

    #[test]
    fn events_each_event_has_exactly_one_schema_file() {
        let idx = index();
        let mut on_disk: BTreeSet<String> = std::fs::read_dir(root().join("events"))
            .unwrap()
            .map(|e| e.unwrap().file_name().into_string().unwrap())
            .filter(|n| n.ends_with(".schema.json"))
            .collect();
        let mut titles = BTreeSet::new();
        for e in &idx.events {
            assert_eq!(e.schema, format!("{}.schema.json", e.event));
            assert!(on_disk.remove(&e.schema), "no schema file for {}", e.event);
            let s = schema(&e.schema);
            assert_eq!(s["properties"]["event"]["enum"], json!([e.event]));
            assert_eq!(s["additionalProperties"], json!(false));
            assert_eq!(
                s["properties"]["payload"]["additionalProperties"],
                json!(false)
            );
            assert!(
                titles.insert(title_of(e)),
                "duplicate title for {}",
                e.event
            );
            assert!(!e.consumers.is_empty());
        }
        assert!(
            on_disk.is_empty(),
            "schema files without an index entry: {on_disk:?}"
        );
    }

    #[test]
    fn events_examples_validate() {
        let idx = index();
        let cases: Vec<(String, Value)> = idx
            .events
            .iter()
            .map(|e| (title_of(e), e.example.clone()))
            .collect();
        for (e, errors) in idx.events.iter().zip(validate(&cases)) {
            assert!(errors.is_empty(), "{}: {errors:?}", e.event);
        }
    }

    #[test]
    fn events_reject_extra_missing_and_wrong_shape() {
        let idx = index();
        let mut cases = Vec::new();
        let mut names = Vec::new();
        for e in &idx.events {
            let title = title_of(e);
            let mut add = |what: String, doc: Value| {
                names.push(format!("{}: {what}", e.event));
                cases.push((title.clone(), doc));
            };
            let mut extra = e.example.clone();
            extra["payload"]["owner_name"] = json!("x");
            add("extra payload field".into(), extra);
            let mut extra = e.example.clone();
            extra["unexpected"] = json!(1);
            add("extra envelope field".into(), extra);
            let mut wrong = e.example.clone();
            wrong["event"] = json!("some.other.event");
            add("wrong event name".into(), wrong);
            let mut no_id = e.example.clone();
            no_id.as_object_mut().unwrap().remove("event_id");
            add("missing event_id".into(), no_id);
            let mut bad_time = e.example.clone();
            bad_time["occurred_at"] = json!("yesterday");
            add("bad timestamp".into(), bad_time);
            for key in e.example["payload"].as_object().unwrap().keys() {
                let mut missing = e.example.clone();
                missing["payload"].as_object_mut().unwrap().remove(key);
                add(format!("missing {key}"), missing);
            }
        }
        for (name, errors) in names.iter().zip(validate(&cases)) {
            assert!(!errors.is_empty(), "accepted: {name}");
        }
    }

    #[test]
    fn events_check_vocabulary_ids_and_counts() {
        let idx = index();
        let by = |n: &str| idx.events.iter().find(|e| e.event == n).unwrap();
        let mut cases = Vec::new();
        let mut push = |n: &str, path: &[&str], v: Value| {
            let mut doc = by(n).example.clone();
            let mut at = &mut doc["payload"];
            for p in path {
                at = &mut at[*p];
            }
            *at = v;
            cases.push((title_of(by(n)), doc));
        };
        push("data.source.changed", &["change"], json!("invented"));
        push("knowledge.review.decided", &["outcome"], json!("maybe"));
        push("knowledge.review.decided", &["families_count"], json!(-1));
        // `correction_reason` is the vocabulary axis (1.6.0), not free text.
        push(
            "knowledge.assertion.superseded",
            &["correction_reason"],
            json!("wrong_page"),
        );
        push("data.raw.archived", &["sha256"], json!("abc"));
        push("data.raw.archived", &["byte_len"], json!(1.5));
        push(
            "knowledge.assertion.proposed",
            &["assertion_id"],
            json!("assertion:01ARZ3NDEKTSV4RRFFQ69G5FAV"),
        );
        push("knowledge.conflict.opened", &["assertion_ids"], json!([]));
        push(
            "ops.circuit_breaker.tripped",
            &["scope", "kind"],
            json!("product"),
        );
        push("knowledge.release.published", &["release_id"], json!("r-1"));
        push(
            "personal.import.confirmed",
            &["contract_id"],
            json!("contract:x"),
        );
        for (i, errors) in validate(&cases).iter().enumerate() {
            assert!(!errors.is_empty(), "case {i} was accepted");
        }
    }

    /// Public queues must not carry the personal identifiers; the personal queue carries
    /// identifiers only.
    #[test]
    fn events_personal_ids_stay_on_the_personal_queue() {
        const PERSONAL_IDS: [&str; 3] = ["upload_id", "contract_id", "del_id"];
        let idx = index();
        for e in &idx.events {
            let payload = schema(&e.schema)["properties"]["payload"]["properties"].clone();
            let keys: Vec<&str> = payload
                .as_object()
                .unwrap()
                .keys()
                .map(String::as_str)
                .collect();
            if e.queue == "personal" {
                assert!(e.event.starts_with("personal."), "{}", e.event);
                assert_eq!(e.publisher, "personal");
                assert_eq!(e.consumers, vec!["personal".to_string()]);
                assert!(
                    keys.iter().all(|k| PERSONAL_IDS.contains(k)),
                    "{}: {keys:?}",
                    e.event
                );
            } else {
                assert!(!e.event.starts_with("personal."), "{}", e.event);
                assert!(
                    !keys.iter().any(|k| PERSONAL_IDS.contains(k)),
                    "{}",
                    e.event
                );
                assert!(!e.consumers.iter().any(|c| c == "personal"), "{}", e.event);
            }
        }
    }
}
