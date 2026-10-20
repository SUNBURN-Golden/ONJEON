//! Institution denominator loading (T-DT-04): the registry CSVs of `data/registry/` become
//! the top axis of the denominator — which institutions are in scope, which are excluded
//! and why (ADR-0018 §4).
//!
//! Scope mapping:
//!
//! | registry row | scope | exclusion reason |
//! |---|---|---|
//! | `insurers.csv` 53행 | in scope (`Insurer`) | — |
//! | `public-epost` (우체국보험) | in scope (`PublicInstitution`) | — |
//! | `coop-*`, `seed-coop-nh` (공제) | excluded | `cooperative_out_of_scope` |
//! | `public-ksure` (한국무역보험공사) | excluded | `non_personal_lines` |
//! | `entity_evidence = seed` 행 | excluded | `seed_not_listed` |
//! | `excluded_or_historical.csv` | excluded | `historical_or_non_insurer` |
//!
//! `seed` rows are never denominator rows (registry README: 기억 기반 후보는 분모에 넣지
//! 않는다). Exclusions keep their reason and provenance — the exclusion itself is part of
//! the denominator record (확보율 분모에서 빠지되 사유는 남는다).

use std::collections::BTreeMap;
use std::path::Path;

use onjeon_contracts::{AcquisitionStatus, EntityEvidence, HostAccess};

/// One typed registry row.
#[derive(Debug, Clone)]
pub struct InstitutionRow {
    pub insurer_id: String,
    pub name_ko: String,
    pub sector: String,
    pub foreign_branch: bool,
    pub listed_in: String,
    pub entity_evidence: EntityEvidence,
    pub in_current_assoc_list: bool,
    pub disclosure_url: String,
    pub disclosure_access: HostAccess,
    pub disclosure_access_detail: String,
    pub home_url: String,
    pub home_access: HostAccess,
    pub home_access_detail: String,
    pub disclosure_status: Option<AcquisitionStatus>,
    pub disclosure_gap_reason: String,
    pub product_list_status: Option<AcquisitionStatus>,
    pub product_list_reason: String,
    pub observed_at: String,
    pub notes: String,
    /// Which registry file this row came from (`insurers` | `cooperatives_and_others` |
    /// `excluded_or_historical`).
    pub registry_file: String,
}

/// Institution kind inside the in-scope denominator (기관 유형은 구분해서 관리).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InstitutionKind {
    Insurer,
    /// 우체국보험 — in scope but tracked as its own institution type.
    PublicInstitution,
}

/// One in-scope denominator entry: the institution plus its registry evidence.
#[derive(Debug, Clone)]
pub struct DenomEntry {
    pub row: InstitutionRow,
    pub kind: InstitutionKind,
}

/// A row kept out of the denominator — the exclusion and its reason are part of the
/// record (ADR-0018 §4: 공제는 분모에서 제외하고 사유를 남긴다).
#[derive(Debug, Clone)]
pub struct Exclusion {
    pub insurer_id: String,
    pub name_ko: String,
    /// `cooperative_out_of_scope` | `non_personal_lines` | `seed_not_listed` |
    /// `historical_or_non_insurer`
    pub reason: &'static str,
    /// Provenance pointer (`data/registry/<file>#<insurer_id>`).
    pub evidence_ref: String,
}

/// The loaded institution denominator.
#[derive(Debug, Clone, Default)]
pub struct Denominator {
    pub in_scope: Vec<DenomEntry>,
    pub exclusions: Vec<Exclusion>,
}

/// Load the denominator from the registry directory (`insurers.csv`,
/// `cooperatives_and_others.csv`, `excluded_or_historical.csv`).
pub fn load_denominator(registry_dir: &Path) -> Result<Denominator, LoadError> {
    let insurers = read_csv(&registry_dir.join("insurers.csv"))?;
    let coop = read_csv(&registry_dir.join("cooperatives_and_others.csv"))?;
    let excluded = read_csv(&registry_dir.join("excluded_or_historical.csv"))?;
    denominator_from_rows(insurers, coop, excluded)
}

