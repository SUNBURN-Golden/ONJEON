//! Rule loading: JSON rule files are parsed into an allow-listed expression tree.
//! Anything outside the allow-list (unknown operators, floats, bare arrays,
//! missing rounding, unknown top-level keys) is rejected at load time.

use crate::value::{parse_rate, Value};
use serde_json::Value as J;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;

pub const SCHEMA_VERSION: &str = "rule-0.1";
/// rule-0.2 adds the operators listed in GAP_REPORT section 5; everything in 0.1 still loads.
pub const SCHEMA_VERSION_0_2: &str = "rule-0.2";
/// Allowed `contract_effect` values (rule-0.2).
pub const CONTRACT_EFFECTS: [&str; 3] = ["none", "void_refund_premium", "terminated_pay_reserve"];
pub const UNKNOWN_POLICY: &str = "use_three_valued_logic_never_default_to_zero";
/// Allowed `publication_state` values; must match `publication_state` in vocabulary.json.
pub const PUBLICATION_STATES: [&str; 3] = ["fixture_only", "candidate", "released"];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputType {
    Bool,
    Int,
    MoneyKrw,
    Date,
    Str,
    /// rule-0.2: list of `{class, krw}` events (krw may be null = unknown).
    ClassMoneyList,
}

/// What a rule does to the contract itself besides paying (rule-0.2, G23).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ContractEffect {
    None,
    VoidRefundPremium,
    TerminatedPayReserve,
}

/// Static type of an expression, checked while the rule loads. `Money` covers both an exact
/// amount and a range from unspecified rounding; the range is a runtime value, not a type.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Ty {
    Bool,
    Int,
    Money,
    Rate,
    Date,
    Str,
    List,
}

impl Ty {
    fn name(self) -> &'static str {
        match self {
            Ty::Bool => "bool",
            Ty::Int => "int",
            Ty::Money => "money",
            Ty::Rate => "rate",
            Ty::Date => "date",
            Ty::Str => "string",
            Ty::List => "class_money_list",
        }
    }
}

