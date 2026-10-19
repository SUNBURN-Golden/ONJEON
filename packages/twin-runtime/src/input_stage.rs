//! Input stage (C-26 `judge`, ADR-0014 §4): fills the inputs a rule declares from the
//! request's facts and from judgements computed outside the DSL.
//!
//! A rule names the inputs it cannot compute itself in `inputs_from_outside_dsl`
//! (C-08). The declaration is part of the **rule artifact** — the rule file the release
//! pins — so [`load_rule_artifact`] lifts it off the artifact's JSON before the DSL
//! loader sees the body (rule-0.1 knows only the DSL keys). A request can neither add
//! nor omit judged inputs, and only declared ones are judged here: `judged_by =
//! "ontology"` inputs go through code membership against the category the linked
//! coverage uses (`uses_definition`), with the evidence trail of every assertion the
//! answer rests on. `time_stage` judgements run through [`judge_time`]; `contract_twin`
//! and `parameter_table` are not part of this skeleton — declaring one fails explicitly
//! instead of filling a value from nothing (I1, O12).
//!
//! Inputs that are not judged at all are copied from the request facts; a missing fact
//! stays `null` and the engine reports it as missing — the stage never invents a value.

use crate::snapshot::Snapshot;
use onjeon_ontology::{membership, Linked, OntologyError};
use onjeon_rules_engine::Rule;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::fmt;

/// Who judges an outside-DSL input (C-08 `judged_by`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JudgedBy {
    /// Code membership against a disease category (`membership`, C-26 `judge`).
    Ontology,
    /// Period boundary judgement from an anchor and a source-unit duration
    /// (`judge_time`, C-26). Assumptions travel with the judgement.
    TimeStage,
    /// Contract-twin state such as cumulative use (S0: declared, not implemented).
    ContractTwin,
    /// Disclosed value lookup (S0: declared, not implemented).
    ParameterTable,
}

impl JudgedBy {
    pub fn as_str(self) -> &'static str {
        match self {
            JudgedBy::Ontology => "ontology",
            JudgedBy::TimeStage => "time_stage",
            JudgedBy::ContractTwin => "contract_twin",
            JudgedBy::ParameterTable => "parameter_table",
        }
    }

    fn parse(s: &str) -> Option<JudgedBy> {
        Some(match s {
            "ontology" => JudgedBy::Ontology,
            "time_stage" => JudgedBy::TimeStage,
            "contract_twin" => JudgedBy::ContractTwin,
            "parameter_table" => JudgedBy::ParameterTable,
            _ => return None,
        })
    }
}

impl Serialize for JudgedBy {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(self.as_str())
    }
}

impl<'de> Deserialize<'de> for JudgedBy {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let s = String::deserialize(d)?;
        JudgedBy::parse(&s)
            .ok_or_else(|| serde::de::Error::custom(format!("unknown judged_by {s}")))
    }
}

/// One entry of a rule artifact's `inputs_from_outside_dsl` (C-08): which engine input
/// is judged outside the DSL, by whom, and which facts feed the judgement. Unknown keys
/// are rejected — a stale or misspelt key must fail loudly, not be silently ignored.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OutsideInput {
    /// The engine input name (must appear in the rule's `inputs`).
    pub name: String,
    pub judged_by: JudgedBy,
    /// C-08 fixes `evidence_required` to `true`: a judgement must carry its evidence.
    /// `Some(false)` is a bad declaration.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub evidence_required: Option<bool>,
    /// `judged_by = "ontology"`: the fact key holding the diagnosis code (e.g. `dx_code`).
    /// The category comes from the linked coverage (`uses_definition`), never the request.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub code_fact: Option<String>,
    /// `judged_by = "ontology"`: the fact key holding the date to judge as of.
    /// Absent means no validity filter on membership claims; present but not a date is
    /// an error — a bad date must never silently judge a different day.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub as_of_fact: Option<String>,
    /// `judged_by = "time_stage"`: the fact key holding the anchor date the period
    /// starts from (e.g. `contract_date`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub anchor_fact: Option<String>,
    /// `judged_by = "time_stage"`: the period length, in the source's own unit.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub duration: Option<TimeDuration>,
    /// `judged_by = "time_stage"`: whether the source counts the anchor day as day one
    /// (기산일 포함 여부). `None` means the source does not say — 기산일 미산입 is then
    /// assumed and recorded in `assumptions` (ADR-0014 §2).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub anchor_day_counted: Option<bool>,
    /// `judged_by = "time_stage"`: fact keys of the dates to classify as inside the
    /// period (e.g. `["diagnosis_date"]`). With several dates the input is their `and`.
    #[serde(default)]
    pub dates_facts: Vec<String>,
}