/// Same as [`load_denominator`] on already-parsed tables (tests feed fixtures here).
pub fn denominator_from_rows(
    insurers: Vec<BTreeMap<String, String>>,
    cooperatives: Vec<BTreeMap<String, String>>,
    excluded: Vec<BTreeMap<String, String>>,
) -> Result<Denominator, LoadError> {
    let mut denom = Denominator::default();
    for row in insurers {
        let row = InstitutionRow::from_record(row, "insurers")?;
        push_scoped(&mut denom, row)?;
    }
    for row in cooperatives {
        let row = InstitutionRow::from_record(row, "cooperatives_and_others")?;
        push_scoped(&mut denom, row)?;
    }
    for row in excluded {
        let row = InstitutionRow::from_record(row, "excluded_or_historical")?;
        denom.exclusions.push(Exclusion {
            insurer_id: row.insurer_id.clone(),
            name_ko: row.name_ko.clone(),
            reason: "historical_or_non_insurer",
            evidence_ref: evidence_ref(&row),
        });
    }
    let mut ids = BTreeMap::new();
    for e in &denom.in_scope {
        if ids.insert(e.row.insurer_id.clone(), ()).is_some() {
            return Err(LoadError::DuplicateId(e.row.insurer_id.clone()));
        }
    }
    denom
        .in_scope
        .sort_by(|a, b| a.row.insurer_id.cmp(&b.row.insurer_id));
    Ok(denom)
}

/// Apply the ADR-0018 scope rules to one registry row.
fn push_scoped(denom: &mut Denominator, row: InstitutionRow) -> Result<(), LoadError> {
    if row.insurer_id.is_empty() {
        return Err(LoadError::MissingField {
            file: row.registry_file.clone(),
            field: "insurer_id",
        });
    }
    let exclude = |denom: &mut Denominator, row: &InstitutionRow, reason: &'static str| {
        denom.exclusions.push(Exclusion {
            insurer_id: row.insurer_id.clone(),
            name_ko: row.name_ko.clone(),
            reason,
            evidence_ref: evidence_ref(row),
        });
    };
    match row.insurer_id.as_str() {
        "public-epost" => denom.in_scope.push(DenomEntry {
            row,
            kind: InstitutionKind::PublicInstitution,
        }),
        "public-ksure" => exclude(denom, &row, "non_personal_lines"),
        id if id.starts_with("coop-") || id.starts_with("seed-coop-") => {
            exclude(denom, &row, "cooperative_out_of_scope")
        }
        // Seed candidates are never denominator rows (registry README: 기억 기반 후보).
        _ if row.entity_evidence == EntityEvidence::Seed => exclude(denom, &row, "seed_not_listed"),
        _ => denom.in_scope.push(DenomEntry {
            row,
            kind: InstitutionKind::Insurer,
        }),
    }
    Ok(())
}

fn evidence_ref(row: &InstitutionRow) -> String {
    format!("data/registry/{}.csv#{}", row.registry_file, row.insurer_id)
}

#[derive(Debug)]
pub enum LoadError {
    Io {
        file: String,
        message: String,
    },
    Csv {
        file: String,
        line: usize,
        message: String,
    },
    MissingField {
        file: String,
        field: &'static str,
    },
    BadValue {
        file: String,
        field: &'static str,
        value: String,
    },
    DuplicateId(String),
}

impl std::fmt::Display for LoadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io { file, message } => write!(f, "{file}: {message}"),
            Self::Csv {
                file,
                line,
                message,
            } => write!(f, "{file}:{line}: {message}"),
            Self::MissingField { file, field } => write!(f, "{file}: missing column {field}"),
            Self::BadValue { file, field, value } => {
                write!(f, "{file}: {field} has unknown value '{value}'")
            }
            Self::DuplicateId(id) => write!(f, "duplicate insurer_id {id}"),
        }
    }
}
impl std::error::Error for LoadError {}

/// Read and parse one CSV file into a header-keyed table.
pub fn read_csv(path: &Path) -> Result<Vec<BTreeMap<String, String>>, LoadError> {
    let file = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| path.display().to_string());
    let bytes = std::fs::read(path).map_err(|e| LoadError::Io {
        file: file.clone(),
        message: e.kind().to_string(),
    })?;
    parse_csv(&bytes).map_err(|(line, message)| LoadError::Csv {
        file,
        line,
        message,
    })
}

