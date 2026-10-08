//! Civil-date arithmetic without external crates. Dates are days since 1970-01-01.

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

/// Parse "YYYY-MM-DD" into days since epoch. Returns None for invalid dates.
pub fn parse_date(s: &str) -> Option<i64> {
    let b = s.as_bytes();
    if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
        return None;
    }
    let y: i64 = s[0..4].parse().ok()?;
    let m: i64 = s[5..7].parse().ok()?;
    let d: i64 = s[8..10].parse().ok()?;
    if !(1..=12).contains(&m) || d < 1 || d > days_in_month(y, m) {
        return None;
    }
    Some(days_from_civil(y, m, d))
}

pub fn format_date(days: i64) -> String {
    let (y, m, d) = civil_from_days(days);
    format!("{y:04}-{m:02}-{d:02}")
}

/// Add calendar months, clamping the day to the end of the target month.
pub fn add_months_clamped(days: i64, months: i64) -> i64 {
    let (y, m, d) = civil_from_days(days);
    let total = y * 12 + (m - 1) + months;
    let ny = total.div_euclid(12);
    let nm = total.rem_euclid(12) + 1;
    let nd = d.min(days_in_month(ny, nm));
    days_from_civil(ny, nm, nd)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_and_known_dates() {
        assert_eq!(days_from_civil(1970, 1, 1), 0);
        assert_eq!(parse_date("2000-02-29"), Some(days_from_civil(2000, 2, 29)));
        assert_eq!(parse_date("1900-02-29"), None, "1900 is not a leap year");
        assert_eq!(parse_date("2026-13-01"), None);
        for z in [-100_000, -1, 0, 1, 11_000, 20_000, 40_000] {
            let (y, m, d) = civil_from_days(z);
            assert_eq!(days_from_civil(y, m, d), z);
        }
        assert_eq!(format_date(parse_date("2026-10-08").unwrap()), "2026-10-08");
    }

    #[test]
    fn month_end_clamps() {
        let jan31 = parse_date("2026-01-31").unwrap();
        assert_eq!(format_date(add_months_clamped(jan31, 1)), "2026-02-28");
        let jan31_leap = parse_date("2024-01-31").unwrap();
        assert_eq!(format_date(add_months_clamped(jan31_leap, 1)), "2024-02-29");
        assert_eq!(format_date(add_months_clamped(jan31, 12)), "2027-01-31");
        assert_eq!(format_date(add_months_clamped(jan31, -2)), "2025-11-30");
    }
}
