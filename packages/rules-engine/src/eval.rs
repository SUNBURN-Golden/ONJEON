//! Deterministic evaluation with three-valued logic and blocker tracking.
//!
//! Every unknown value carries the set of unknown inputs that caused it
//! (`blockers`). A definite result (for example `false AND unknown`) has no
//! blockers, so `missing_inputs` lists only inputs that actually matter.

use crate::date::{add_months_clamped, parse_date};
use crate::rule::{CmpOp, DurUnit, Expr, InputType, Rounding, Rule};
use crate::tri::Tri;
use crate::value::Value;
use serde::Serialize;
use serde_json::Value as J;
use sha2::{Digest, Sha256};
use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EvalError {
    InputsNotObject,
    UnknownInput(String),
    BadInput {
        name: String,
        expected: &'static str,
    },
    Type {
        path: String,
        message: String,
    },
    Overflow {
        path: String,
    },
    AmountNotMoney {
        found: &'static str,
    },
}

impl fmt::Display for EvalError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            EvalError::InputsNotObject => write!(f, "inputs must be a JSON object"),
            EvalError::UnknownInput(n) => write!(f, "input `{n}` is not declared by the rule"),
            EvalError::BadInput { name, expected } => {
                write!(f, "input `{name}` must be {expected} or null")
            }
            EvalError::Type { path, message } => write!(f, "type error at {path}: {message}"),
            EvalError::Overflow { path } => write!(f, "arithmetic overflow at {path}"),
            EvalError::AmountNotMoney { found } => {
                write!(f, "amount expression must produce money, found {found}")
            }
        }
    }
}