/// A period length in the unit the source stated (ADR-0014 §2: units are never
/// converted between each other).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct TimeDuration {
    pub value: i64,
    pub unit: DurUnit,
}

/// Duration units the contract knows; they stay as the source wrote them.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DurUnit {
    Day,
    CalendarMonth,
    CalendarYear,
}

impl DurUnit {
    pub fn as_str(self) -> &'static str {
        match self {
            DurUnit::Day => "day",
            DurUnit::CalendarMonth => "calendar_month",
            DurUnit::CalendarYear => "calendar_year",
        }
    }
}

impl Serialize for DurUnit {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(self.as_str())
    }
}

impl<'de> Deserialize<'de> for DurUnit {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let s = String::deserialize(d)?;
        Ok(match s.as_str() {
            "day" => DurUnit::Day,
            "calendar_month" => DurUnit::CalendarMonth,
            "calendar_year" => DurUnit::CalendarYear,
            _ => {
                return Err(serde::de::Error::custom(format!(
                    "unknown duration unit {s}"
                )))
            }
        })
    }
}

/// The answer of [`judge_time`]: where the period ends, and for each date handed in
/// whether it falls inside the period.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct TimeJudgement {
    /// The period end date (`YYYY-MM-DD`). `None` when the boundary left the supported
    /// range — never a guessed date.
    pub value: Option<String>,
    /// Per date in `dates`: inside `[first_day, value]`?
    pub within: Vec<onjeon_contracts::Tri>,
    /// Conventions applied that the source did not state (e.g. an assumed 기산일
    /// handling, a month-end clamp). Empty when everything came from the source.
    pub assumptions: Vec<String>,
}

/// A judgement the input stage produced for one outside input — the wire `InputJudgement`
/// (02 §2.4) plus the code sets consulted and the date the answer is for (C-26 `judge`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct StageJudgement {
    pub input_name: String,
    /// `"true" | "false" | "unknown"`.
    pub value: onjeon_contracts::Tri,
    pub judged_by: JudgedBy,
    /// The assertions the answer rests on, in the order they were read.
    pub evidence_assertion_ids: Vec<String>,
    /// CodeSet nodes consulted (code system and its edition live on the node).
    pub code_system_refs: Vec<String>,
    pub judged_as_of: Option<String>,
    /// The period end a `time_stage` judgement computed (`YYYY-MM-DD`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub boundary: Option<String>,
    /// Conventions the judgement applied that the source did not state.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub assumptions: Vec<String>,
}

/// The inputs handed to the engine and the judgements that produced them.
#[derive(Debug, Clone, PartialEq)]
pub struct Filled {
    /// Every key of `rule.input_types()`, each with a value (or `null` = unknown).
    pub inputs: Map<String, Value>,
    pub judgements: Vec<StageJudgement>,
}

/// What [`fill`] needs beyond the declaration and the facts: the release snapshot and
/// the linked chain (its `category` feeds ontology judgements).
pub struct FillRequest<'a> {
    pub snapshot: &'a Snapshot,
    pub linked: &'a Linked,
    pub rule: &'a Rule,
    /// Flat request facts: assumptions merged with dates, codes and the contract date.
    pub facts: &'a Map<String, Value>,
}

#[derive(Debug)]
pub enum FillError {
    /// The declaration names an input the rule does not declare, or omits what the
    /// judgement needs (`code_fact` for an ontology judgement).
    BadDeclaration(String),
    /// The judgement kind is declared but has no implementation at this stage.
    UnsupportedJudgedBy { input: String, judged_by: String },
    /// An ontology judgement was requested but the chain supplies no category.
    NoCategory { input: String },
    /// The underlying membership judgement failed (e.g. a malformed code fact).
    Ontology(OntologyError),
    /// A fact a judgement needs is absent, not a date, or out of range.
    BadFact(String),
}

