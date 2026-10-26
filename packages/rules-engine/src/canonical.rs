use serde_json::Value as J;
use std::collections::BTreeMap;

/// Canonical JSON tree for hashing. Objects are `BTreeMap`s, so keys are emitted in
/// byte-wise order no matter how `serde_json::Map` is configured (its `preserve_order`
/// feature, enabled by any crate in the build graph, would otherwise make the hash
/// depend on key order in the file).
#[derive(serde::Serialize)]
#[serde(untagged)]
pub(crate) enum Canon {
    Null,
    Bool(bool),
    Number(serde_json::Number),
    String(String),
    Array(Vec<Canon>),
    Object(BTreeMap<String, Canon>),
}

pub(crate) fn canonicalize(v: &J) -> Canon {
    match v {
        J::Null => Canon::Null,
        J::Bool(b) => Canon::Bool(*b),
        J::Number(n) => Canon::Number(n.clone()),
        J::String(s) => Canon::String(s.clone()),
        J::Array(a) => Canon::Array(a.iter().map(canonicalize).collect()),
        J::Object(o) => Canon::Object(
            o.iter()
                .map(|(k, x)| (k.clone(), canonicalize(x)))
                .collect(),
        ),
    }
}

/// Compact UTF-8 JSON with recursively sorted object keys and no trailing newline.
pub(crate) fn canonical_bytes(v: &J) -> Vec<u8> {
    serde_json::to_vec(&canonicalize(v)).expect("a canonical JSON tree always serializes")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::value::Value;

    #[test]
    fn runtime_struct_fields_are_sorted_recursively_and_types_are_explicit() {
        let values = [
            Value::MoneyRange { min: 1, max: 2 },
            Value::Rate { num: 5, den: 10 },
            Value::Unknown,
        ];
        assert_eq!(
            String::from_utf8(canonical_bytes(&serde_json::to_value(values).unwrap())).unwrap(),
            r#"[{"type":"money_range","value":{"max":2,"min":1}},{"type":"rate","value":{"den":10,"num":5}},{"type":"unknown"}]"#
        );
    }
}
