//! T-CT-05 persistence. Values are parameters; table and column identifiers come from
//! a closed mapping and PostgreSQL's catalogue. No domain table is auto-created.
use crate::{AcquisitionTask, KnowledgeError, ReviewDecision};
use onjeon_ontology::Abox;
use postgres::{Client, GenericClient, NoTls};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Mutex;

pub(crate) struct PostgresStore(Mutex<Client>);
impl std::fmt::Debug for PostgresStore {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("PostgresStore([connection redacted])")
    }
}

pub(crate) struct Snapshot {
    pub abox: Abox,
    pub decisions: BTreeMap<String, ReviewDecision>,
    pub tasks: BTreeMap<String, AcquisitionTask>,
    pub candidates: BTreeSet<String>,
}

pub(crate) fn db_error(error: postgres::Error) -> KnowledgeError {
    // Never return SQL detail: it may contain a row or connection credentials.
    KnowledgeError::Database {
        code: error.code().map(|c| c.code().to_owned()),
        constraint: error
            .as_db_error()
            .and_then(|e| e.constraint())
            .map(str::to_owned),
    }
}

/// Predicates the ontology shapes with both a target and a literal (`object` + `value`).
/// `chk_assertion_object_xor_value` stores exactly one of them: the target goes to the
/// typed column and the literal lives only in `knowledge.record_extension`, written in the
/// same transaction. `snapshot` restores it, so the mapping is reversible and K4/K12 still
/// read the relation after a reconnect.
const DUAL_REFERENCE_PREDICATES: &[&str] = &["scope_relation"];

fn dual_reference(value: &Value) -> bool {
    value
        .get("predicate")
        .and_then(Value::as_str)
        .is_some_and(|p| DUAL_REFERENCE_PREDICATES.contains(&p))
        && value.get("object").and_then(Value::as_str).is_some()
        && value.get("value").is_some_and(|v| !v.is_null())
}

/// The row shape sent to the public table. Only the closed mapping above changes anything.
fn sql_shape(section: &str, value: &Value) -> Value {
    let mut sql = value.clone();
    if section == "assertions" && dual_reference(value) {
        sql.as_object_mut().unwrap().remove("value");
    }
    sql
}

const TABLES: &[(&str, &str)] = &[
    ("raw_assets", "public.raw_asset"),
    ("observations", "public.observation"),
    ("segments", "public.document_segment"),
    ("clauses", "public.clause"),
    ("terms_editions", "public.terms_edition"),
    ("terms_lineages", "public.terms_lineage"),
    ("nodes", "public.node"),
    ("code_systems", "public.code_system"),
    ("assertions", "public.assertion"),
    ("premium_observations", "public.premium_observation"),
    ("gaps", "public.gap"),
];

impl PostgresStore {
    pub fn connect(config: &str) -> Result<Self, KnowledgeError> {
        Ok(Self(Mutex::new(
            Client::connect(config, NoTls).map_err(db_error)?,
        )))
    }

    pub fn snapshot(&self) -> Result<Snapshot, KnowledgeError> {
        let mut client = self.0.lock().map_err(|_| KnowledgeError::Immutable)?;
        let mut tx = client
            .build_transaction()
            .isolation_level(postgres::IsolationLevel::RepeatableRead)
            .read_only(true)
            .start()
            .map_err(db_error)?;
        let mut abox = Abox::default();
        let extensions: BTreeMap<(String, String), Value> = tx
            .query(
                "SELECT section, id, payload FROM knowledge.record_extension",
                &[],
            )
            .map_err(db_error)?
            .iter()
            .map(|r| ((r.get(0), r.get(1)), r.get(2)))
            .collect();
        for &(section, table) in TABLES.iter().chain(std::iter::once(&(
            "premium_observations",
            "knowledge.raw_premium_observation",
        ))) {
            for row in tx
                .query(
                    &format!("SELECT to_jsonb(t) FROM {table} t ORDER BY id"),
                    &[],
                )
                .map_err(db_error)?
            {
                let mut value: Value = row.get(0);
                if let Some(extra) =
                    extensions.get(&(section.to_owned(), value["id"].as_str().unwrap().to_owned()))
                {
                    // Preserve non-SQL attributes only. Actual DB columns always win.
                    let mut merged = extra.clone();
                    merged
                        .as_object_mut()
                        .unwrap()
                        .extend(value.as_object().unwrap().clone());
                    // Reverse of `sql_shape`: the literal of a dual-reference assertion was
                    // never sent to the NULL `value` column, so the payload holds it.
                    if section == "assertions"
                        && dual_reference(extra)
                        && merged.get("value").is_none_or(Value::is_null)
                    {
                        merged["value"] = extra["value"].clone();
                    }
                    value = merged;
                }
                abox.section_mut(section).push(value);
            }
        }
        for row in tx.query("SELECT to_jsonb(c) || jsonb_build_object('assertions', (SELECT jsonb_agg(assertion_id ORDER BY assertion_id) FROM public.conflict_member WHERE conflict_id=c.id)) FROM public.conflict c ORDER BY id", &[]).map_err(db_error)? {
            let mut value: Value = row.get(0);
            if let Some(extra) = extensions.get(&("conflicts".to_owned(), value["id"].as_str().unwrap().to_owned())) {
                let mut merged = extra.clone();
                merged.as_object_mut().unwrap().extend(value.as_object().unwrap().clone());
                value = merged;
            }
            abox.section_mut("conflicts").push(value);
        }
        let decisions = tx
            .query("SELECT to_jsonb(t) FROM public.review_decision t", &[])
            .map_err(db_error)?
            .iter()
            .map(|r| {
                serde_json::from_value::<ReviewDecision>(r.get(0))
                    .map(|d| (d.id.clone(), d))
                    .map_err(|_| KnowledgeError::InvalidShape("stored decision".into()))
            })
            .collect::<Result<_, _>>()?;
        let tasks = tx
            .query("SELECT to_jsonb(t) FROM public.acquisition_task t", &[])
            .map_err(db_error)?
            .iter()
            .map(|r| {
                serde_json::from_value::<AcquisitionTask>(r.get(0))
                    .map(|t| (t.id.clone(), t))
                    .map_err(|_| KnowledgeError::InvalidShape("stored task".into()))
            })
            .collect::<Result<_, _>>()?;
        let candidates = tx
            .query("SELECT id FROM knowledge.candidate", &[])
            .map_err(db_error)?
            .iter()
            .map(|r| r.get(0))
            .collect();
        tx.commit().map_err(db_error)?;
        Ok(Snapshot {
            abox,
            decisions,
            tasks,
            candidates,
        })
    }