impl fmt::Display for FillError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            FillError::BadDeclaration(m) => write!(f, "bad outside-input declaration: {m}"),
            FillError::UnsupportedJudgedBy { input, judged_by } => {
                write!(f, "input {input}: judged_by {judged_by} is not implemented")
            }
            FillError::NoCategory { input } => {
                write!(f, "input {input}: no disease category on the linked chain")
            }
            FillError::Ontology(e) => write!(f, "ontology judgement failed: {e}"),
            FillError::BadFact(m) => write!(f, "bad fact: {m}"),
        }
    }
}

impl std::error::Error for FillError {}

/// Loads a rule artifact: the DSL body for the engine plus the C-08
/// `inputs_from_outside_dsl` declaration for the input stage. The declaration is part
/// of the rule file the release pins; the engine's loader knows only the DSL keys, so
/// the key is lifted off the JSON before `Rule::from_json` sees the body. A file
/// without the key declares no outside inputs.
pub fn load_rule_artifact(bytes: &[u8]) -> Result<(Rule, Vec<OutsideInput>), String> {
    let mut v: Value = serde_json::from_slice(bytes).map_err(|e| format!("invalid JSON: {e}"))?;
    let decl = v
        .as_object_mut()
        .and_then(|o| o.remove("inputs_from_outside_dsl"));
    let outside: Vec<OutsideInput> = match decl {
        None | Some(Value::Null) => Vec::new(),
        Some(d) => {
            serde_json::from_value(d).map_err(|e| format!("inputs_from_outside_dsl: {e}"))?
        }
    };
    let rule = Rule::from_json(&v).map_err(|e| e.to_string())?;
    Ok((rule, outside))
}

/// Fills `rule`'s declared inputs for [`FillRequest`], honouring `outside`
/// (the rule artifact's `inputs_from_outside_dsl`) and producing a judgement per
/// judged input.
pub fn fill(outside: &[OutsideInput], req: &FillRequest<'_>) -> Result<Filled, FillError> {
    let mut inputs = Map::new();
    let mut judgements = Vec::new();
    for name in req.rule.input_types().keys() {
        match outside.iter().find(|o| o.name == *name) {
            None => {
                inputs.insert(
                    name.clone(),
                    req.facts.get(name).cloned().unwrap_or(Value::Null),
                );
            }
            Some(o) => {
                if o.evidence_required == Some(false) {
                    return Err(FillError::BadDeclaration(format!(
                        "{}: evidence_required is always true (C-08)",
                        o.name
                    )));
                }
                let (v, j) = judge(o, req)?;
                inputs.insert(name.clone(), v);
                judgements.push(j);
            }
        }
    }
    for o in outside {
        if !req.rule.input_types().contains_key(&o.name) {
            return Err(FillError::BadDeclaration(format!(
                "{}: declared outside but not an input of rule {}",
                o.name,
                req.rule.rule_id()
            )));
        }
    }
    Ok(Filled { inputs, judgements })
}

