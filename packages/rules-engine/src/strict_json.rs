//! Deserialize JSON without silently discarding repeated object members.
//! Keys are checked after decoding, at every depth, before a `Value` loses them.
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{Map, Value};
use std::fmt;

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
            serde_json::from_str::<StrictValue>(text).unwrap().0,
            serde_json::from_str::<Value>(text).unwrap()
        );
    }

    #[test]
    fn malformed_trailing_and_excessively_nested_json_still_fail() {
        for text in ["", "{", "[1,]", "{} {}", r#"{"x":1,}"#, "1e999"] {
            assert!(serde_json::from_str::<StrictValue>(text).is_err(), "{text}");
        }
        let text = format!("{}null{}", "[".repeat(130), "]".repeat(130));
        let error = serde_json::from_str::<StrictValue>(&text).err().unwrap();
        assert!(error.to_string().contains("recursion limit exceeded"));
    }
}