impl std::error::Error for EvalError {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct TraceEntry {
    pub path: String,
    pub op: &'static str,
    pub result: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum AmountOut {
    Exact { krw: i64 },
    Range { min_krw: i64, max_krw: i64 },
    Unknown,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Payout {
    /// The rule says no payment is due. Never produced from unknown inputs.
    NotPayable,
    /// Eligibility is established. The amount may still be unknown or a range.
    Payable { amount: AmountOut },
    /// Eligibility cannot be decided yet; `conditional_amount` is what would be paid if eligible.
    Undetermined { conditional_amount: AmountOut },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EvaluationResult {
    pub rule_id: String,
    pub schema_version: String,
    pub engine_version: &'static str,
    pub eligibility: Tri,
    pub payout: Payout,
    pub missing_inputs: Vec<String>,
    pub trace: Vec<TraceEntry>,
    pub input_snapshot_hash: String,
}

struct Ev {
    v: Value,
    blockers: BTreeSet<String>,
}

impl Ev {
    fn known(v: Value) -> Ev {
        Ev {
            v,
            blockers: BTreeSet::new(),
        }
    }
    fn unknown(blockers: BTreeSet<String>) -> Ev {
        Ev {
            v: Value::Unknown,
            blockers,
        }
    }
}

struct Ctx<'a> {
    inputs: &'a BTreeMap<String, Value>,
    trace: Vec<TraceEntry>,
}

fn type_err(path: &str, message: impl Into<String>) -> EvalError {
    EvalError::Type {
        path: path.to_string(),
        message: message.into(),
    }
}

fn to_tri(ev: &Ev, path: &str) -> Result<Tri, EvalError> {
    match &ev.v {
        Value::Bool(true) => Ok(Tri::True),
        Value::Bool(false) => Ok(Tri::False),
        Value::Unknown => Ok(Tri::Unknown),
        other => Err(type_err(
            path,
            format!("expected a boolean, found {}", other.type_name()),
        )),
    }
}

fn from_tri(t: Tri, blockers: BTreeSet<String>) -> Ev {
    match t {
        Tri::True => Ev::known(Value::Bool(true)),
        Tri::False => Ev::known(Value::Bool(false)),
        Tri::Unknown => Ev::unknown(blockers),
    }
}

fn union_unknown<'a>(items: impl IntoIterator<Item = &'a Ev>) -> BTreeSet<String> {
    let mut s = BTreeSet::new();
    for e in items {
        if e.v.is_unknown() {
            s.extend(e.blockers.iter().cloned());
        }
    }
    s
}

fn compare(a: &Value, b: &Value, path: &str) -> Result<Ordering, EvalError> {
    match (a, b) {
        (Value::Int(x), Value::Int(y)) => Ok(x.cmp(y)),
        (Value::Money(x), Value::Money(y)) => Ok(x.cmp(y)),
        (Value::Date(x), Value::Date(y)) => Ok(x.cmp(y)),
        (Value::Rate { num: n1, den: d1 }, Value::Rate { num: n2, den: d2 }) => {
            Ok((*n1 as i128 * *d2 as i128).cmp(&(*n2 as i128 * *d1 as i128)))
        }
        (Value::Bool(x), Value::Bool(y)) => Ok(x.cmp(y)),
        (Value::Str(x), Value::Str(y)) => Ok(x.cmp(y)),
        _ => Err(type_err(
            path,
            format!("cannot compare {} with {}", a.type_name(), b.type_name()),
        )),
    }
}

fn money_bounds(v: &Value, path: &str) -> Result<(i64, i64), EvalError> {
    match v {
        Value::Money(m) => Ok((*m, *m)),
        Value::MoneyRange { min, max } => Ok((*min, *max)),
        other => Err(type_err(
            path,
            format!("expected money, found {}", other.type_name()),
        )),
    }
}

fn money_value(min: i64, max: i64) -> Value {
    if min == max {
        Value::Money(min)
    } else {
        Value::MoneyRange { min, max }
    }
}

/// money * num/den, rounded to a multiple of `unit` with an explicit rule.
fn multiply_rate(
    money: i64,
    num: i64,
    den: i64,
    rounding: Rounding,
    unit: i64,
    path: &str,
) -> Result<Value, EvalError> {
    if money < 0 || num < 0 || den <= 0 {
        return Err(type_err(path, "money and rate must be non-negative"));
    }
    let n = money as i128 * num as i128;
    let d = den as i128 * unit as i128;
    let floor = n.div_euclid(d);
    let rem = n - floor * d;
    let ceil = if rem > 0 { floor + 1 } else { floor };
    let pick = |q: i128| -> Result<i64, EvalError> {
        i64::try_from(q * unit as i128).map_err(|_| EvalError::Overflow {
            path: path.to_string(),
        })
    };
    match rounding {
        Rounding::Floor => Ok(Value::Money(pick(floor)?)),
        Rounding::Ceil => Ok(Value::Money(pick(ceil)?)),
        Rounding::HalfUp => Ok(Value::Money(pick(if rem * 2 >= d {
            floor + 1
        } else {
            floor
        })?)),
        Rounding::HalfEven => {
            let q = match (rem * 2).cmp(&d) {
                Ordering::Less => floor,
                Ordering::Greater => floor + 1,
                Ordering::Equal => {
                    if floor % 2 == 0 {
                        floor
                    } else {
                        floor + 1
                    }
                }
            };
            Ok(Value::Money(pick(q)?))
        }
        Rounding::Unspecified => Ok(money_value(pick(floor)?, pick(ceil)?)),
    }
}

fn eval(expr: &Expr, path: &str, ctx: &mut Ctx<'_>) -> Result<Ev, EvalError> {
    let out = eval_inner(expr, path, ctx)?;
    ctx.trace.push(TraceEntry {
        path: path.to_string(),
        op: expr.op_name(),
        result: out.v.to_string(),
    });
    Ok(out)
}

fn eval_inner(expr: &Expr, path: &str, ctx: &mut Ctx<'_>) -> Result<Ev, EvalError> {
    match expr {
        Expr::Lit(v) => Ok(Ev::known(v.clone())),
        Expr::Input(name) => {
            let v = ctx.inputs.get(name).cloned().unwrap_or(Value::Unknown);
            if v.is_unknown() {
                Ok(Ev::unknown(BTreeSet::from([name.clone()])))
            } else {
                Ok(Ev::known(v))
            }
        }
        Expr::All(children) | Expr::Any(children) => {
            let is_all = matches!(expr, Expr::All(_));
            let mut evs = Vec::with_capacity(children.len());
            for (i, c) in children.iter().enumerate() {
                evs.push(eval(c, &format!("{path}.{}[{i}]", expr.op_name()), ctx)?);
            }
            let mut acc = if is_all { Tri::True } else { Tri::False };
            for (i, e) in evs.iter().enumerate() {
                let t = to_tri(e, &format!("{path}[{i}]"))?;
                acc = if is_all { acc.and(t) } else { acc.or(t) };
            }
            Ok(from_tri(acc, union_unknown(&evs)))
        }
        Expr::Not(inner) => {
            let e = eval(inner, &format!("{path}.not"), ctx)?;
            let t = !to_tri(&e, path)?;
            Ok(from_tri(t, e.blockers))
        }
        Expr::Cmp(op, l, r) => {
            let a = eval(l, &format!("{path}.{}[0]", expr.op_name()), ctx)?;
            let b = eval(r, &format!("{path}.{}[1]", expr.op_name()), ctx)?;
            if a.v.is_unknown() || b.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&a, &b])));
            }
            let ord = compare(&a.v, &b.v, path)?;
            let ordered = !matches!(
                (&a.v, op),
                (
                    Value::Bool(_) | Value::Str(_),
                    CmpOp::Lt | CmpOp::Lte | CmpOp::Gt | CmpOp::Gte
                )
            );
            if !ordered {
                return Err(type_err(
                    path,
                    "ordering comparison is not defined for bool or string",
                ));
            }
            let res = match op {
                CmpOp::Eq => ord == Ordering::Equal,
                CmpOp::Ne => ord != Ordering::Equal,
                CmpOp::Lt => ord == Ordering::Less,
                CmpOp::Lte => ord != Ordering::Greater,
                CmpOp::Gt => ord == Ordering::Greater,
                CmpOp::Gte => ord != Ordering::Less,
            };
            Ok(Ev::known(Value::Bool(res)))
        }
        Expr::If(c, t, e) => {
            let cond = eval(c, &format!("{path}.if"), ctx)?;
            match to_tri(&cond, path)? {
                Tri::True => eval(t, &format!("{path}.then"), ctx),
                Tri::False => eval(e, &format!("{path}.else"), ctx),
                Tri::Unknown => {
                    let a = eval(t, &format!("{path}.then"), ctx)?;
                    let b = eval(e, &format!("{path}.else"), ctx)?;
                    if !a.v.is_unknown() && a.v == b.v {
                        Ok(a)
                    } else {
                        // The condition is undecided and the branches disagree (or one is
                        // itself unknown). Blockers are the condition's unknown inputs plus
                        // the unknown inputs inside any unknown branch.
                        let mut blockers = cond.blockers;
                        blockers.extend(union_unknown([&a, &b]));
                        Ok(Ev::unknown(blockers))
                    }
                }
            }
        }
        Expr::MultiplyRate {
            money,
            rate,
            rounding,
            unit,
        } => {
            let m = eval(money, &format!("{path}.multiply_rate[0]"), ctx)?;
            let r = eval(rate, &format!("{path}.multiply_rate[1]"), ctx)?;
            if m.v.is_unknown() || r.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&m, &r])));
            }
            match (&m.v, &r.v) {
                (Value::Money(x), Value::Rate { num, den }) => Ok(Ev::known(multiply_rate(
                    *x, *num, *den, *rounding, *unit, path,
                )?)),
                (a, b) => Err(type_err(
                    path,
                    format!(
                        "multiply_rate needs money and rate, found {} and {}",
                        a.type_name(),
                        b.type_name()
                    ),
                )),
            }
        }
        Expr::Add(items) | Expr::Min(items) | Expr::Max(items) => {
            let mut evs = Vec::with_capacity(items.len());
            for (i, c) in items.iter().enumerate() {
                evs.push(eval(c, &format!("{path}.{}[{i}]", expr.op_name()), ctx)?);
            }
            if evs.iter().any(|e| e.v.is_unknown()) {
                return Ok(Ev::unknown(union_unknown(&evs)));
            }
            let mut lo = None::<i64>;
            let mut hi = None::<i64>;
            for e in &evs {
                let (a, b) = money_bounds(&e.v, path)?;
                let ov = || EvalError::Overflow {
                    path: path.to_string(),
                };
                lo = Some(match (lo, expr) {
                    (None, _) => a,
                    (Some(x), Expr::Add(_)) => x.checked_add(a).ok_or_else(ov)?,
                    (Some(x), Expr::Min(_)) => x.min(a),
                    (Some(x), _) => x.max(a),
                });
                hi = Some(match (hi, expr) {
                    (None, _) => b,
                    (Some(x), Expr::Add(_)) => x.checked_add(b).ok_or_else(ov)?,
                    (Some(x), Expr::Min(_)) => x.min(b),
                    (Some(x), _) => x.max(b),
                });
            }
            Ok(Ev::known(money_value(
                lo.expect("at least two items"),
                hi.expect("at least two items"),
            )))
        }
        Expr::ApplyCap(m, c) => {
            let a = eval(m, &format!("{path}.apply_cap[0]"), ctx)?;
            let b = eval(c, &format!("{path}.apply_cap[1]"), ctx)?;
            if a.v.is_unknown() || b.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&a, &b])));
            }
            let (alo, ahi) = money_bounds(&a.v, path)?;
            let (blo, bhi) = money_bounds(&b.v, path)?;
            Ok(Ev::known(money_value(alo.min(blo), ahi.min(bhi))))
        }
        Expr::DaysBetween {
            a,
            b,
            inclusive_start,
            inclusive_end,
        } => {
            let x = eval(a, &format!("{path}.days_between[0]"), ctx)?;
            let y = eval(b, &format!("{path}.days_between[1]"), ctx)?;
            if x.v.is_unknown() || y.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&x, &y])));
            }
            match (&x.v, &y.v) {
                (Value::Date(s), Value::Date(e)) => {
                    let diff = e - s;
                    // Negative: the second date is before the first; report the raw signed gap.
                    let n = if diff < 0 {
                        diff
                    } else {
                        (diff - 1 + i64::from(*inclusive_start) + i64::from(*inclusive_end)).max(0)
                    };
                    Ok(Ev::known(Value::Int(n)))
                }
                (p, q) => Err(type_err(
                    path,
                    format!(
                        "days_between needs dates, found {} and {}",
                        p.type_name(),
                        q.type_name()
                    ),
                )),
            }
        }
        Expr::DateAdd { date, value, unit } => {
            let d = eval(date, &format!("{path}.date_add[0]"), ctx)?;
            if d.v.is_unknown() {
                return Ok(d);
            }
            match &d.v {
                Value::Date(days) => {
                    let out = match unit {
                        DurUnit::Day => {
                            days.checked_add(*value)
                                .ok_or_else(|| EvalError::Overflow {
                                    path: path.to_string(),
                                })?
                        }
                        DurUnit::CalendarMonth => add_months_clamped(*days, *value),
                        DurUnit::CalendarYear => {
                            let months =
                                value.checked_mul(12).ok_or_else(|| EvalError::Overflow {
                                    path: path.to_string(),
                                })?;
                            add_months_clamped(*days, months)
                        }
                    };
                    Ok(Ev::known(Value::Date(out)))
                }
                other => Err(type_err(
                    path,
                    format!("date_add needs a date, found {}", other.type_name()),
                )),
            }
        }
    }
}