/// Minimal RFC 4180 parse: `,` separators, `"` quoting with `""` escapes, LF/CRLF,
/// embedded newlines inside quotes. Returns one `BTreeMap` per data row.
pub fn parse_csv(bytes: &[u8]) -> Result<Vec<BTreeMap<String, String>>, (usize, String)> {
    let text = String::from_utf8_lossy(bytes);
    let mut rows: Vec<Vec<String>> = Vec::new();
    let mut field = String::new();
    let mut row: Vec<String> = Vec::new();
    let mut in_quotes = false;
    let mut quoted_field = false;
    let mut line = 1usize;
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        if in_quotes {
            match c {
                '"' if chars.peek() == Some(&'"') => {
                    field.push('"');
                    chars.next();
                }
                '"' => in_quotes = false,
                '\n' => {
                    field.push('\n');
                    line += 1;
                }
                '\r' => {
                    if chars.peek() == Some(&'\n') {
                        field.push('\n');
                        chars.next();
                    } else {
                        field.push('\r');
                    }
                    line += 1;
                }
                _ => field.push(c),
            }
            continue;
        }
        match c {
            '"' if field.is_empty() && !quoted_field => {
                in_quotes = true;
                quoted_field = true;
            }
            ',' => {
                row.push(std::mem::take(&mut field));
                quoted_field = false;
            }
            '\n' => {
                row.push(std::mem::take(&mut field));
                quoted_field = false;
                rows.push(std::mem::take(&mut row));
                line += 1;
            }
            '\r' => {}
            _ => field.push(c),
        }
    }
    if !field.is_empty() || !row.is_empty() {
        row.push(field);
        rows.push(row);
    }
    if rows.is_empty() {
        return Err((line, "empty file".into()));
    }
    let header = rows.remove(0);
    let mut out = Vec::with_capacity(rows.len());
    for (i, r) in rows.into_iter().enumerate() {
        if r.len() == 1 && r[0].is_empty() {
            continue;
        }
        if r.len() != header.len() {
            return Err((
                i + 2,
                format!("{} fields but header has {}", r.len(), header.len()),
            ));
        }
        let mut m = BTreeMap::new();
        for (k, v) in header.iter().zip(r) {
            m.insert(k.clone(), v);
        }
        out.push(m);
    }
    Ok(out)
}

fn get<'a>(
    row: &'a BTreeMap<String, String>,
    file: &str,
    field: &'static str,
) -> Result<&'a str, LoadError> {
    row.get(field)
        .map(String::as_str)
        .ok_or(LoadError::MissingField {
            file: file.into(),
            field,
        })
}

fn vocab<T>(file: &str, field: &'static str, value: &str) -> Result<T, LoadError>
where
    T: for<'de> serde::Deserialize<'de>,
{
    serde_json::from_str::<T>(&format!(
        "\"{}\"",
        value.replace('\\', "\\\\").replace('"', "\\\"")
    ))
    .map_err(|_| LoadError::BadValue {
        file: file.into(),
        field,
        value: value.to_string(),
    })
}

impl InstitutionRow {
    /// Build a typed row. Unknown vocabulary values are an error, never a default
    /// (vocabulary rule 4). Columns absent in `excluded_or_historical.csv`
    /// (`entity_evidence`, `*_detail`, `disclosure_status`, `product_list_*`) become
    /// `None`/empty — the file's own `status` column is kept in `notes`-adjacent fields.
    fn from_record(row: BTreeMap<String, String>, file: &str) -> Result<Self, LoadError> {
        let opt = |f: &str| row.get(f).map(String::as_str).unwrap_or("").to_string();
        let entity_evidence = match row.get("entity_evidence") {
            Some(v) if !v.is_empty() => vocab::<EntityEvidence>(file, "entity_evidence", v)?,
            _ => {
                // excluded_or_historical has no entity_evidence column; its `status`
                // column carries the legacy label.
                match row.get("status").map(String::as_str) {
                    Some("verified_2_sources") | Some("two_or_more_sources") => {
                        EntityEvidence::TwoOrMoreSources
                    }
                    Some("one_source") | Some("verified_1_source") => EntityEvidence::OneSource,
                    _ => EntityEvidence::OneSource,
                }
            }
        };
        let acq = |field: &'static str| -> Result<Option<AcquisitionStatus>, LoadError> {
            match row.get(field).map(String::as_str) {
                Some(v) if !v.is_empty() => vocab::<AcquisitionStatus>(file, field, v).map(Some),
                _ => Ok(None),
            }
        };
        let host = |field: &'static str| -> Result<HostAccess, LoadError> {
            match row.get(field).map(String::as_str) {
                Some(v) if !v.is_empty() => vocab::<HostAccess>(file, field, v),
                _ => Ok(HostAccess::NotChecked),
            }
        };
        Ok(Self {
            insurer_id: get(&row, file, "insurer_id")?.into(),
            name_ko: opt("name_ko"),
            sector: opt("sector"),
            foreign_branch: opt("foreign_branch") == "true",
            listed_in: opt("listed_in"),
            entity_evidence,
            in_current_assoc_list: opt("in_current_assoc_list") == "true",
            disclosure_url: opt("disclosure_url"),
            disclosure_access: host("disclosure_access")?,
            disclosure_access_detail: opt("disclosure_access_detail"),
            home_url: opt("home_url"),
            home_access: host("home_access")?,
            home_access_detail: opt("home_access_detail"),
            disclosure_status: acq("disclosure_status")?,
            disclosure_gap_reason: opt("disclosure_gap_reason"),
            product_list_status: acq("product_list_status")?,
            product_list_reason: opt("product_list_reason"),
            observed_at: opt("observed_at"),
            notes: opt("notes"),
            registry_file: file.into(),
        })
    }
}
