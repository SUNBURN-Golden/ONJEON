//! Minimal JSON Schema check for model output (type, enum, const, required,
//! properties, additionalProperties, items, min/max, length bounds).
//! Keywords outside this list are rejected rather than silently ignored, so a
//! schema can never look enforced when it is not.

use serde_json::Value;

const KNOWN: &[&str] = &[
    "$schema",
    "$id",
    "title",
    "description",
    "type",
    "enum",
    "const",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
];

/// Returns the list of violations (JSON-pointer-like path + reason); empty means valid.
pub fn validate(schema: &Value, value: &Value) -> Vec<String> {
    let mut out = Vec::new();
    check(schema, value, "", &mut out);
    out
}

/// Checks the schema itself: returns unsupported keywords/forms (empty means usable).
pub fn unsupported(schema: &Value) -> Vec<String> {
    let mut out = Vec::new();
    walk(schema, "", &mut out);
    out
}

fn walk(schema: &Value, path: &str, out: &mut Vec<String>) {
    let p = if path.is_empty() { "/" } else { path };
    let Some(s) = schema.as_object() else {
        if schema != &Value::Bool(true) {
            out.push(format!("{p}: unsupported schema form"));
        }
        return;
    };
    for k in s.keys().filter(|k| !KNOWN.contains(&k.as_str())) {
        out.push(format!("{p}: unsupported keyword {k}"));
    }
    if let Some(items) = s.get("items") {
        walk(items, &format!("{path}/items"), out);
    }
    if let Some(sub @ Value::Object(_)) = s.get("additionalProperties") {
        walk(sub, &format!("{path}/additionalProperties"), out);
    }
    if let Some(Value::Object(ps)) = s.get("properties") {
        for (k, x) in ps {
            walk(x, &format!("{path}/{k}"), out);
        }
    }
}

fn type_ok(t: &str, v: &Value) -> bool {
    match t {
        "object" => v.is_object(),
        "array" => v.is_array(),
        "string" => v.is_string(),
        "boolean" => v.is_boolean(),
        "null" => v.is_null(),
        "integer" => v.is_i64() || v.is_u64() || v.as_f64().is_some_and(|f| f.fract() == 0.0),
        "number" => v.is_number(),
        _ => false,
    }
}

fn check(schema: &Value, v: &Value, path: &str, out: &mut Vec<String>) {
    let p = if path.is_empty() { "/" } else { path };
    let Some(s) = schema.as_object() else {
        if schema != &Value::Bool(true) {
            out.push(format!("{p}: unsupported schema form"));
        }
        return;
    };
    for k in s.keys() {
        if !KNOWN.contains(&k.as_str()) {
            out.push(format!("{p}: unsupported keyword {k}"));
        }
    }
    if let Some(t) = s.get("type") {
        let ok = match t {
            Value::String(t) => type_ok(t, v),
            Value::Array(ts) => ts.iter().any(|t| t.as_str().is_some_and(|t| type_ok(t, v))),
            _ => false,
        };
        if !ok {
            out.push(format!("{p}: wrong type"));
            return;
        }
    }
    if let Some(Value::Array(e)) = s.get("enum") {
        if !e.contains(v) {
            out.push(format!("{p}: not in enum"));
        }
    }
    if let Some(c) = s.get("const") {
        if c != v {
            out.push(format!("{p}: not equal to const"));
        }
    }
    if let Some(n) = v.as_f64() {
        if s.get("minimum")
            .and_then(Value::as_f64)
            .is_some_and(|m| n < m)
        {
            out.push(format!("{p}: below minimum"));
        }
        if s.get("maximum")
            .and_then(Value::as_f64)
            .is_some_and(|m| n > m)
        {
            out.push(format!("{p}: above maximum"));
        }
    }
    if let Some(st) = v.as_str() {
        let len = st.chars().count() as u64;
        if s.get("minLength")
            .and_then(Value::as_u64)
            .is_some_and(|m| len < m)
        {
            out.push(format!("{p}: too short"));
        }
        if s.get("maxLength")
            .and_then(Value::as_u64)
            .is_some_and(|m| len > m)
        {
            out.push(format!("{p}: too long"));
        }
    }
    if let Some(a) = v.as_array() {
        let len = a.len() as u64;
        if s.get("minItems")
            .and_then(Value::as_u64)
            .is_some_and(|m| len < m)
        {
            out.push(format!("{p}: too few items"));
        }
        if s.get("maxItems")
            .and_then(Value::as_u64)
            .is_some_and(|m| len > m)
        {
            out.push(format!("{p}: too many items"));
        }
        if let Some(items) = s.get("items") {
            for (i, x) in a.iter().enumerate() {
                check(items, x, &format!("{path}/{i}"), out);
            }
        }
    }
    if let Some(o) = v.as_object() {
        if let Some(Value::Array(req)) = s.get("required") {
            for r in req.iter().filter_map(Value::as_str) {
                if !o.contains_key(r) {
                    out.push(format!("{p}: missing required {r}"));
                }
            }
        }
        let props = s.get("properties").and_then(Value::as_object);
        for (k, x) in o {
            match props.and_then(|ps| ps.get(k)) {
                Some(ps) => check(ps, x, &format!("{path}/{k}"), out),
                None => match s.get("additionalProperties") {
                    Some(Value::Bool(false)) => out.push(format!("{p}: unexpected property {k}")),
                    Some(sub @ Value::Object(_)) => check(sub, x, &format!("{path}/{k}"), out),
                    _ => {}
                },
            }
        }
    }
}
