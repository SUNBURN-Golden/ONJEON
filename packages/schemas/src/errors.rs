//! Error code catalog (02_구현계약 §4, C-22): `packages/schemas/errors.json`.
//!
//! The JSON file is the contract. This module loads it, looks codes up and checks the
//! rules the file has to keep: every code has a screen-state mapping, the class letter
//! matches the code, each class letter names its `error_class` vocabulary value (the
//! word an [`ErrorResponse`] carries on the wire), the delivery matches the HTTP status,
//! and the catalog is pinned to the contracts package version (C-23).

use crate::checks::{error_class_for_letter, error_class_letter};
use crate::{ErrorClass, ErrorResponse};
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../errors.json");

#[derive(Debug, Clone, Deserialize)]
pub struct Catalog {
    pub contracts_version: String,
    pub zones: BTreeMap<String, String>,
    /// Class letter of `code` (`V`, `A`, ...) to its vocabulary value and meaning.
    pub classes: BTreeMap<String, ClassDef>,
    pub deliveries: BTreeMap<String, String>,
    pub screen_states: BTreeMap<String, ScreenState>,
    pub codes: Vec<ErrorCode>,
}

/// One class letter: `vocabulary` is the `error_class` axis value the wire body carries.
#[derive(Debug, Clone, Deserialize)]
pub struct ClassDef {
    pub vocabulary: String,
    pub name_ko: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ScreenState {
    pub name_ko: String,
    pub rule_ko: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ErrorCode {
    pub code: String,
    pub error_class: String,
    pub zone: String,
    pub meaning_ko: String,
    /// `http_error`, `result_state` or `operational` (see `deliveries`).
    pub delivery: String,
    pub http_status: Option<u16>,
    pub retryable: bool,
    pub screen_state: String,
    pub screen_ko: String,
    pub message_key: String,
}

/// The catalog compiled into the crate.
pub fn catalog() -> Catalog {
    serde_json::from_str(SOURCE).expect("errors.json matches the catalog types")
}

/// Splits `ONJ-<zone 2>-<class 1>-<nnn>` into (zone, class); `None` when malformed.
pub fn split_code(code: &str) -> Option<(&str, &str)> {
    let parts: Vec<&str> = code.split('-').collect();
    let [prefix, zone, class, num] = parts[..] else {
        return None;
    };
    let ok = prefix == "ONJ"
        && zone.len() == 2
        && zone.bytes().all(|b| b.is_ascii_uppercase())
        && class.len() == 1
        && num.len() == 3
        && num.bytes().all(|b| b.is_ascii_digit());
    ok.then_some((zone, class))
}

impl Catalog {
    pub fn get(&self, code: &str) -> Option<&ErrorCode> {
        self.codes.iter().find(|c| c.code == code)
    }

    /// The `error_class` vocabulary value for a code's class letter; `None` for an
    /// unknown code or a letter outside the axis.
    pub fn class_of(&self, code: &str) -> Option<ErrorClass> {
        error_class_for_letter(&self.get(code)?.error_class)
    }

    /// The wire body for a code delivered as an HTTP error. `None` for codes that are
    /// results or operational stops, which have no `ErrorResponse`.
    pub fn error_response(&self, code: &str, trace_id: &str) -> Option<ErrorResponse> {
        let c = self.get(code).filter(|c| c.delivery == "http_error")?;
        Some(ErrorResponse {
            error_class: error_class_for_letter(&c.error_class)?,
            code: c.code.clone(),
            message_key: c.message_key.clone(),
            retryable: c.retryable,
            trace_id: trace_id.to_string(),
        })
    }

    /// Everything wrong with the catalog; empty when it keeps its rules.
    pub fn problems(&self) -> Vec<String> {
        let mut out = Vec::new();
        if self.contracts_version != crate::CONTRACTS_VERSION {
            out.push(format!(
                "contracts_version {} differs from the package version {}",
                self.contracts_version,
                crate::CONTRACTS_VERSION
            ));
        }
        // The class letters are exactly the `error_class` axis, and each names its value.
        for (letter, def) in &self.classes {
            match error_class_for_letter(letter) {
                None => out.push(format!(
                    "class {letter}: no error_class value has this letter"
                )),
                Some(c) if c.as_str() != def.vocabulary => out.push(format!(
                    "class {letter}: vocabulary {} should be {}",
                    def.vocabulary,
                    c.as_str()
                )),
                Some(_) => {}
            }
            if def.name_ko.trim().is_empty() {
                out.push(format!("class {letter}: name_ko must not be empty"));
            }
        }
        for c in ErrorClass::ALL {
            let letter = error_class_letter(*c).to_string();
            if !self.classes.contains_key(&letter) {
                out.push(format!("class {letter} ({}) is missing", c.as_str()));
            }
        }
        let mut codes = BTreeSet::new();
        let mut keys = BTreeSet::new();
        for c in &self.codes {
            let id = &c.code;
            if !codes.insert(id.as_str()) {
                out.push(format!("{id}: duplicate code"));
            }
            if !keys.insert(c.message_key.as_str()) {
                out.push(format!("{id}: message_key {} is not unique", c.message_key));
            }
            if c.message_key.is_empty() || c.message_key.contains(char::is_whitespace) {
                out.push(format!("{id}: message_key must be a non-empty token"));
            }
            match split_code(id) {
                None => out.push(format!("{id}: not ONJ-<zone>-<class>-<nnn>")),
                Some((zone, class)) => {
                    if zone != c.zone || class != c.error_class {
                        out.push(format!("{id}: zone/class fields differ from the code"));
                    }
                }
            }
            if !self.zones.contains_key(&c.zone) {
                out.push(format!("{id}: unknown zone {}", c.zone));
            }
            if !self.classes.contains_key(&c.error_class) {
                out.push(format!("{id}: unknown class {}", c.error_class));
            }
            if !self.screen_states.contains_key(&c.screen_state) {
                out.push(format!("{id}: no screen state {}", c.screen_state));
            }
            if c.screen_ko.trim().is_empty() || c.meaning_ko.trim().is_empty() {
                out.push(format!("{id}: meaning and screen text must not be empty"));
            }
            match (c.delivery.as_str(), c.http_status) {
                ("http_error", Some(s)) if (400..600).contains(&s) => {}
                ("result_state", Some(200)) => {}
                ("operational", None) => {}
                (d, s) => out.push(format!("{id}: delivery {d} does not fit http_status {s:?}")),
            }
            if !self.deliveries.contains_key(&c.delivery) {
                out.push(format!("{id}: unknown delivery {}", c.delivery));
            }
            if c.delivery == "operational" && c.screen_state != "operational" {
                out.push(format!(
                    "{id}: operational stops use the operational screen state"
                ));
            }
            if c.screen_state == "operational" && c.delivery != "operational" {
                out.push(format!(
                    "{id}: only operational stops use the operational state"
                ));
            }
            // Retrying only makes sense for something that was sent as an error.
            if c.retryable && c.delivery != "http_error" {
                out.push(format!("{id}: only HTTP errors can be retryable"));
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::checks::check_error_response;

    #[test]
    fn errors_catalog_keeps_its_rules() {
        assert_eq!(catalog().problems(), Vec::<String>::new());
    }

    #[test]
    fn errors_every_code_maps_to_a_screen_state() {
        let c = catalog();
        assert!(!c.codes.is_empty());
        for e in &c.codes {
            let s = c.screen_states.get(&e.screen_state);
            assert!(s.is_some(), "{} has no screen state", e.code);
            assert!(!e.screen_ko.is_empty(), "{}", e.code);
        }
    }

    /// The twelve codes 02 §4.2 lists, with their screen states from the same table.
    #[test]
    fn errors_catalog_has_the_codes_of_the_contract() {
        let c = catalog();
        let expect = [
            ("ONJ-AP-V-001", "error"),
            ("ONJ-AP-N-002", "changed"),
            ("ONJ-TW-U-010", "partial"),
            ("ONJ-TW-U-011", "undeterminable"),
            ("ONJ-AP-L-020", "error"),
            ("ONJ-PS-A-030", "error"),
            ("ONJ-PS-S-031", "error"),
            ("ONJ-DT-S-040", "operational"),
            ("ONJ-KN-S-050", "operational"),
            ("ONJ-KN-S-051", "operational"),
            ("ONJ-KN-S-052", "operational"),
            ("ONJ-AP-T-090", "error"),
        ];
        assert_eq!(c.codes.len(), expect.len());
        for (code, state) in expect {
            assert_eq!(c.get(code).unwrap().screen_state, state, "{code}");
        }
        assert_eq!(c.get("ONJ-PS-A-030").unwrap().http_status, Some(403));
        assert_eq!(c.get("ONJ-PS-S-031").unwrap().http_status, Some(409));
        assert_eq!(c.class_of("ONJ-PS-A-030"), Some(ErrorClass::Auth));
        assert_eq!(c.class_of("ONJ-AP-T-090"), Some(ErrorClass::Timeout));
        assert_eq!(c.class_of("ONJ-XX-X-999"), None);
    }

    /// Every class letter names its `error_class` value and every value has a letter.
    #[test]
    fn errors_class_letters_name_their_vocabulary_values() {
        let c = catalog();
        assert_eq!(c.classes.len(), ErrorClass::ALL.len());
        for class in ErrorClass::ALL {
            let def = &c.classes[&error_class_letter(*class).to_string()];
            assert_eq!(def.vocabulary, class.as_str());
        }
        let mut c = catalog();
        c.classes.get_mut("A").unwrap().vocabulary = "validation".into();
        assert!(c
            .problems()
            .iter()
            .any(|p| p.contains("class A: vocabulary")));
        let mut c = catalog();
        c.classes.remove("T");
        assert!(c
            .problems()
            .iter()
            .any(|p| p.contains("class T (timeout) is missing")));
        let mut c = catalog();
        let def = c.classes.remove("X").unwrap();
        c.classes.insert("Z".into(), def);
        assert!(c
            .problems()
            .iter()
            .any(|p| p.contains("class Z: no error_class")));
    }

    #[test]
    fn errors_unmapped_screen_state_is_reported() {
        let mut c = catalog();
        c.codes[0].screen_state = "nowhere".into();
        assert!(c.problems().iter().any(|p| p.contains("no screen state")));
        let mut c = catalog();
        c.screen_states.remove("error");
        assert!(!c.problems().is_empty());
    }

    #[test]
    fn errors_broken_catalogs_are_reported() {
        let mut c = catalog();
        c.codes[1].code = c.codes[0].code.clone();
        assert!(c.problems().iter().any(|p| p.contains("duplicate")));
        let mut c = catalog();
        c.codes[0].error_class = "X".into();
        assert!(!c.problems().is_empty());
        let mut c = catalog();
        c.codes[0].http_status = Some(200);
        assert!(!c.problems().is_empty());
        let mut c = catalog();
        c.contracts_version = "9.9.9".into();
        assert!(c.problems().iter().any(|p| p.contains("contracts_version")));
        assert_eq!(split_code("ONJ-AP-V-1"), None);
        assert_eq!(split_code("ONJ-ap-V-001"), None);
        assert_eq!(split_code("ONJ-AP-V-001"), Some(("AP", "V")));
    }

    #[test]
    fn errors_http_codes_build_valid_error_responses() {
        let c = catalog();
        for e in c.codes.iter().filter(|e| e.delivery == "http_error") {
            let r = c.error_response(&e.code, "trace-1").unwrap();
            assert!(check_error_response(&r).is_empty(), "{}", e.code);
            let doc = serde_json::to_value(&r).unwrap();
            let back: ErrorResponse = serde_json::from_value(doc).unwrap();
            assert_eq!(back, r);
        }
        // Results and operational stops have no wire error body.
        assert!(c.error_response("ONJ-TW-U-010", "t").is_none());
        assert!(c.error_response("ONJ-KN-S-051", "t").is_none());
        assert!(c.error_response("ONJ-XX-X-999", "t").is_none());
    }

    /// `json/error_response.schema.json` takes `error_class` from the vocabulary axis and
    /// fixes the zones and class letters of `code` in a pattern; both must match this
    /// catalog.
    #[test]
    fn errors_classes_match_the_error_response_schema() {
        let schema: serde_json::Value =
            serde_json::from_str(include_str!("../json/error_response.schema.json")).unwrap();
        let vocab_schema: serde_json::Value =
            serde_json::from_str(include_str!("../json/vocabulary.schema.json")).unwrap();
        let sorted = |text: &str| {
            let mut v: Vec<char> = text.chars().collect();
            v.sort_unstable();
            v
        };
        let c = catalog();
        let class_ref = schema["properties"]["error_class"]["$ref"]
            .as_str()
            .unwrap();
        assert_eq!(class_ref, "vocabulary.schema.json#/$defs/error_class");
        let mut in_vocab: Vec<&str> = vocab_schema["$defs"]["error_class"]["enum"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        in_vocab.sort_unstable();
        let mut words: Vec<&str> = c.classes.values().map(|d| d.vocabulary.as_str()).collect();
        words.sort_unstable();
        assert_eq!(in_vocab, words);
        let letters: String = c.classes.keys().cloned().collect();
        // `^ONJ-(CT|DT|...)-[VANSLUXT]-[0-9]{3}$`
        let code_pat = schema["properties"]["code"]["pattern"].as_str().unwrap();
        let zones_in_schema = code_pat.split(['(', ')']).nth(1).unwrap();
        let mut a: Vec<&str> = zones_in_schema.split('|').collect();
        a.sort_unstable();
        let b: Vec<&str> = c.zones.keys().map(String::as_str).collect();
        assert_eq!(a, b);
        let classes_in_code = code_pat.split(['[', ']']).nth(1).unwrap();
        assert_eq!(sorted(classes_in_code), sorted(&letters));
    }
}