fn judge(o: &OutsideInput, req: &FillRequest<'_>) -> Result<(Value, StageJudgement), FillError> {
    match o.judged_by {
        JudgedBy::Ontology => {
            // the category is the linked coverage's `uses_definition`, never an override
            let cat = req
                .linked
                .category
                .clone()
                .ok_or_else(|| FillError::NoCategory {
                    input: o.name.clone(),
                })?;
            let code_key = o.code_fact.as_deref().ok_or_else(|| {
                FillError::BadDeclaration(format!("{}: ontology judgement needs code_fact", o.name))
            })?;
            let code = req.facts.get(code_key).and_then(Value::as_str);
            let Some(code) = code else {
                // No code fact: nothing to judge — the input stays unknown and the engine
                // decides what that means (undetermined, never a guessed boolean).
                return Ok((
                    Value::Null,
                    StageJudgement {
                        input_name: o.name.clone(),
                        value: onjeon_contracts::Tri::Unknown,
                        judged_by: JudgedBy::Ontology,
                        evidence_assertion_ids: Vec::new(),
                        code_system_refs: Vec::new(),
                        judged_as_of: None,
                        boundary: None,
                        assumptions: Vec::new(),
                    },
                ));
            };
            let as_of = match o.as_of_fact.as_deref() {
                None => None,
                Some(k) => match req.facts.get(k) {
                    // the date the judgement is for is unknown too — same answer, and the
                    // judgement says so instead of judging with no validity filter
                    None | Some(Value::Null) => {
                        return Ok((
                            Value::Null,
                            StageJudgement {
                                input_name: o.name.clone(),
                                value: onjeon_contracts::Tri::Unknown,
                                judged_by: JudgedBy::Ontology,
                                evidence_assertion_ids: Vec::new(),
                                code_system_refs: Vec::new(),
                                judged_as_of: None,
                                boundary: None,
                                assumptions: Vec::new(),
                            },
                        ))
                    }
                    Some(v) => {
                        let s = v
                            .as_str()
                            .ok_or_else(|| FillError::BadFact(format!("{k}: not a date fact")))?;
                        if onjeon_rules_engine::date::parse_date(s).is_none() {
                            return Err(FillError::BadFact(format!("{k}: not a date: {s}")));
                        }
                        Some(s.to_string())
                    }
                },
            };
            let j = membership(req.snapshot.view(), &cat, code, as_of.as_deref())
                .map_err(FillError::Ontology)?;
            let v = match j.value {
                onjeon_contracts::Tri::True => Value::Bool(true),
                onjeon_contracts::Tri::False => Value::Bool(false),
                onjeon_contracts::Tri::Unknown => Value::Null,
            };
            Ok((
                v,
                StageJudgement {
                    input_name: o.name.clone(),
                    value: j.value,
                    judged_by: JudgedBy::Ontology,
                    evidence_assertion_ids: j
                        .evidence_assertion_ids()
                        .iter()
                        .map(|s| s.to_string())
                        .collect(),
                    code_system_refs: j.code_system_refs,
                    judged_as_of: j.judged_as_of,
                    boundary: None,
                    assumptions: Vec::new(),
                },
            ))
        }
        JudgedBy::TimeStage => {
            let bad = |m: String| FillError::BadDeclaration(format!("{}: {m}", o.name));
            let anchor_key = o
                .anchor_fact
                .as_deref()
                .ok_or_else(|| bad("time_stage judgement needs anchor_fact".to_string()))?;
            let duration = o
                .duration
                .ok_or_else(|| bad("time_stage judgement needs duration".to_string()))?;
            if o.dates_facts.is_empty() {
                return Err(bad("time_stage judgement needs dates_facts".to_string()));
            }
            let anchor = req
                .facts
                .get(anchor_key)
                .and_then(Value::as_str)
                .ok_or_else(|| FillError::BadFact(format!("{anchor_key}: not a date fact")))?;
            let mut dates = Vec::new();
            for k in &o.dates_facts {
                let d = req
                    .facts
                    .get(k)
                    .and_then(Value::as_str)
                    .ok_or_else(|| FillError::BadFact(format!("{k}: not a date fact")))?;
                dates.push(d);
            }
            let tj = judge_time(anchor, &duration, o.anchor_day_counted, &dates)
                .map_err(|m| FillError::BadFact(format!("{}: {m}", o.name)))?;
            let within =
                tj.within
                    .iter()
                    .copied()
                    .fold(onjeon_contracts::Tri::True, |acc, w| match (acc, w) {
                        (onjeon_contracts::Tri::False, _) | (_, onjeon_contracts::Tri::False) => {
                            onjeon_contracts::Tri::False
                        }
                        (onjeon_contracts::Tri::True, onjeon_contracts::Tri::True) => {
                            onjeon_contracts::Tri::True
                        }
                        _ => onjeon_contracts::Tri::Unknown,
                    });
            let v = match within {
                onjeon_contracts::Tri::True => Value::Bool(true),
                onjeon_contracts::Tri::False => Value::Bool(false),
                onjeon_contracts::Tri::Unknown => Value::Null,
            };
            Ok((
                v,
                StageJudgement {
                    input_name: o.name.clone(),
                    value: within,
                    judged_by: JudgedBy::TimeStage,
                    evidence_assertion_ids: Vec::new(),
                    code_system_refs: Vec::new(),
                    judged_as_of: None,
                    boundary: tj.value,
                    assumptions: tj.assumptions,
                },
            ))
        }
        other => Err(FillError::UnsupportedJudgedBy {
            input: o.name.clone(),
            judged_by: other.as_str().to_string(),
        }),
    }
}