fn to_amount(ev: &Ev) -> Result<AmountOut, EvalError> {
    match &ev.v {
        Value::Money(m) => Ok(AmountOut::Exact { krw: *m }),
        Value::MoneyRange { min, max } => Ok(AmountOut::Range {
            min_krw: *min,
            max_krw: *max,
        }),
        Value::Unknown => Ok(AmountOut::Unknown),
        other => Err(EvalError::AmountNotMoney {
            found: other.type_name(),
        }),
    }
}

fn convert_inputs(rule: &Rule, inputs: &J) -> Result<BTreeMap<String, Value>, EvalError> {
    let obj = inputs.as_object().ok_or(EvalError::InputsNotObject)?;
    for k in obj.keys() {
        if !rule.inputs.contains_key(k) {
            return Err(EvalError::UnknownInput(k.clone()));
        }
    }
    let mut out = BTreeMap::new();
    for (name, ty) in &rule.inputs {
        let v = match obj.get(name) {
            None | Some(J::Null) => Value::Unknown,
            Some(j) => {
                let bad = |expected: &'static str| EvalError::BadInput {
                    name: name.clone(),
                    expected,
                };
                match ty {
                    InputType::Bool => Value::Bool(j.as_bool().ok_or_else(|| bad("a boolean"))?),
                    InputType::Int => Value::Int(j.as_i64().ok_or_else(|| bad("an integer"))?),
                    InputType::MoneyKrw => match j.as_i64() {
                        Some(n) if n >= 0 => Value::Money(n),
                        _ => return Err(bad("a non-negative integer (KRW)")),
                    },
                    InputType::Date => Value::Date(
                        j.as_str()
                            .and_then(parse_date)
                            .ok_or_else(|| bad("a YYYY-MM-DD date"))?,
                    ),
                    InputType::Str => {
                        Value::Str(j.as_str().ok_or_else(|| bad("a string"))?.to_string())
                    }
                }
            }
        };
        out.insert(name.clone(), v);
    }
    Ok(out)
}