impl From<InputType> for Ty {
    fn from(t: InputType) -> Ty {
        match t {
            InputType::Bool => Ty::Bool,
            InputType::Int => Ty::Int,
            InputType::MoneyKrw => Ty::Money,
            InputType::Date => Ty::Date,
            InputType::Str => Ty::Str,
            InputType::ClassMoneyList => Ty::List,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum CmpOp {
    Eq,
    Ne,
    Lt,
    Lte,
    Gt,
    Gte,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Rounding {
    Floor,
    Ceil,
    HalfUp,
    HalfEven,
    /// The source does not state a rounding rule: the result is a [floor, ceil] range.
    Unspecified,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum DurUnit {
    Day,
    CalendarMonth,
    CalendarYear,
}

#[derive(Debug, Clone)]
pub(crate) enum Expr {
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
    // ---- rule-0.2
    MultiplyCount(Box<Expr>, Box<Expr>),
    SubtractFloor0(Box<Expr>, Box<Expr>),
    ProRata {
        money: Box<Expr>,
        part: Box<Expr>,
        whole: Box<Expr>,
        rounding: Rounding,
        unit: i64,
    },
    DivideCount {
        money: Box<Expr>,
        count: Box<Expr>,
        rounding: Rounding,
        unit: i64,
    },
    AnniversaryBand {
        from: Box<Expr>,
        at: Box<Expr>,
        /// `(years, value)` thresholds, ascending, first is 0.
        bands: Vec<(i64, Value)>,
        boundary: Boundary,
    },
    /// Sum over classes of the largest amount in the class. Holds the list input's name.
    MaxOver(String),
}

/// Whether a band that starts at an anniversary already applies on the anniversary day itself.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Boundary {
    /// `lower_inclusive`: the new band applies from the anniversary day.
    Lower,
    /// `upper_inclusive`: the old band still applies on the anniversary day; the new one starts the day after.
    Upper,
}

impl Expr {
    pub(crate) fn op_name(&self) -> &'static str {
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
            Expr::MultiplyCount(..) => "multiply_count",
            Expr::SubtractFloor0(..) => "subtract_floor0",
            Expr::ProRata { .. } => "pro_rata",
            Expr::DivideCount { .. } => "divide_count",
            Expr::AnniversaryBand { .. } => "anniversary_band",
            Expr::MaxOver(_) => "max_over",
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

/// A validated, immutable rule.
///
/// The only way to obtain a `Rule` is [`Rule::from_json`] / [`Rule::from_json_str`],
/// which validate the rule and compute its content hash from the same JSON that
/// the expression tree was parsed from. Fields are private and there is no `&mut`
/// API, so the logic that is evaluated can never drift from the hash and version
/// that results report. To change a rule, edit its JSON (see [`Rule::source_json`])
/// and load it again, which re-validates and re-hashes.
///
/// Reading works through accessors (this example compiles and runs; the two
/// below differ only in the assignment, which proves they fail on privacy):
///
/// ```
/// # let json = r#"{"rule_id":"r","rule_version":"1","schema_version":"rule-0.1","inputs":{},
/// #   "eligibility":true,"amount":{"krw":1},
/// #   "unknown_policy":"use_three_valued_logic_never_default_to_zero",
/// #   "evidence_refs":[],"publication_state":"fixture_only"}"#;
/// let mut rule = onjeon_rules_engine::Rule::from_json_str(json).unwrap();
/// let other = rule.clone();
/// assert_eq!(rule.rule_version(), "1");
/// assert_eq!(rule.content_hash().len(), 64);
/// rule = other; // replacing a whole validated rule is fine
/// # let _ = rule;
/// ```
///
/// ```compile_fail
/// # let json = r#"{"rule_id":"r","rule_version":"1","schema_version":"rule-0.1","inputs":{},
/// #   "eligibility":true,"amount":{"krw":1},
/// #   "unknown_policy":"use_three_valued_logic_never_default_to_zero",
/// #   "evidence_refs":[],"publication_state":"fixture_only"}"#;
/// let mut rule = onjeon_rules_engine::Rule::from_json_str(json).unwrap();
/// rule.content_hash = String::new(); // private: does not compile
/// ```
///
/// ```compile_fail
/// # let json = r#"{"rule_id":"r","rule_version":"1","schema_version":"rule-0.1","inputs":{},
/// #   "eligibility":true,"amount":{"krw":1},
/// #   "unknown_policy":"use_three_valued_logic_never_default_to_zero",
/// #   "evidence_refs":[],"publication_state":"fixture_only"}"#;
/// let mut rule = onjeon_rules_engine::Rule::from_json_str(json).unwrap();
/// let other = rule.clone();
/// rule.amount = other.amount; // private: does not compile
/// ```
#[derive(Debug, Clone)]
pub struct Rule {
    pub(crate) rule_id: String,
    /// Version of this rule's content. Bump whenever the clause or its encoding changes.
    pub(crate) rule_version: String,
    /// Dataset release that published this rule. Required unless `fixture_only`.
    pub(crate) release_id: Option<String>,
    /// SHA-256 of the canonical rule JSON (keys sorted, `release_id` excluded).
    /// Identifies the exact content even if someone forgets to bump `rule_version`.
    pub(crate) content_hash: String,
    pub(crate) schema_version: String,
    pub(crate) publication_state: String,
    pub(crate) evidence_refs: Vec<String>,
    pub(crate) inputs: BTreeMap<String, InputType>,
    pub(crate) eligibility: Expr,
    pub(crate) amount: Expr,
    pub(crate) contract_effect: ContractEffect,
    /// The JSON this rule was loaded from, in canonical form.
    pub(crate) source: J,
}

const TOP_LEVEL_KEYS: [&str; 13] = [
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
    "contract_effect",
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
        if schema_version != SCHEMA_VERSION && schema_version != SCHEMA_VERSION_0_2 {
            return Err(RuleError::at(
                "schema_version",
                format!("expected {SCHEMA_VERSION} or {SCHEMA_VERSION_0_2}, got {schema_version}"),
            ));
        }
        let v02 = schema_version == SCHEMA_VERSION_0_2;
        let contract_effect = match obj.get("contract_effect") {
            None => ContractEffect::None,
            Some(_) if !v02 => {
                return Err(RuleError::at(
                    "contract_effect",
                    "requires schema_version rule-0.2",
                ))
            }
            Some(J::String(e)) => match e.as_str() {
                "none" => ContractEffect::None,
                "void_refund_premium" => ContractEffect::VoidRefundPremium,
                "terminated_pay_reserve" => ContractEffect::TerminatedPayReserve,
                _ => {
                    return Err(RuleError::at(
                        "contract_effect",
                        format!("must be one of {}", CONTRACT_EFFECTS.join("|")),
                    ))
                }
            },
            Some(_) => {
                return Err(RuleError::at(
                    "contract_effect",
                    format!("must be one of {}", CONTRACT_EFFECTS.join("|")),
                ))
            }
        };
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
        if !PUBLICATION_STATES.contains(&publication_state.as_str()) {
            return Err(RuleError::at(
                "publication_state",
                "must be fixture_only|candidate|released (packages/schemas/vocabulary.json)",
            ));
        }
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
        if let Some(i) = evidence_refs.iter().position(|r| r.trim().is_empty()) {
            return Err(RuleError::at(
                &format!("evidence_refs[{i}]"),
                "evidence reference must not be blank",
            ));
        }
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
                        Some("class_money_list") if v02 => InputType::ClassMoneyList,
                        Some("class_money_list") => {
                            return Err(RuleError::at(
                                &format!("inputs.{name}"),
                                "`class_money_list` requires schema_version rule-0.2",
                            ))
                        }
                        _ => {
                            return Err(RuleError::at(
                                &format!("inputs.{name}"),
                                "type must be bool|int|money_krw|date|string (rule-0.2 also class_money_list)",
                            ))
                        }
                    };
                    inputs.insert(name.clone(), ty);
                }
            }
            _ => return Err(RuleError::at("inputs", "must be an object of name -> type")),
        }
        let scope = Scope {
            inputs: &inputs,
            v02,
        };
        let eligibility = parse_expr(
            obj.get("eligibility")
                .ok_or_else(|| RuleError::at("eligibility", "missing"))?,
            &scope,
            "eligibility",
            Ty::Bool,
        )?;
        let amount = parse_expr(
            obj.get("amount")
                .ok_or_else(|| RuleError::at("amount", "missing"))?,
            &scope,
            "amount",
            Ty::Money,
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
            contract_effect,
            source: v.clone(),
        })
    }

    pub fn rule_id(&self) -> &str {
        &self.rule_id
    }

    pub fn rule_version(&self) -> &str {
        &self.rule_version
    }

    pub fn release_id(&self) -> Option<&str> {
        self.release_id.as_deref()
    }

    /// SHA-256 of the canonical rule content (excluding `release_id`).
    pub fn content_hash(&self) -> &str {
        &self.content_hash
    }

    pub fn schema_version(&self) -> &str {
        &self.schema_version
    }

    pub fn publication_state(&self) -> &str {
        &self.publication_state
    }

    pub fn evidence_refs(&self) -> &[String] {
        &self.evidence_refs
    }

    /// What the rule does to the contract when it fires (rule-0.2; `None` for rule-0.1).
    pub fn contract_effect(&self) -> ContractEffect {
        self.contract_effect
    }

    pub fn input_types(&self) -> &BTreeMap<String, InputType> {
        &self.inputs
    }

    /// The JSON this rule was loaded from. To derive a changed rule, clone and edit
    /// this value and pass it to [`Rule::from_json`], which validates and re-hashes.
    pub fn source_json(&self) -> &J {
        &self.source
    }
}