/// Period boundary judgement (C-26 `judge_time`): `anchor` is a `YYYY-MM-DD` fact,
/// `duration` the period length in the source's own unit. `anchor_day_counted` is the
/// source's 기산일 rule: `Some(true)` the anchor day is day one, `Some(false)` it is not,
/// `None` the source does not say — 기산일 미산입 is then assumed and recorded in
/// `assumptions` (ADR-0014 §2). For each date in `dates`, `within` says whether it falls
/// in `[first_day, end]`; the period is always exactly `duration` long.
///
/// Returns `Err` on a malformed anchor/date or a non-positive duration; a boundary that
/// leaves the supported year range makes `value`/`within` unknown, never a wrong date.
pub fn judge_time(
    anchor: &str,
    duration: &TimeDuration,
    anchor_day_counted: Option<bool>,
    dates: &[&str],
) -> Result<TimeJudgement, String> {
    use onjeon_rules_engine::date as d;
    let a = d::parse_date(anchor).ok_or_else(|| format!("anchor is not a date: {anchor}"))?;
    if duration.value <= 0 {
        return Err(format!("duration must be positive: {}", duration.value));
    }
    let counted = anchor_day_counted.unwrap_or(false);
    let mut assumptions = Vec::new();
    if anchor_day_counted.is_none() {
        assumptions.push(format!(
            "기산일 미산입으로 계산(원문 출처 없음, 엔진 가정): {} {} {}",
            anchor,
            duration.value,
            duration.unit.as_str()
        ));
    }
    let advanced = match duration.unit {
        DurUnit::Day => d::add_days(a, duration.value),
        DurUnit::CalendarMonth => d::add_months_clamped(a, duration.value),
        DurUnit::CalendarYear => d::add_months_clamped(
            a,
            duration
                .value
                .checked_mul(12)
                .ok_or_else(|| "duration years overflow".to_string())?,
        ),
    };
    let Some(advanced) = advanced else {
        return Ok(TimeJudgement {
            value: None,
            within: vec![onjeon_contracts::Tri::Unknown; dates.len()],
            assumptions,
        });
    };
    if matches!(
        duration.unit,
        DurUnit::CalendarMonth | DurUnit::CalendarYear
    ) {
        // a clamp happened iff the anchor's day does not exist in the target month
        let (_, _, ad) = d::civil_from_days(a);
        let (ey, em, _) = d::civil_from_days(advanced);
        if ad > d::days_in_month(ey, em) {
            assumptions.push(format!(
                "월말이 없는 달은 그 달의 마지막 날로 맞춤(엔진 관례): {anchor} + {} {}",
                duration.value,
                duration.unit.as_str()
            ));
        }
    }
    // counted: [anchor, advanced - 1]; not counted: [anchor + 1, advanced]
    let end = if counted {
        match d::add_days(advanced, -1) {
            Some(e) => e,
            None => {
                return Ok(TimeJudgement {
                    value: None,
                    within: vec![onjeon_contracts::Tri::Unknown; dates.len()],
                    assumptions,
                })
            }
        }
    } else {
        advanced
    };
    let first = if counted { a } else { a + 1 };
    let mut within = Vec::new();
    for date in dates {
        let dd = d::parse_date(date).ok_or_else(|| format!("date is not a date: {date}"))?;
        within.push(if first <= dd && dd <= end {
            onjeon_contracts::Tri::True
        } else {
            onjeon_contracts::Tri::False
        });
    }
    Ok(TimeJudgement {
        value: Some(d::format_date(end)),
        within,
        assumptions,
    })
}