fn snapshot_hash(inputs: &BTreeMap<String, Value>) -> String {
    let mut h = Sha256::new();
    for (k, v) in inputs {
        h.update(k.as_bytes());
        h.update(b"=");
        h.update(v.to_string().as_bytes());
        h.update(b"\n");
    }
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

impl Rule {
    /// Evaluate the rule against an input snapshot (a JSON object; missing or null means unknown).
    pub fn evaluate(&self, inputs: &J) -> Result<EvaluationResult, EvalError> {
        let values = convert_inputs(self, inputs)?;
        let mut ctx = Ctx {
            inputs: &values,
            trace: Vec::new(),
        };
        let elig = eval(&self.eligibility, "eligibility", &mut ctx)?;
        let eligibility = to_tri(&elig, "eligibility")?;
        let (payout, missing): (Payout, BTreeSet<String>) = match eligibility {
            Tri::False => (Payout::NotPayable, BTreeSet::new()),
            Tri::True => {
                let amt = eval(&self.amount, "amount", &mut ctx)?;
                let blockers = if amt.v.is_unknown() {
                    amt.blockers.clone()
                } else {
                    BTreeSet::new()
                };
                (
                    Payout::Payable {
                        amount: to_amount(&amt)?,
                    },
                    blockers,
                )
            }
            Tri::Unknown => {
                let amt = eval(&self.amount, "amount", &mut ctx)?;
                let mut blockers = elig.blockers.clone();
                if amt.v.is_unknown() {
                    blockers.extend(amt.blockers.iter().cloned());
                }
                (
                    Payout::Undetermined {
                        conditional_amount: to_amount(&amt)?,
                    },
                    blockers,
                )
            }
        };
        Ok(EvaluationResult {
            rule_id: self.rule_id.clone(),
            schema_version: self.schema_version.clone(),
            engine_version: crate::ENGINE_VERSION,
            eligibility,
            payout,
            missing_inputs: missing.into_iter().collect(),
            trace: ctx.trace,
            input_snapshot_hash: snapshot_hash(&values),
        })
    }
}
