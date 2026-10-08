//! Rule loading: JSON rule files are parsed into an allow-listed expression tree.
//! Anything outside the allow-list (unknown operators, floats, bare arrays,
//! missing rounding, unknown top-level keys) is rejected at load time.

use crate::value::{parse_rate, Value};
use serde_json::Value as J;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;

pub const SCHEMA_VERSION: &str = "rule-0.1";
pub const UNKNOWN_POLICY: &str = "use_three_valued_logic_never_default_to_zero";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputType {
    Bool,
    Int,
    MoneyKrw,
    Date,
    Str,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CmpOp {
    Eq,
    Ne,
    Lt,
    Lte,
    Gt,
    Gte,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Rounding {
    Floor,
    Ceil,
    HalfUp,
    HalfEven,
    /// The source does not state a rounding rule: the result is a [floor, ceil] range.
    Unspecified,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DurUnit {
    Day,
    CalendarMonth,
    CalendarYear,
}

#[derive(Debug, Clone)]
pub enum Expr {
    Lit(Value),
    Input(String),
    All(Vec<Expr>),
    Any(Vec<Expr>),
    Not(Box<Expr>),
    Cmp(CmpOp, Box<Expr>, Box<Expr>),
    If(Box<Expr>, Box<Expr>, Box<Expr>),
    MultiplyRate {
        money: Box<Expr>,
        rate: Box<Expr>,
        rounding: Rounding,
        unit: i64,
    },
    Add(Vec<Expr>),
    Min(Vec<Expr>),
    Max(Vec<Expr>),
    ApplyCap(Box<Expr>, Box<Expr>),
    DaysBetween {
        a: Box<Expr>,
        b: Box<Expr>,
        inclusive_start: bool,
        inclusive_end: bool,
    },
    DateAdd {
        date: Box<Expr>,
        value: i64,
        unit: DurUnit,
    },
}

impl Expr {
    pub fn op_name(&self) -> &'static str {
        match self {
            Expr::Lit(_) => "lit",
            Expr::Input(_) => "input",
            Expr::All(_) => "all",
            Expr::Any(_) => "any",
            Expr::Not(_) => "not",
            Expr::Cmp(op, _, _) => match op {
                CmpOp::Eq => "eq",
                CmpOp::Ne => "ne",
                CmpOp::Lt => "lt",
                CmpOp::Lte => "lte",
                CmpOp::Gt => "gt",
                CmpOp::Gte => "gte",
            },
            Expr::If(..) => "if",
            Expr::MultiplyRate { .. } => "multiply_rate",
            Expr::Add(_) => "add",
            Expr::Min(_) => "min",
            Expr::Max(_) => "max",
            Expr::ApplyCap(..) => "apply_cap",
            Expr::DaysBetween { .. } => "days_between",
            Expr::DateAdd { .. } => "date_add",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuleError {
    pub path: String,
    pub message: String,
}

impl RuleError {
    fn at(path: &str, message: impl Into<String>) -> Self {
        RuleError {
            path: path.to_string(),
            message: message.into(),
        }
    }
}

impl fmt::Display for RuleError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "rule error at {}: {}", self.path, self.message)
    }
}

impl std::error::Error for RuleError {}

#[derive(Debug, Clone)]
pub struct Rule {
    pub rule_id: String,
    /// Version of this rule's content. Bump whenever the clause or its encoding changes.
    pub rule_version: String,
    /// Dataset release that published this rule. Required unless `fixture_only`.
    pub release_id: Option<String>,
    /// SHA-256 of the canonical rule JSON (keys sorted, `release_id` excluded).
    /// Identifies the exact content even if someone forgets to bump `rule_version`.
    pub content_hash: String,
    pub schema_version: String,
    pub publication_state: String,
    pub evidence_refs: Vec<String>,
    pub inputs: BTreeMap<String, InputType>,
    pub eligibility: Expr,
    pub amount: Expr,
}

const TOP_LEVEL_KEYS: [&str; 12] = [
    "example_kind",
    "rule_id",
    "rule_version",
    "release_id",
    "schema_version",
    "calendar",
    "inputs",
    "eligibility",
    "amount",
    "unknown_policy",
    "evidence_refs",
    "publication_state",
];

impl Rule {
    pub fn from_json_str(s: &str) -> Result<Rule, RuleError> {
        let v: J = serde_json::from_str(s)
            .map_err(|e| RuleError::at("$", format!("invalid JSON: {e}")))?;
        Rule::from_json(&v)
    }

    pub fn from_json(v: &J) -> Result<Rule, RuleError> {
        let obj = v
            .as_object()
            .ok_or_else(|| RuleError::at("$", "rule must be a JSON object"))?;
        for k in obj.keys() {
            if !TOP_LEVEL_KEYS.contains(&k.as_str()) {
                return Err(RuleError::at("$", format!("unknown top-level key `{k}`")));
            }
        }
        let get_str = |key: &str| -> Result<String, RuleError> {
            obj.get(key)
                .and_then(J::as_str)
                .map(str::to_string)
                .ok_or_else(|| RuleError::at("$", format!("`{key}` must be a string")))
        };
        let rule_id = get_str("rule_id")?;
        let rule_version = get_str("rule_version")?;
        if rule_version.trim().is_empty() {
            return Err(RuleError::at("rule_version", "must not be empty"));
        }
        let release_id = match obj.get("release_id") {
            None | Some(J::Null) => None,
            Some(J::String(r)) if !r.trim().is_empty() => Some(r.clone()),
            _ => return Err(RuleError::at("release_id", "must be a non-empty string")),
        };
        let schema_version = get_str("schema_version")?;
        if schema_version != SCHEMA_VERSION {
            return Err(RuleError::at(
                "schema_version",
                format!("expected {SCHEMA_VERSION}, got {schema_version}"),
            ));
        }
        let unknown_policy = get_str("unknown_policy")?;
        if unknown_policy != UNKNOWN_POLICY {
            return Err(RuleError::at(
                "unknown_policy",
                format!("must be `{UNKNOWN_POLICY}`"),
            ));
        }
        if let Some(cal) = obj.get("calendar") {
            if cal.as_str() != Some("Asia/Seoul") {
                return Err(RuleError::at(
                    "calendar",
                    "only Asia/Seoul is supported in rule-0.1",
                ));
            }
        }
        let publication_state = get_str("publication_state")?;
        let evidence_refs: Vec<String> = match obj.get("evidence_refs") {
            Some(J::Array(a)) => a
                .iter()
                .map(|x| {
                    x.as_str()
                        .map(str::to_string)
                        .ok_or_else(|| RuleError::at("evidence_refs", "must be strings"))
                })
                .collect::<Result<_, _>>()?,
            _ => return Err(RuleError::at("evidence_refs", "must be an array")),
        };
        if publication_state != "fixture_only" && evidence_refs.is_empty() {
            return Err(RuleError::at(
                "evidence_refs",
                "a publishable rule needs at least one evidence reference (principle 5)",
            ));
        }
        if publication_state != "fixture_only" && release_id.is_none() {
            return Err(RuleError::at(
                "release_id",
                "a publishable rule must name the release it belongs to",
            ));
        }
        let mut inputs = BTreeMap::new();
        match obj.get("inputs") {
            Some(J::Object(m)) => {
                for (name, ty) in m {
                    let ty = match ty.as_str() {
                        Some("bool") => InputType::Bool,
                        Some("int") => InputType::Int,
                        Some("money_krw") => InputType::MoneyKrw,
                        Some("date") => InputType::Date,
                        Some("string") => InputType::Str,
                        _ => {
                            return Err(RuleError::at(
                                &format!("inputs.{name}"),
                                "type must be bool|int|money_krw|date|string",
                            ))
                        }
                    };
                    inputs.insert(name.clone(), ty);
                }
            }
            _ => return Err(RuleError::at("inputs", "must be an object of name -> type")),
        }
        let eligibility = parse_expr(
            obj.get("eligibility")
                .ok_or_else(|| RuleError::at("eligibility", "missing"))?,
            &inputs,
            "eligibility",
        )?;
        let amount = parse_expr(
            obj.get("amount")
                .ok_or_else(|| RuleError::at("amount", "missing"))?,
            &inputs,
            "amount",
        )?;
        Ok(Rule {
            rule_id,
            rule_version,
            release_id,
            content_hash: content_hash(v),
            schema_version,
            publication_state,
            evidence_refs,
            inputs,
            eligibility,
            amount,
        })
    }
}

/// SHA-256 over the canonical serialization (serde_json sorts object keys),
/// excluding `release_id` so re-releasing identical content keeps the same hash.
fn content_hash(v: &J) -> String {
    let mut canonical = v.clone();
    if let Some(o) = canonical.as_object_mut() {
        o.remove("release_id");
    }
    let bytes = serde_json::to_vec(&canonical).expect("a parsed JSON value always serializes");
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn args<'a>(v: &'a J, min: usize, max: usize, path: &str) -> Result<&'a Vec<J>, RuleError> {
    let a = v
        .as_array()
        .ok_or_else(|| RuleError::at(path, "operator arguments must be an array"))?;
    if a.len() < min || a.len() > max {
        return Err(RuleError::at(
            path,
            format!("expected {min}..={max} arguments, got {}", a.len()),
        ));
    }
    Ok(a)
}

fn parse_expr(v: &J, inputs: &BTreeMap<String, InputType>, path: &str) -> Result<Expr, RuleError> {
    match v {
        J::Bool(b) => Ok(Expr::Lit(Value::Bool(*b))),
        J::Number(n) => match n.as_i64() {
            Some(i) => Ok(Expr::Lit(Value::Int(i))),
            None => Err(RuleError::at(
                path,
                "floating-point numbers are not allowed; use a decimal string for rates",
            )),
        },
        J::String(s) => {
            if inputs.contains_key(s) {
                Ok(Expr::Input(s.clone()))
            } else if let Some(r) = parse_rate(s) {
                Ok(Expr::Lit(r))
            } else {
                Err(RuleError::at(
                    path,
                    format!("`{s}` is neither a declared input nor a decimal rate"),
                ))
            }
        }
        J::Null => Err(RuleError::at(path, "null is not an expression")),
        J::Array(_) => Err(RuleError::at(path, "a bare array is not an expression")),
        J::Object(map) => {
            if map.contains_key("if") {
                let mut keys: Vec<&str> = map.keys().map(String::as_str).collect();
                keys.sort_unstable();
                if keys != ["else", "if", "then"] {
                    return Err(RuleError::at(
                        path,
                        "an `if` object must have exactly if/then/else",
                    ));
                }
                return Ok(Expr::If(
                    Box::new(parse_expr(&map["if"], inputs, &format!("{path}.if"))?),
                    Box::new(parse_expr(&map["then"], inputs, &format!("{path}.then"))?),
                    Box::new(parse_expr(&map["else"], inputs, &format!("{path}.else"))?),
                ));
            }
            if map.len() != 1 {
                return Err(RuleError::at(
                    path,
                    "an operator object must have exactly one key",
                ));
            }
            let (op, a) = map.iter().next().expect("len checked");
            let p = format!("{path}.{op}");
            let list = |a: &J, min: usize, p: &str| -> Result<Vec<Expr>, RuleError> {
                let items = args(a, min, 64, p)?;
                items
                    .iter()
                    .enumerate()
                    .map(|(i, x)| parse_expr(x, inputs, &format!("{p}[{i}]")))
                    .collect()
            };
            let two = |a: &J, p: &str| -> Result<(Box<Expr>, Box<Expr>), RuleError> {
                let items = args(a, 2, 2, p)?;
                Ok((
                    Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"))?),
                    Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"))?),
                ))
            };
            match op.as_str() {
                "all" => Ok(Expr::All(list(a, 1, &p)?)),
                "any" => Ok(Expr::Any(list(a, 1, &p)?)),
                "not" => Ok(Expr::Not(Box::new(parse_expr(a, inputs, &p)?))),
                "eq" | "ne" | "lt" | "lte" | "gt" | "gte" => {
                    let (l, r) = two(a, &p)?;
                    let cmp = match op.as_str() {
                        "eq" => CmpOp::Eq,
                        "ne" => CmpOp::Ne,
                        "lt" => CmpOp::Lt,
                        "lte" => CmpOp::Lte,
                        "gt" => CmpOp::Gt,
                        _ => CmpOp::Gte,
                    };
                    Ok(Expr::Cmp(cmp, l, r))
                }
                "input" => match a.as_str() {
                    Some(name) if inputs.contains_key(name) => Ok(Expr::Input(name.to_string())),
                    _ => Err(RuleError::at(&p, "must name a declared input")),
                },
                "rate" => a
                    .as_str()
                    .and_then(parse_rate)
                    .map(Expr::Lit)
                    .ok_or_else(|| RuleError::at(&p, "must be a non-negative decimal string")),
                "krw" => match a.as_i64() {
                    Some(n) if n >= 0 => Ok(Expr::Lit(Value::Money(n))),
                    _ => Err(RuleError::at(&p, "must be a non-negative integer")),
                },
                "date" => a
                    .as_str()
                    .and_then(crate::date::parse_date)
                    .map(|d| Expr::Lit(Value::Date(d)))
                    .ok_or_else(|| RuleError::at(&p, "must be a valid YYYY-MM-DD date")),
                "multiply" => Err(RuleError::at(&p, "`multiply` is not allowed; use `multiply_rate` with explicit rounding and unit")),
                "multiply_rate" => {
                    let items = args(a, 3, 3, &p)?;
                    let params = items[2].as_object().ok_or_else(|| RuleError::at(&p, "third argument must be {rounding, unit}"))?;
                    let rounding = match params.get("rounding").and_then(J::as_str) {
                        Some("floor") => Rounding::Floor,
                        Some("ceil") => Rounding::Ceil,
                        Some("half_up") => Rounding::HalfUp,
                        Some("half_even") => Rounding::HalfEven,
                        Some("unspecified") => Rounding::Unspecified,
                        _ => return Err(RuleError::at(&p, "rounding is required: floor|ceil|half_up|half_even|unspecified")),
                    };
                    let unit = match params.get("unit").and_then(J::as_i64) {
                        Some(u @ (1 | 10 | 100 | 1000)) => u,
                        _ => return Err(RuleError::at(&p, "unit is required: 1|10|100|1000")),
                    };
                    if params.len() != 2 {
                        return Err(RuleError::at(&p, "only rounding and unit are allowed"));
                    }
                    Ok(Expr::MultiplyRate {
                        money: Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"))?),
                        rate: Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"))?),
                        rounding,
                        unit,
                    })
                }
                "add" => Ok(Expr::Add(list(a, 2, &p)?)),
                "min" => Ok(Expr::Min(list(a, 2, &p)?)),
                "max" => Ok(Expr::Max(list(a, 2, &p)?)),
                "apply_cap" => {
                    let (m, c) = two(a, &p)?;
                    Ok(Expr::ApplyCap(m, c))
                }
                "days_between" => {
                    let items = args(a, 3, 3, &p)?;
                    let params = items[2].as_object().ok_or_else(|| RuleError::at(&p, "third argument must be {inclusive_start, inclusive_end}"))?;
                    let (Some(s), Some(e)) = (
                        params.get("inclusive_start").and_then(J::as_bool),
                        params.get("inclusive_end").and_then(J::as_bool),
                    ) else {
                        return Err(RuleError::at(&p, "inclusive_start and inclusive_end are required booleans"));
                    };
                    if params.len() != 2 {
                        return Err(RuleError::at(&p, "only inclusive_start and inclusive_end are allowed"));
                    }
                    Ok(Expr::DaysBetween {
                        a: Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"))?),
                        b: Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"))?),
                        inclusive_start: s,
                        inclusive_end: e,
                    })
                }
                "date_add" => {
                    let items = args(a, 2, 2, &p)?;
                    let params = items[1].as_object().ok_or_else(|| RuleError::at(&p, "second argument must be {value, unit[, month_end]}"))?;
                    let value = params.get("value").and_then(J::as_i64).ok_or_else(|| RuleError::at(&p, "value must be an integer"))?;
                    let unit = match params.get("unit").and_then(J::as_str) {
                        Some("day") => DurUnit::Day,
                        Some("calendar_month") => DurUnit::CalendarMonth,
                        Some("calendar_year") => DurUnit::CalendarYear,
                        _ => return Err(RuleError::at(&p, "unit must be day|calendar_month|calendar_year")),
                    };
                    // Bounded to the supported calendar span (1900..=2199, 300 years).
                    let limit = match unit {
                        DurUnit::Day => 110_000,
                        DurUnit::CalendarMonth => 3_600,
                        DurUnit::CalendarYear => 300,
                    };
                    if value.abs() > limit {
                        return Err(RuleError::at(&p, format!("|value| must be <= {limit} for this unit")));
                    }
                    if unit != DurUnit::Day && params.get("month_end").and_then(J::as_str) != Some("clamp") {
                        return Err(RuleError::at(&p, "month/year arithmetic requires month_end=\"clamp\" (never assume 365 days per year)"));
                    }
                    Ok(Expr::DateAdd { date: Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"))?), value, unit })
                }
                other => Err(RuleError::at(path, format!("operator `{other}` is not in the allow-list"))),
            }
        }
    }
}
