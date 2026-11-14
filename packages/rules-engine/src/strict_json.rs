//! Deserialize JSON without silently discarding repeated object members.
//! Keys are checked after decoding, at every depth, before a `Value` loses them.
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{Map, Value};
use std::fmt;

/// Parse a complete JSON artifact, rejecting duplicate object keys at every depth.
///
/// Use this before extracting metadata or passing a `Value` to a rule loader:
/// ordinary `Value` deserialization irreversibly discards duplicate members.
pub fn from_slice(bytes: &[u8]) -> Result<Value, serde_json::Error> {
    serde_json::from_slice::<StrictValue>(bytes).map(|value| value.0)
}

pub(crate) struct StrictValue(pub Value);

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(StrictVisitor).map(StrictValue)
    }
}

struct StrictVisitor;

impl<'de> Visitor<'de> for StrictVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("JSON with unique object keys")
    }

    fn visit_unit<E: de::Error>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }

    fn visit_bool<E: de::Error>(self, value: bool) -> Result<Value, E> {
        Ok(Value::Bool(value))
    }

    fn visit_i64<E: de::Error>(self, value: i64) -> Result<Value, E> {
        Ok(value.into())
    }

    fn visit_u64<E: de::Error>(self, value: u64) -> Result<Value, E> {
        Ok(value.into())
    }

    fn visit_f64<E: de::Error>(self, value: f64) -> Result<Value, E> {
        serde_json::Number::from_f64(value)
            .map(Value::Number)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }

    fn visit_str<E: de::Error>(self, value: &str) -> Result<Value, E> {
        Ok(Value::String(value.to_owned()))
    }

    fn visit_string<E: de::Error>(self, value: String) -> Result<Value, E> {
        Ok(Value::String(value))
    }

    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Value, A::Error> {
        let mut values = Vec::new();
        while let Some(StrictValue(value)) = seq.next_element()? {
            values.push(value);
        }
        Ok(Value::Array(values))
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Value, A::Error> {
        let mut values = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if values.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate JSON key {key:?}")));
            }
            let StrictValue(value) = map.next_value()?;
            values.insert(key, value);
        }
        Ok(Value::Object(values))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unique_json_preserves_serde_value_semantics() {
        let text = r#"{"null":null,"bool":[true,false],"numbers":[-9223372036854775808,18446744073709551615,1.5,-0.0,1e20],"text":"한글\n\"\\","nested":[{"a":1},{"a":2}]}"#;
        assert_eq!(
            from_slice(text.as_bytes()).unwrap(),
            serde_json::from_str::<Value>(text).unwrap()
        );
    }

    #[test]
    fn malformed_trailing_and_excessively_nested_json_still_fail() {
        for text in ["", "{", "[1,]", "{} {}", r#"{"x":1,}"#, "1e999"] {
            assert!(from_slice(text.as_bytes()).is_err(), "{text}");
        }
        let text = format!("{}null{}", "[".repeat(130), "]".repeat(130));
        let error = from_slice(text.as_bytes()).unwrap_err();
        assert!(error.to_string().contains("recursion limit exceeded"));
    }

    #[test]
    fn artifact_bytes_reject_duplicates_and_invalid_utf8() {
        for bytes in [
            br#"{"inputs_from_outside_dsl":[],"inputs_from_outside_dsl":[]}"#.as_slice(),
            br#"{"inputs_from_outside_dsl":[{"duration":{"value":90,"value":1}}]}"#,
            br#"{"amount":{"krw":999999999,"\u006brw":1}}"#,
        ] {
            let error = from_slice(bytes).unwrap_err();
            assert!(error.to_string().contains("duplicate JSON key"), "{error}");
            assert!(error.line() > 0 && error.column() > 0, "{error}");
        }
        assert!(from_slice(b"{\"text\":\"\xff\"}").is_err());
    }
}
