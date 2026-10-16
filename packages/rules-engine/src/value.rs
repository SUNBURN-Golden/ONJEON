use crate::date::format_date;
use std::fmt;

/// One event of a `class_money_list` input: an equivalence class and an amount that may be unknown.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ListItem {
    pub class: String,
    pub krw: Option<i64>,
}

/// Runtime values. `Unknown` is a value of any type and is never coerced to zero.
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Bool(bool),
    Int(i64),
    /// KRW, integer won.
    Money(i64),
    /// Inclusive range of KRW, used when the source leaves rounding unspecified.
    MoneyRange {
        min: i64,
        max: i64,
    },
    /// Rational rate, `num/den`, den > 0.
    Rate {
        num: i64,
        den: i64,
    },
    /// Days since 1970-01-01.
    Date(i64),
    Str(String),
    /// Events of one moment, each with an equivalence class (rule-0.2).
    List(Vec<ListItem>),
    Unknown,
}

impl Value {
    pub fn type_name(&self) -> &'static str {
        match self {
            Value::Bool(_) => "bool",
            Value::Int(_) => "int",
            Value::Money(_) => "money",
            Value::MoneyRange { .. } => "money_range",
            Value::Rate { .. } => "rate",
            Value::Date(_) => "date",
            Value::Str(_) => "string",
            Value::List(_) => "class_money_list",
            Value::Unknown => "unknown",
        }
    }

    pub fn is_unknown(&self) -> bool {
        matches!(self, Value::Unknown)
    }
}

impl fmt::Display for Value {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Value::Bool(b) => write!(f, "{b}"),
            Value::Int(i) => write!(f, "{i}"),
            Value::Money(m) => write!(f, "{m} KRW"),
            Value::MoneyRange { min, max } => write!(f, "{min}..{max} KRW"),
            Value::Rate { num, den } => write!(f, "{num}/{den}"),
            Value::Date(d) => write!(f, "{}", format_date(*d)),
            Value::Str(s) => write!(f, "{s:?}"),
            Value::List(items) => {
                write!(f, "[")?;
                for (i, it) in items.iter().enumerate() {
                    if i > 0 {
                        write!(f, ",")?;
                    }
                    match it.krw {
                        Some(k) => write!(f, "{:?}={k}", it.class)?,
                        None => write!(f, "{:?}=unknown", it.class)?,
                    }
                }
                write!(f, "]")
            }
            Value::Unknown => write!(f, "unknown"),
        }
    }
}

/// Parse a non-negative decimal string like "0.5" into a rational rate.
pub fn parse_rate(s: &str) -> Option<Value> {
    let (int_part, frac_part) = match s.split_once('.') {
        Some((a, b)) => (a, b),
        None => (s, ""),
    };
    if int_part.is_empty() && frac_part.is_empty() {
        return None;
    }
    if !int_part.bytes().all(|c| c.is_ascii_digit())
        || !frac_part.bytes().all(|c| c.is_ascii_digit())
    {
        return None;
    }
    if frac_part.len() > 9 || int_part.len() > 9 {
        return None;
    }
    let den: i64 = 10_i64.pow(frac_part.len() as u32);
    let ip: i64 = if int_part.is_empty() {
        0
    } else {
        int_part.parse().ok()?
    };
    let fp: i64 = if frac_part.is_empty() {
        0
    } else {
        frac_part.parse().ok()?
    };
    Some(Value::Rate {
        num: ip * den + fp,
        den,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rate_parsing() {
        assert_eq!(parse_rate("0.5"), Some(Value::Rate { num: 5, den: 10 }));
        assert_eq!(parse_rate("1"), Some(Value::Rate { num: 1, den: 1 }));
        assert_eq!(
            parse_rate("12.345"),
            Some(Value::Rate {
                num: 12_345,
                den: 1000
            })
        );
        assert_eq!(parse_rate("abc"), None);
        assert_eq!(parse_rate("-0.5"), None);
        assert_eq!(parse_rate(""), None);
    }
}
