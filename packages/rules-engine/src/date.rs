//! Civil-date arithmetic without external crates. Dates are days since 1970-01-01.
//!
//! Only years 1900..=2199 are supported. Every operation that can leave this
//! range returns `None` instead of overflowing or producing a wrong date.

pub const MIN_YEAR: i64 = 1900;
pub const MAX_YEAR: i64 = 2199;

/// First supported day (1900-01-01) as days since epoch.
pub fn min_day() -> i64 {
    days_from_civil(MIN_YEAR, 1, 1)
}

/// Last supported day (2199-12-31) as days since epoch.
pub fn max_day() -> i64 {
    days_from_civil(MAX_YEAR, 12, 31)
}

pub fn in_supported_range(days: i64) -> bool {
    (min_day()..=max_day()).contains(&days)
}

/// Days since 1970-01-01 for a proleptic Gregorian date (Hinnant's algorithm).
pub fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

pub fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (if m <= 2 { y + 1 } else { y }, m, d)
}

pub fn is_leap(y: i64) -> bool {
    (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
}

pub fn days_in_month(y: i64, m: i64) -> i64 {
    match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if is_leap(y) {
                29
            } else {
                28
            }
        }
        _ => 0,
    }
}

/// Parse exactly zero-padded ASCII "YYYY-MM-DD" into days since epoch.
/// Returns `None` for invalid dates; signs and alternate spellings are rejected.
pub fn parse_date(s: &str) -> Option<i64> {
    let b = s.as_bytes();
    if b.len() != 10
        || b[4] != b'-'
        || b[7] != b'-'
        || !b[0..4].iter().all(u8::is_ascii_digit)
        || !b[5..7].iter().all(u8::is_ascii_digit)
        || !b[8..10].iter().all(u8::is_ascii_digit)
    {
        return None;
    }
    let y: i64 = s[0..4].parse().ok()?;
    let m: i64 = s[5..7].parse().ok()?;
    let d: i64 = s[8..10].parse().ok()?;
    if !(MIN_YEAR..=MAX_YEAR).contains(&y)
        || !(1..=12).contains(&m)
        || d < 1
        || d > days_in_month(y, m)
    {
        return None;
    }
    Some(days_from_civil(y, m, d))
}

pub fn format_date(days: i64) -> String {
    let (y, m, d) = civil_from_days(days);
    format!("{y:04}-{m:02}-{d:02}")
}

/// Add calendar months, clamping the day to the end of the target month.
/// Returns `None` if the input or the result is outside the supported range.
pub fn add_months_clamped(days: i64, months: i64) -> Option<i64> {
    if !in_supported_range(days) {
        return None;
    }
    let (y, m, d) = civil_from_days(days);
    let total = y.checked_mul(12)?.checked_add(m - 1)?.checked_add(months)?;
    let ny = total.div_euclid(12);
    if !(MIN_YEAR..=MAX_YEAR).contains(&ny) {
        return None;
    }
    let nm = total.rem_euclid(12) + 1;
    let nd = d.min(days_in_month(ny, nm));
    Some(days_from_civil(ny, nm, nd))
}

/// Add days. Returns `None` if the input or the result is outside the supported range.
pub fn add_days(days: i64, n: i64) -> Option<i64> {
    if !in_supported_range(days) {
        return None;
    }
    let out = days.checked_add(n)?;
    in_supported_range(out).then_some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_date_rejects_non_digits_in_every_component() {
        for date in [
            "2026-+1-+5",
            "2026-+1-05",
            "2026-01-+5",
            "2024-+2-+9",
            "2024-+2-09",
            "2024-02-+9",
            "+202-02-09",
        ] {
            assert_eq!(parse_date(date), None, "must reject {date:?}");
        }
        for index in [0, 1, 2, 3, 5, 6, 8, 9] {
            for non_digit in ['+', '-', ' ', '\t', 'x', 'é', '２'] {
                let mut date = "2024-02-09".to_owned();
                date.replace_range(index..index + 1, &non_digit.to_string());
                assert_eq!(parse_date(&date), None, "must reject {date:?}");
            }
        }
    }

    #[test]
    fn parse_date_preserves_canonical_dates_and_calendar_validation() {
        for date in [
            "1900-01-01",
            "1970-01-01",
            "2024-02-09",
            "2024-02-29",
            "2026-01-05",
            "2199-12-31",
        ] {
            assert_eq!(format_date(parse_date(date).unwrap()), date);
        }
        for date in [
            "2024-2-09",
            "2024-02-9",
            "2024/02/09",
            "2024-02-09 ",
            "",
            "2024-00-09",
            "2024-02-00",
            "2024-13-09",
            "2024-04-31",
            "2023-02-29",
        ] {
            assert_eq!(parse_date(date), None, "must reject {date:?}");
        }
    }

    #[test]
    fn roundtrip_and_known_dates() {
        assert_eq!(days_from_civil(1970, 1, 1), 0);
        assert_eq!(parse_date("2000-02-29"), Some(days_from_civil(2000, 2, 29)));
        assert_eq!(parse_date("1900-02-29"), None, "1900 is not a leap year");
        assert_eq!(parse_date("2026-13-01"), None);
        assert_eq!(parse_date("1899-12-31"), None, "below supported range");
        assert_eq!(parse_date("2200-01-01"), None, "above supported range");
        for z in [-100_000, -1, 0, 1, 11_000, 20_000, 40_000] {
            let (y, m, d) = civil_from_days(z);
            assert_eq!(days_from_civil(y, m, d), z);
        }
        assert_eq!(format_date(parse_date("2026-10-08").unwrap()), "2026-10-08");
    }

    #[test]
    fn month_end_clamps() {
        let jan31 = parse_date("2026-01-31").unwrap();
        assert_eq!(
            format_date(add_months_clamped(jan31, 1).unwrap()),
            "2026-02-28"
        );
        let jan31_leap = parse_date("2024-01-31").unwrap();
        assert_eq!(
            format_date(add_months_clamped(jan31_leap, 1).unwrap()),
            "2024-02-29"
        );
        assert_eq!(
            format_date(add_months_clamped(jan31, 12).unwrap()),
            "2027-01-31"
        );
        assert_eq!(
            format_date(add_months_clamped(jan31, -2).unwrap()),
            "2025-11-30"
        );
    }

    #[test]
    fn out_of_range_and_overflow_return_none_instead_of_panicking() {
        let d = parse_date("2026-01-31").unwrap();
        assert_eq!(add_months_clamped(d, i64::MAX), None);
        assert_eq!(add_months_clamped(d, i64::MIN), None);
        assert_eq!(add_months_clamped(d, 12 * 200), None, "2226 is beyond 2199");
        assert_eq!(add_months_clamped(i64::MAX, 1), None);
        assert_eq!(add_days(d, i64::MAX), None);
        assert_eq!(add_days(d, 1_000_000), None);
        assert_eq!(add_days(max_day(), 1), None);
        assert_eq!(add_days(max_day(), 0), Some(max_day()));
    }
}