/// Canonical JSON tree for hashing. Objects are `BTreeMap`s, so keys are emitted in
/// byte-wise order no matter how `serde_json::Map` is configured (its `preserve_order`
/// feature, enabled by any crate in the build graph, would otherwise make the hash
/// depend on key order in the file).
#[derive(serde::Serialize)]
#[serde(untagged)]
enum Canon {
    Null,
    Bool(bool),
    Number(serde_json::Number),
    String(String),
    Array(Vec<Canon>),
    Object(BTreeMap<String, Canon>),
}

fn canonicalize(v: &J) -> Canon {
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

/// Compact JSON with recursively sorted keys, excluding the top-level `release_id`
/// so re-releasing identical content keeps the same hash.
fn canonical_bytes(v: &J) -> Vec<u8> {
    let mut canonical = canonicalize(v);
    if let Canon::Object(o) = &mut canonical {
        o.remove("release_id");
    }
    serde_json::to_vec(&canonical).expect("a canonical JSON tree always serializes")
}

/// SHA-256 (lowercase hex) over [`canonical_bytes`].
fn content_hash(v: &J) -> String {
    Sha256::digest(canonical_bytes(v))
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// Declared inputs plus the schema generation, so rule-0.2 operators can be refused in rule-0.1.
struct Scope<'a> {
    inputs: &'a BTreeMap<String, InputType>,
    v02: bool,
}

impl Scope<'_> {
    fn get(&self, name: &str) -> Option<&InputType> {
        self.inputs.get(name)
    }
}

