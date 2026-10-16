//! Deterministic evaluation with three-valued logic and blocker tracking.
//!
//! Every unknown value carries the set of unknown inputs that caused it
//! (`blockers`). A definite result (for example `false AND unknown`) has no
//! blockers, so `missing_inputs` lists only inputs that actually matter.

use crate::date::{add_days, add_months_clamped, civil_from_days, parse_date};
use crate::rule::{Boundary, CmpOp, ContractEffect, DurUnit, Expr, InputType, Rounding, Rule};
use crate::tri::Tri;
use crate::value::{ListItem, Value};
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
    DateOutOfRange {
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
            EvalError::DateOutOfRange { path } => write!(
                f,
                "date outside the supported range 1900-01-01..2199-12-31 at {path}"
            ),
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

/// The contract-level consequence of the rule (rule-0.2). Unknown eligibility is never `None`
/// unless the rule itself declares no effect.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ContractEffectOut {
    /// The rule declares no effect, or its eligibility is false.
    None,
    /// Eligibility is established, so the effect applies.
    Applies { effect: ContractEffect },
    /// Eligibility cannot be decided yet; this is what would happen if it holds.
    Undetermined { conditional_effect: ContractEffect },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EvaluationResult {
    pub rule_id: String,
    /// Content version of the rule that produced this result.
    pub rule_version: String,
    /// Dataset release the rule came from (`None` only for fixtures).
    pub release_id: Option<String>,
    /// Hash of the exact rule content used.
    pub rule_content_hash: String,
    /// Source clauses the rule encodes (principle 5).
    pub evidence_refs: Vec<String>,
    pub schema_version: String,
    pub engine_version: &'static str,
    pub eligibility: Tri,
    pub payout: Payout,
    pub contract_effect: ContractEffectOut,
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

/// Scales an amount (or an amount range) by `num/den`. The factor is non-negative, so the
/// product is monotonic and each bound maps to the matching bound of the result.
fn scale_money(
    m: &Value,
    num: i64,
    den: i64,
    rounding: Rounding,
    unit: i64,
    path: &str,
) -> Result<Value, EvalError> {
    match m {
        Value::Money(x) => multiply_rate(*x, num, den, rounding, unit, path),
        Value::MoneyRange { min, max } => {
            let lo_v = multiply_rate(*min, num, den, rounding, unit, path)?;
            let hi_v = multiply_rate(*max, num, den, rounding, unit, path)?;
            let (lo, _) = money_bounds(&lo_v, path)?;
            let (_, hi) = money_bounds(&hi_v, path)?;
            Ok(money_value(lo, hi))
        }
        other => Err(type_err(
            path,
            format!("expected money, found {}", other.type_name()),
        )),
    }
}

/// Completed years from `from` to `at` (`from <= at`) and whether `at` is exactly an anniversary.
/// An anniversary that does not exist (Feb 29 in a common year) falls on the last day of the month.
fn completed_years(from: i64, at: i64) -> (i64, bool) {
    let mut k = civil_from_days(at).0 - civil_from_days(from).0;
    loop {
        match add_months_clamped(from, k * 12) {
            Some(d) if d <= at => return (k, d == at),
            _ => k -= 1,
        }
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

/// Evaluates a branch whose selection is still undecided. A failure is returned instead of
/// aborting the rule, and its partial trace is replaced by one `error:` entry so the trace
/// shows why the branch contributed nothing.
fn eval_untaken(expr: &Expr, path: &str, ctx: &mut Ctx<'_>) -> Result<Ev, EvalError> {
    let mark = ctx.trace.len();
    let out = eval(expr, path, ctx);
    if let Err(err) = &out {
        ctx.trace.truncate(mark);
        ctx.trace.push(TraceEntry {
            path: path.to_string(),
            op: expr.op_name(),
            result: format!("error: {err}"),
        });
    }
    out
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
                    let then_path = format!("{path}.then");
                    let else_path = format!("{path}.else");
                    let a = eval_untaken(t, &then_path, ctx);
                    let b = eval_untaken(e, &else_path, ctx);
                    // An error in a branch only matters if that branch is taken, and the
                    // condition is undecided. If both branches fail the rule fails either
                    // way, so that error is real; otherwise the failed branch is unknown.
                    let (a, b) = match (a, b) {
                        (Err(err), Err(_)) => return Err(err),
                        (a, b) => (
                            a.unwrap_or_else(|_| Ev::unknown(BTreeSet::new())),
                            b.unwrap_or_else(|_| Ev::unknown(BTreeSet::new())),
                        ),
                    };
                    if !a.v.is_unknown() && a.v == b.v {
                        Ok(a)
                    } else {
                        // The condition is undecided and the branches disagree (or one is
                        // itself unknown or failed). Blockers are the condition's unknown
                        // inputs plus the unknown inputs inside any unknown branch.
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
                // A range from an earlier unspecified rounding. The rate is non-negative, so
                // the product is monotonic: each bound maps to the matching bound of the result.
                (Value::MoneyRange { min, max }, Value::Rate { num, den }) => {
                    let lo_v = multiply_rate(*min, *num, *den, *rounding, *unit, path)?;
                    let hi_v = multiply_rate(*max, *num, *den, *rounding, *unit, path)?;
                    let (lo, _) = money_bounds(&lo_v, path)?;
                    let (_, hi) = money_bounds(&hi_v, path)?;
                    Ok(Ev::known(money_value(lo, hi)))
                }
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
                    // Inclusivity is defined for a forward interval only; a raw negative gap
                    // would be a different scale (and 0 would be ambiguous), so reject it.
                    if diff < 0 {
                        return Err(type_err(
                            path,
                            format!(
                                "days_between needs the first date on or before the second, \
                                 found the second {} day(s) earlier; compare the dates with \
                                 lt/gt instead",
                                -diff
                            ),
                        ));
                    }
                    let n =
                        (diff - 1 + i64::from(*inclusive_start) + i64::from(*inclusive_end)).max(0);
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
        Expr::MultiplyCount(money, count) => {
            let m = eval(money, &format!("{path}.multiply_count[0]"), ctx)?;
            let c = eval(count, &format!("{path}.multiply_count[1]"), ctx)?;
            if m.v.is_unknown() || c.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&m, &c])));
            }
            let (lo, hi) = money_bounds(&m.v, path)?;
            let n = match &c.v {
                Value::Int(n) if *n >= 0 => *n,
                Value::Int(n) => {
                    return Err(type_err(path, format!("count must be >= 0, found {n}")))
                }
                other => {
                    return Err(type_err(
                        path,
                        format!(
                            "multiply_count needs an int count, found {}",
                            other.type_name()
                        ),
                    ))
                }
            };
            let ov = || EvalError::Overflow {
                path: path.to_string(),
            };
            Ok(Ev::known(money_value(
                lo.checked_mul(n).ok_or_else(ov)?,
                hi.checked_mul(n).ok_or_else(ov)?,
            )))
        }
        Expr::SubtractFloor0(a, b) => {
            let x = eval(a, &format!("{path}.subtract_floor0[0]"), ctx)?;
            let y = eval(b, &format!("{path}.subtract_floor0[1]"), ctx)?;
            if x.v.is_unknown() || y.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&x, &y])));
            }
            let (xlo, xhi) = money_bounds(&x.v, path)?;
            let (ylo, yhi) = money_bounds(&y.v, path)?;
            // Amounts are non-negative, so the differences cannot overflow.
            Ok(Ev::known(money_value(
                (xlo - yhi).max(0),
                (xhi - ylo).max(0),
            )))
        }
        Expr::ProRata {
            money,
            part,
            whole,
            rounding,
            unit,
        } => {
            let m = eval(money, &format!("{path}.pro_rata[0]"), ctx)?;
            let p = eval(part, &format!("{path}.pro_rata[1]"), ctx)?;
            let w = eval(whole, &format!("{path}.pro_rata[2]"), ctx)?;
            if m.v.is_unknown() || p.v.is_unknown() || w.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&m, &p, &w])));
            }
            let (pn, wn) = match (&p.v, &w.v) {
                (Value::Int(a), Value::Int(b)) | (Value::Money(a), Value::Money(b)) => (*a, *b),
                (a, b) => {
                    return Err(type_err(
                        path,
                        format!(
                            "pro_rata needs part and whole as int or exact money, found {} and {}",
                            a.type_name(),
                            b.type_name()
                        ),
                    ))
                }
            };
            if pn < 0 || wn < 0 {
                return Err(type_err(path, "part and whole must be non-negative"));
            }
            // A zero whole has no share: the answer is unknown, not an error and not zero.
            if wn == 0 {
                return Ok(Ev::unknown(BTreeSet::new()));
            }
            if pn > wn {
                return Err(type_err(path, format!("part {pn} exceeds whole {wn}")));
            }
            Ok(Ev::known(scale_money(
                &m.v, pn, wn, *rounding, *unit, path,
            )?))
        }
        Expr::DivideCount {
            money,
            count,
            rounding,
            unit,
        } => {
            let m = eval(money, &format!("{path}.divide_count[0]"), ctx)?;
            let c = eval(count, &format!("{path}.divide_count[1]"), ctx)?;
            if m.v.is_unknown() || c.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&m, &c])));
            }
            let n = match &c.v {
                Value::Int(n) if *n >= 0 => *n,
                Value::Int(n) => {
                    return Err(type_err(path, format!("count must be >= 0, found {n}")))
                }
                other => {
                    return Err(type_err(
                        path,
                        format!(
                            "divide_count needs an int count, found {}",
                            other.type_name()
                        ),
                    ))
                }
            };
            // Dividing among zero has no answer: unknown, never zero.
            if n == 0 {
                return Ok(Ev::unknown(BTreeSet::new()));
            }
            Ok(Ev::known(scale_money(&m.v, 1, n, *rounding, *unit, path)?))
        }
        Expr::AnniversaryBand {
            from,
            at,
            bands,
            boundary,
        } => {
            let f = eval(from, &format!("{path}.anniversary_band[0]"), ctx)?;
            let a = eval(at, &format!("{path}.anniversary_band[1]"), ctx)?;
            if f.v.is_unknown() || a.v.is_unknown() {
                return Ok(Ev::unknown(union_unknown([&f, &a])));
            }
            let (Value::Date(fd), Value::Date(ad)) = (&f.v, &a.v) else {
                return Err(type_err(
                    path,
                    format!(
                        "anniversary_band needs dates, found {} and {}",
                        f.v.type_name(),
                        a.v.type_name()
                    ),
                ));
            };
            if ad < fd {
                return Err(type_err(
                    path,
                    format!(
                        "anniversary_band needs `at` on or after `from`, found {} day(s) earlier",
                        fd - ad
                    ),
                ));
            }
            let (years, exact) = completed_years(*fd, *ad);
            // The first band is the base and always applies. A later band applies once its start
            // anniversary is reached (lower_inclusive) or passed (upper_inclusive).
            let applies = |i: usize, start: i64| {
                i == 0
                    || match boundary {
                        Boundary::Lower => start <= years,
                        Boundary::Upper => start < years || (start == years && !exact),
                    }
            };
            let value = bands
                .iter()
                .enumerate()
                .rfind(|(i, (start, _))| applies(*i, *start))
                .map(|(_, (_, v))| v.clone())
                .expect("the first band always applies");
            Ok(Ev::known(value))
        }
        Expr::MaxOver(name) => {
            let list = match ctx.inputs.get(name) {
                Some(Value::List(items)) => items,
                Some(Value::Unknown) | None => {
                    return Ok(Ev::unknown(BTreeSet::from([name.clone()])))
                }
                Some(other) => {
                    return Err(type_err(
                        path,
                        format!("max_over needs a list, found {}", other.type_name()),
                    ))
                }
            };
            // An event with an unknown amount may be the largest of its class, so the total is unknown.
            if list.iter().any(|it| it.krw.is_none()) {
                return Ok(Ev::unknown(BTreeSet::from([name.clone()])));
            }
            let mut best: BTreeMap<&str, i64> = BTreeMap::new();
            for it in list {
                let k = it.krw.expect("checked above");
                let slot = best.entry(it.class.as_str()).or_insert(0);
                *slot = (*slot).max(k);
            }
            let mut total = 0_i64;
            for v in best.values() {
                total = total.checked_add(*v).ok_or_else(|| EvalError::Overflow {
                    path: path.to_string(),
                })?;
            }
            Ok(Ev::known(Value::Money(total)))
        }
        Expr::DateAdd { date, value, unit } => {
            let d = eval(date, &format!("{path}.date_add[0]"), ctx)?;
            if d.v.is_unknown() {
                return Ok(d);
            }
            match &d.v {
                Value::Date(days) => {
                    let out = match unit {
                        DurUnit::Day => add_days(*days, *value),
                        DurUnit::CalendarMonth => add_months_clamped(*days, *value),
                        DurUnit::CalendarYear => value
                            .checked_mul(12)
                            .and_then(|months| add_months_clamped(*days, months)),
                    };
                    let out = out.ok_or_else(|| EvalError::DateOutOfRange {
                        path: path.to_string(),
                    })?;
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
                            .ok_or_else(|| bad("a YYYY-MM-DD date between 1900 and 2199"))?,
                    ),
                    InputType::Str => {
                        Value::Str(j.as_str().ok_or_else(|| bad("a string"))?.to_string())
                    }
                    InputType::ClassMoneyList => {
                        const WANT: &str = "a list of {class, krw} (class: non-empty string, krw: non-negative integer or null)";
                        let arr = j
                            .as_array()
                            .filter(|a| a.len() <= 1000)
                            .ok_or_else(|| bad(WANT))?;
                        let mut items = Vec::with_capacity(arr.len());
                        for e in arr {
                            let o = e
                                .as_object()
                                .filter(|o| o.len() == 2)
                                .ok_or_else(|| bad(WANT))?;
                            let class = o
                                .get("class")
                                .and_then(J::as_str)
                                .filter(|c| !c.trim().is_empty())
                                .ok_or_else(|| bad(WANT))?;
                            let krw = match o.get("krw") {
                                Some(J::Null) => None,
                                Some(k) => {
                                    Some(k.as_i64().filter(|n| *n >= 0).ok_or_else(|| bad(WANT))?)
                                }
                                None => return Err(bad(WANT)),
                            };
                            items.push(ListItem {
                                class: class.to_string(),
                                krw,
                            });
                        }
                        Value::List(items)
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
        let contract_effect = match (eligibility, self.contract_effect) {
            (_, ContractEffect::None) | (Tri::False, _) => ContractEffectOut::None,
            (Tri::True, effect) => ContractEffectOut::Applies { effect },
            (Tri::Unknown, effect) => ContractEffectOut::Undetermined {
                conditional_effect: effect,
            },
        };
        Ok(EvaluationResult {
            rule_id: self.rule_id.clone(),
            rule_version: self.rule_version.clone(),
            release_id: self.release_id.clone(),
            rule_content_hash: self.content_hash.clone(),
            evidence_refs: self.evidence_refs.clone(),
            schema_version: self.schema_version.clone(),
            engine_version: crate::ENGINE_VERSION,
            eligibility,
            payout,
            contract_effect,
            missing_inputs: missing.into_iter().collect(),
            trace: ctx.trace,
            input_snapshot_hash: snapshot_hash(&values),
        })
    }
}