    pub fn insert(&self, section: &str, value: &Value) -> Result<(), KnowledgeError> {
        let mut client = self.0.lock().map_err(|_| KnowledgeError::Immutable)?;
        let mut tx = client.transaction().map_err(db_error)?;
        insert_record(&mut tx, section, value)?;
        tx.commit().map_err(db_error)
    }

    /// Branching corrections and their conflict must commit together (deferred K10).
    pub fn insert_corrections(
        &self,
        assertions: &[Value],
        conflict: &Value,
    ) -> Result<(), KnowledgeError> {
        let mut client = self.0.lock().map_err(|_| KnowledgeError::Immutable)?;
        let mut tx = client.transaction().map_err(db_error)?;
        for assertion in assertions {
            insert_record(&mut tx, "assertions", assertion)?;
        }
        insert_record(&mut tx, "conflicts", conflict)?;
        tx.commit().map_err(db_error)
    }

    pub fn update_task(&self, id: &str, state: &str) -> Result<(), KnowledgeError> {
        let mut client = self.0.lock().map_err(|_| KnowledgeError::Immutable)?;
        let count = client
            .execute(
                "UPDATE public.acquisition_task SET state=$2, updated_at=now() WHERE id=$1",
                &[&id, &state],
            )
            .map_err(db_error)?;
        if count == 1 {
            Ok(())
        } else {
            Err(KnowledgeError::MissingTarget(id.to_owned()))
        }
    }

    pub fn promote(&self, id: &str, abox: &Abox) -> Result<(), KnowledgeError> {
        let members: BTreeMap<_, _> = abox
            .sections
            .iter()
            .map(|(s, rows)| (s, rows.iter().map(|r| &r["id"]).collect::<Vec<_>>()))
            .collect();
        let mut client = self.0.lock().map_err(|_| KnowledgeError::Immutable)?;
        client
            .execute(
                "INSERT INTO knowledge.candidate(id,members) VALUES($1,$2)",
                &[&id, &json!(members)],
            )
            .map_err(db_error)?;
        Ok(())
    }
}

fn insert_record(
    client: &mut impl GenericClient,
    section: &str,
    value: &Value,
) -> Result<(), KnowledgeError> {
    if section == "conflicts" {
        insert_columns(client, "public.conflict", value)?;
        for id in value["assertions"].as_array().unwrap() {
            client
                .execute(
                    "INSERT INTO public.conflict_member(conflict_id,assertion_id) VALUES($1,$2)",
                    &[&value["id"].as_str().unwrap(), &id.as_str().unwrap()],
                )
                .map_err(db_error)?;
        }
        client
            .execute(
                "INSERT INTO knowledge.record_extension(section,id,payload) VALUES($1,$2,$3)",
                &[&section, &value["id"].as_str().unwrap(), &value],
            )
            .map_err(db_error)?;
        return Ok(());
    }
    let table = match section {
        "review_decisions" => "public.review_decision",
        "acquisition_tasks" => "public.acquisition_task",
        "premium_observations"
            if value
                .get("conditions")
                .is_none_or(|v| v.is_null() || v == &json!({})) =>
        {
            "knowledge.raw_premium_observation"
        }
        _ => TABLES
            .iter()
            .find(|(s, _)| *s == section)
            .map(|(_, t)| *t)
            .ok_or_else(|| KnowledgeError::InvalidShape(section.into()))?,
    };
    insert_columns(client, table, &sql_shape(section, value))?;
    if !matches!(section, "review_decisions" | "acquisition_tasks") {
        client
            .execute(
                "INSERT INTO knowledge.record_extension(section,id,payload) VALUES($1,$2,$3)",
                &[&section, &value["id"].as_str().unwrap(), &value],
            )
            .map_err(db_error)?;
    }
    Ok(())
}

fn insert_columns(
    client: &mut impl GenericClient,
    table: &str,
    value: &Value,
) -> Result<(), KnowledgeError> {
    let columns: Vec<String> = client.query("SELECT attname::text FROM pg_attribute WHERE attrelid=$1::text::regclass AND attnum>0 AND NOT attisdropped AND attgenerated='' ORDER BY attnum", &[&table]).map_err(db_error)?
        .iter().map(|r| r.get::<_, String>(0)).filter(|c| value.get(c).is_some()).collect();
    if columns.is_empty() {
        return Err(KnowledgeError::MissingId);
    }
    let names = columns
        .iter()
        .map(|c| format!("\"{c}\""))
        .collect::<Vec<_>>()
        .join(",");
    client.execute(&format!("INSERT INTO {table} ({names}) SELECT {names} FROM jsonb_populate_record(NULL::{table}, $1)"), &[value]).map_err(db_error)?;
    Ok(())
}