/// Parses the `{rounding, unit}` parameter object shared by the rounding operators.
fn rounding_params(params: &J, p: &str) -> Result<(Rounding, i64), RuleError> {
    let params = params
        .as_object()
        .ok_or_else(|| RuleError::at(p, "last argument must be {rounding, unit}"))?;
    let rounding = match params.get("rounding").and_then(J::as_str) {
        Some("floor") => Rounding::Floor,
        Some("ceil") => Rounding::Ceil,
        Some("half_up") => Rounding::HalfUp,
        Some("half_even") => Rounding::HalfEven,
        Some("unspecified") => Rounding::Unspecified,
        _ => {
            return Err(RuleError::at(
                p,
                "rounding is required: floor|ceil|half_up|half_even|unspecified",
            ))
        }
    };
    let unit = match params.get("unit").and_then(J::as_i64) {
        Some(u @ (1 | 10 | 100 | 1000)) => u,
        _ => return Err(RuleError::at(p, "unit is required: 1|10|100|1000")),
    };
    if params.len() != 2 {
        return Err(RuleError::at(p, "only rounding and unit are allowed"));
    }
    Ok((rounding, unit))
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

/// Parses `v` and requires it to have static type `want`, so a type mismatch is a load error
/// (invariant I5) instead of an evaluation error on whichever input happens to reach it.
fn parse_expr(v: &J, inputs: &Scope<'_>, path: &str, want: Ty) -> Result<Expr, RuleError> {
    let (e, got) = parse_typed(v, inputs, path)?;
    if got != want {
        return Err(RuleError::at(
            path,
            format!("expected {}, found {}", want.name(), got.name()),
        ));
    }
    Ok(e)
}

fn parse_typed(v: &J, inputs: &Scope<'_>, path: &str) -> Result<(Expr, Ty), RuleError> {
    match v {
        J::Bool(b) => Ok((Expr::Lit(Value::Bool(*b)), Ty::Bool)),
        J::Number(n) => match n.as_i64() {
            Some(i) => Ok((Expr::Lit(Value::Int(i)), Ty::Int)),
            None => Err(RuleError::at(
                path,
                "floating-point numbers are not allowed; use a decimal string for rates",
            )),
        },
        J::String(s) => {
            if let Some(t) = inputs.get(s) {
                Ok((Expr::Input(s.clone()), Ty::from(*t)))
            } else if let Some(r) = parse_rate(s) {
                Ok((Expr::Lit(r), Ty::Rate))
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
                let cond = parse_expr(&map["if"], inputs, &format!("{path}.if"), Ty::Bool)?;
                let (then, ty) = parse_typed(&map["then"], inputs, &format!("{path}.then"))?;
                let els = parse_expr(&map["else"], inputs, &format!("{path}.else"), ty)?;
                return Ok((Expr::If(Box::new(cond), Box::new(then), Box::new(els)), ty));
            }
            if map.len() != 1 {
                return Err(RuleError::at(
                    path,
                    "an operator object must have exactly one key",
                ));
            }
            let (op, a) = map.iter().next().expect("len checked");
            let p = format!("{path}.{op}");
            // Every argument of an n-ary operator must have type `want`.
            let list = |a: &J, min: usize, p: &str, want: Ty| -> Result<Vec<Expr>, RuleError> {
                let items = args(a, min, 64, p)?;
                items
                    .iter()
                    .enumerate()
                    .map(|(i, x)| parse_expr(x, inputs, &format!("{p}[{i}]"), want))
                    .collect()
            };
            let two = |a: &J, p: &str, want: Ty| -> Result<(Box<Expr>, Box<Expr>), RuleError> {
                let items = args(a, 2, 2, p)?;
                Ok((
                    Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"), want)?),
                    Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"), want)?),
                ))
            };
            let typed = match op.as_str() {
                "all" => (Expr::All(list(a, 1, &p, Ty::Bool)?), Ty::Bool),
                "any" => (Expr::Any(list(a, 1, &p, Ty::Bool)?), Ty::Bool),
                "not" => (Expr::Not(Box::new(parse_expr(a, inputs, &p, Ty::Bool)?)), Ty::Bool),
                "eq" | "ne" | "lt" | "lte" | "gt" | "gte" => {
                    let items = args(a, 2, 2, &p)?;
                    let (l, lt) = parse_typed(&items[0], inputs, &format!("{p}[0]"))?;
                    let (r, rt) = parse_typed(&items[1], inputs, &format!("{p}[1]"))?;
                    if lt != rt {
                        return Err(RuleError::at(
                            &p,
                            format!("cannot compare {} with {}", lt.name(), rt.name()),
                        ));
                    }
                    if lt == Ty::List {
                        return Err(RuleError::at(&p, "lists cannot be compared"));
                    }
                    if matches!(lt, Ty::Bool | Ty::Str) && !matches!(op.as_str(), "eq" | "ne") {
                        return Err(RuleError::at(
                            &p,
                            format!("ordering comparison is not defined for {}", lt.name()),
                        ));
                    }
                    let (l, r) = (Box::new(l), Box::new(r));
                    let cmp = match op.as_str() {
                        "eq" => CmpOp::Eq,
                        "ne" => CmpOp::Ne,
                        "lt" => CmpOp::Lt,
                        "lte" => CmpOp::Lte,
                        "gt" => CmpOp::Gt,
                        _ => CmpOp::Gte,
                    };
                    (Expr::Cmp(cmp, l, r), Ty::Bool)
                }
                "input" => match a.as_str().and_then(|name| inputs.get(name).map(|t| (name, *t))) {
                    Some((name, t)) => (Expr::Input(name.to_string()), Ty::from(t)),
                    None => return Err(RuleError::at(&p, "must name a declared input")),
                },
                "rate" => a
                    .as_str()
                    .and_then(parse_rate)
                    .map(|r| (Expr::Lit(r), Ty::Rate))
                    .ok_or_else(|| RuleError::at(&p, "must be a non-negative decimal string"))?,
                "krw" => match a.as_i64() {
                    Some(n) if n >= 0 => (Expr::Lit(Value::Money(n)), Ty::Money),
                    _ => return Err(RuleError::at(&p, "must be a non-negative integer")),
                },
                "date" => a
                    .as_str()
                    .and_then(crate::date::parse_date)
                    .map(|d| (Expr::Lit(Value::Date(d)), Ty::Date))
                    .ok_or_else(|| RuleError::at(&p, "must be a valid YYYY-MM-DD date"))?,
                "multiply" => return Err(RuleError::at(&p, "`multiply` is not allowed; use `multiply_rate` with explicit rounding and unit")),
                "multiply_rate" => {
                    let items = args(a, 3, 3, &p)?;
                    let (rounding, unit) = rounding_params(&items[2], &p)?;
                    let money = Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"), Ty::Money)?);
                    let rate = Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"), Ty::Rate)?);
                    (Expr::MultiplyRate { money, rate, rounding, unit }, Ty::Money)
                }
                "add" => (Expr::Add(list(a, 2, &p, Ty::Money)?), Ty::Money),
                "min" => (Expr::Min(list(a, 2, &p, Ty::Money)?), Ty::Money),
                "max" => (Expr::Max(list(a, 2, &p, Ty::Money)?), Ty::Money),
                "apply_cap" => {
                    let (m, c) = two(a, &p, Ty::Money)?;
                    (Expr::ApplyCap(m, c), Ty::Money)
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
                    let (a, b) = (
                        Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"), Ty::Date)?),
                        Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"), Ty::Date)?),
                    );
                    (Expr::DaysBetween { a, b, inclusive_start: s, inclusive_end: e }, Ty::Int)
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
                    // Range check instead of `abs()`: `i64::MIN.abs()` overflows.
                    if !(-limit..=limit).contains(&value) {
                        return Err(RuleError::at(&p, format!("|value| must be <= {limit} for this unit")));
                    }
                    if unit != DurUnit::Day && params.get("month_end").and_then(J::as_str) != Some("clamp") {
                        return Err(RuleError::at(&p, "month/year arithmetic requires month_end=\"clamp\" (never assume 365 days per year)"));
                    }
                    // Exact key sets, like `multiply_rate`: day => {value, unit}; month/year => {value, unit, month_end}.
                    let (allowed, expected_len) = if unit == DurUnit::Day { ("value and unit", 2) } else { ("value, unit and month_end", 3) };
                    if params.len() != expected_len {
                        let hint = if unit == DurUnit::Day && params.contains_key("month_end") { " (`month_end` applies only to calendar_month|calendar_year)" } else { "" };
                        return Err(RuleError::at(&p, format!("only {allowed} are allowed for this unit{hint}")));
                    }
                    let date = Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"), Ty::Date)?);
                    (Expr::DateAdd { date, value, unit }, Ty::Date)
                }
                "multiply_count" | "subtract_floor0" | "pro_rata" | "divide_count" | "anniversary_band" | "max_over" if !inputs.v02 => {
                    return Err(RuleError::at(&p, format!("operator `{op}` requires schema_version rule-0.2")))
                }
                "multiply_count" => {
                    let items = args(a, 2, 2, &p)?;
                    let money = Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"), Ty::Money)?);
                    let count = Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"), Ty::Int)?);
                    (Expr::MultiplyCount(money, count), Ty::Money)
                }
                "subtract_floor0" => {
                    let (x, y) = two(a, &p, Ty::Money)?;
                    (Expr::SubtractFloor0(x, y), Ty::Money)
                }
                "pro_rata" => {
                    let items = args(a, 4, 4, &p)?;
                    let (rounding, unit) = rounding_params(&items[3], &p)?;
                    let money = Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"), Ty::Money)?);
                    // part and whole are both counts (int) or both amounts (money).
                    let (part, pt) = parse_typed(&items[1], inputs, &format!("{p}[1]"))?;
                    let (whole, wt) = parse_typed(&items[2], inputs, &format!("{p}[2]"))?;
                    if pt != wt || !matches!(pt, Ty::Int | Ty::Money) {
                        return Err(RuleError::at(&p, format!("part and whole must both be int or both be money, found {} and {}", pt.name(), wt.name())));
                    }
                    (Expr::ProRata { money, part: Box::new(part), whole: Box::new(whole), rounding, unit }, Ty::Money)
                }
                "divide_count" => {
                    let items = args(a, 3, 3, &p)?;
                    let (rounding, unit) = rounding_params(&items[2], &p)?;
                    let money = Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"), Ty::Money)?);
                    let count = Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"), Ty::Int)?);
                    (Expr::DivideCount { money, count, rounding, unit }, Ty::Money)
                }
                "anniversary_band" => {
                    let items = args(a, 4, 4, &p)?;
                    let from = Box::new(parse_expr(&items[0], inputs, &format!("{p}[0]"), Ty::Date)?);
                    let at = Box::new(parse_expr(&items[1], inputs, &format!("{p}[1]"), Ty::Date)?);
                    let table = items[2].as_array().ok_or_else(|| RuleError::at(&format!("{p}[2]"), "must be an array of [years, rate] pairs"))?;
                    if table.is_empty() || table.len() > 64 {
                        return Err(RuleError::at(&format!("{p}[2]"), "needs 1..=64 bands"));
                    }
                    let mut bands: Vec<(i64, Value)> = Vec::new();
                    for (i, row) in table.iter().enumerate() {
                        let bp = format!("{p}[2][{i}]");
                        let pair = row.as_array().filter(|r| r.len() == 2).ok_or_else(|| RuleError::at(&bp, "must be [years, rate]"))?;
                        let years = pair[0].as_i64().filter(|y| (0..=300).contains(y)).ok_or_else(|| RuleError::at(&bp, "years must be an integer in 0..=300"))?;
                        let rate = pair[1].as_str().and_then(parse_rate).ok_or_else(|| RuleError::at(&bp, "value must be a decimal rate string"))?;
                        match bands.last() {
                            None if years != 0 => return Err(RuleError::at(&bp, "the first band must start at 0 years")),
                            Some((prev, _)) if years <= *prev => return Err(RuleError::at(&bp, "band start years must be strictly ascending")),
                            _ => {}
                        }
                        bands.push((years, rate));
                    }
                    let bparams = items[3].as_object().ok_or_else(|| RuleError::at(&format!("{p}[3]"), "last argument must be {boundary}"))?;
                    let boundary = match bparams.get("boundary").and_then(J::as_str) {
                        Some("lower_inclusive") => Boundary::Lower,
                        Some("upper_inclusive") => Boundary::Upper,
                        _ => return Err(RuleError::at(&format!("{p}[3]"), "boundary is required: lower_inclusive|upper_inclusive")),
                    };
                    if bparams.len() != 1 {
                        return Err(RuleError::at(&format!("{p}[3]"), "only boundary is allowed"));
                    }
                    (Expr::AnniversaryBand { from, at, bands, boundary }, Ty::Rate)
                }
                "max_over" => match a.as_str().and_then(|n| inputs.get(n).map(|t| (n, *t))) {
                    Some((name, InputType::ClassMoneyList)) => (Expr::MaxOver(name.to_string()), Ty::Money),
                    _ => return Err(RuleError::at(&p, "must name a declared class_money_list input")),
                },
                other => return Err(RuleError::at(path, format!("operator `{other}` is not in the allow-list"))),
            };
            Ok(typed)
        }
    }
}

#[cfg(test)]
mod canonical_tests {
    use super::*;

    #[test]
    fn canonical_bytes_sort_keys_recursively_and_drop_release_id() {
        let v: J = serde_json::from_str(
            r#"{"z":1,"release_id":"r","a":{"y":[{"d":null,"c":true}],"b":"x"},"m":{"release_id":"kept"}}"#,
        )
        .unwrap();
        assert_eq!(
            String::from_utf8(canonical_bytes(&v)).unwrap(),
            r#"{"a":{"b":"x","y":[{"c":true,"d":null}]},"m":{"release_id":"kept"},"z":1}"#
        );
    }

    #[test]
    fn content_hash_matches_independent_sha256_of_the_canonical_text() {
        // sha256 of the exact bytes `{"a":1,"b":2}` (computed outside this crate)
        let v: J = serde_json::from_str(r#"{"b":2,"a":1,"release_id":"x"}"#).unwrap();
        assert_eq!(
            content_hash(&v),
            "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
        );
    }
}
