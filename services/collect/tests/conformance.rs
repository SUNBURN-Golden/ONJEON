use onjeon_collect::{archive::*, digest::sha256_hex, keys, LocalStore, Store};
use onjeon_contracts::{AcquisitionStatus, DocRole};
use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Fixture(LocalStore);
impl Fixture {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "collect-fixture-only-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir_all(&path).unwrap();
        Self(LocalStore::new(path))
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0.root).unwrap();
    }
}
fn observation() -> Observation {
    Observation {
        source_id: "fixture_only".into(),
        url: "https://example.org/fixture_only".into(),
        observed_at: "2026-10-09T04:43:40Z".into(),
        doc_role: DocRole::Terms,
        format: Some("json".into()),
        extra: BTreeMap::from([("origin".into(), "fixture".into())]),
    }
}

#[test]
fn python_put_once_same_and_different_bytes() {
    let f = Fixture::new();
    assert_eq!(
        put_once(&f.0, "k", b"old", "text/plain").unwrap(),
        PutOutcome::Stored
    );
    assert_eq!(
        put_once(&f.0, "k", b"old", "text/plain").unwrap(),
        PutOutcome::AlreadyPresent
    );
    assert!(matches!(
        put_once(&f.0, "k", b"changed", "text/plain"),
        Err(ArchiveError::Conflict(_))
    ));
    assert_eq!(f.0.get("k").unwrap(), b"old");
}

#[test]
fn python_raw_hash_layout_idempotence_and_corruption() {
    let f = Fixture::new();
    let (digest, _) = put_raw(&f.0, b"fixture_only", "text/plain").unwrap();
    assert_eq!(digest, sha256_hex(b"fixture_only"));
    assert_eq!(
        keys::object_key(&digest),
        format!(
            "objects/sha256/{}/{}/{}",
            &digest[..2],
            &digest[2..4],
            digest
        )
    );
    assert_eq!(
        put_raw(&f.0, b"fixture_only", "text/plain").unwrap().1,
        PutOutcome::AlreadyPresent
    );
    std::fs::write(
        f.0.root.join(keys::object_key(&digest)),
        b"corrupt fixture_only",
    )
    .unwrap();
    assert!(put_raw(&f.0, b"fixture_only", "text/plain").is_err());
}

#[test]
fn observations_preserve_url_changes_provenance_and_all_roles() {
    let f = Fixture::new();
    let mut obs = observation();
    for role in [
        DocRole::Terms,
        DocRole::RiderTerms,
        DocRole::Annex,
        DocRole::BusinessMethod,
        DocRole::Summary,
        DocRole::PriceTable,
    ] {
        obs.doc_role = role;
        let body =
            serde_json::to_vec(&serde_json::json!({"origin":"fixture", "role":role})).unwrap();
        let (digest, _, key, _) = observe(&f.0, &obs, &body, "application/json").unwrap();
        assert_eq!(
            observe(&f.0, &obs, &body, "application/json").unwrap().3,
            PutOutcome::AlreadyPresent
        );
        let record: serde_json::Value = serde_json::from_slice(&f.0.get(&key).unwrap()).unwrap();
        assert_eq!(record["object_key"], keys::object_key(&digest));
        assert_eq!(record["doc_role"], role.as_str());
        assert_eq!(record["url"], obs.url);
        assert_eq!(record["observed_at"], obs.observed_at);
        assert_eq!(f.0.get(&keys::object_key(&digest)).unwrap(), body);
    }
    assert_eq!(f.0.list("objects").unwrap().len(), 6);
    assert_eq!(f.0.list("observations").unwrap().len(), 6);
}

#[test]
fn python_observation_conflict_and_reserved_metadata_refusal() {
    let f = Fixture::new();
    let mut obs = observation();
    let (_, _, key, _) = observe(&f.0, &obs, b"{}", "application/json").unwrap();
    let before = f.0.get(&key).unwrap();
    obs.extra
        .insert("note".into(), "changed fixture_only".into());
    assert!(matches!(
        observe(&f.0, &obs, b"{}", "application/json"),
        Err(ArchiveError::Conflict(_))
    ));
    assert_eq!(f.0.get(&key).unwrap(), before);
    obs.extra.insert("object_key".into(), "wrong".into());
    assert!(observe(&f.0, &obs, b"{}", "application/json").is_err());
}

#[test]
fn invalid_responses_are_only_quarantined() {
    for (format, content_type, body) in [
        ("pdf", "text/html", b"<html>fixture_only</html>".as_slice()),
        ("json", "application/json", b"bad fixture_only"),
        ("pdf", "application/pdf", b""),
    ] {
        let f = Fixture::new();
        let mut obs = observation();
        obs.format = Some(format.into());
        assert!(observe(&f.0, &obs, body, content_type).is_err());
        assert!(f.0.list("objects").unwrap().is_empty());
        assert!(f.0.list("observations").unwrap().is_empty());
        assert_eq!(f.0.list("quarantine").unwrap().len(), 2);
    }
}

#[test]
fn missing_documents_have_separate_reason_records() {
    let f = Fixture::new();
    let mut record = UnacquiredRecord {
        source_id: "fixture_only".into(),
        url: Some(observation().url),
        doc_role: Some(DocRole::Terms),
        observed_at: observation().observed_at,
        status: AcquisitionStatus::Blocked,
        reason: "fixture_only blocked evidence".into(),
    };
    for status in [
        AcquisitionStatus::Blocked,
        AcquisitionStatus::Failed,
        AcquisitionStatus::NotFound,
        AcquisitionStatus::NotDisclosed,
    ] {
        record.status = status;
        let (key, _) = record_unacquired(&f.0, &record).unwrap();
        let json: serde_json::Value = serde_json::from_slice(&f.0.get(&key).unwrap()).unwrap();
        assert_eq!(json["status"], status.as_str());
        assert_eq!(json["reason"], record.reason);
    }
    for status in [AcquisitionStatus::Archived, AcquisitionStatus::Unqueried] {
        record.status = status;
        assert!(record_unacquired(&f.0, &record).is_err());
    }
    record.status = AcquisitionStatus::Failed;
    record.reason.clear();
    assert!(record_unacquired(&f.0, &record).is_err());
    assert!(f.0.list("observations").unwrap().is_empty());
}

#[test]
fn python_copy_conflict_and_verify_all_outcomes() {
    let src = Fixture::new();
    let dst = Fixture::new();
    put_once(&src.0, "k", b"fixture_only", "text/plain").unwrap();
    let listing = Listing::from_store(&src.0).unwrap();
    assert_eq!(Listing::parse(&listing.to_bytes()).unwrap(), listing);
    assert_eq!(
        verify_copy(&listing, "fixture_only", &dst.0, false)
            .unwrap()
            .results[0]
            .status,
        VerifyStatus::Missing
    );
    copy(&src.0, &dst.0).unwrap();
    assert!(verify_copy(&listing, "fixture_only", &dst.0, false)
        .unwrap()
        .passed(false));
    put_once(&dst.0, "extra", b"fixture_only", "text/plain").unwrap();
    let report = verify_copy(&listing, "fixture_only", &dst.0, false).unwrap();
    assert!(!report.passed(false));
    assert!(report.passed(true));
    std::fs::write(dst.0.root.join("k"), b"changed fixture_only").unwrap();
    assert!(matches!(
        copy(&src.0, &dst.0),
        Err(ArchiveError::Conflict(_))
    ));
    assert_eq!(
        verify_copy(&listing, "fixture_only", &dst.0, false)
            .unwrap()
            .results[0]
            .status,
        VerifyStatus::HashMismatch
    );
    assert!(!verify_copy(
        &Listing {
            objects: BTreeMap::new()
        },
        "fixture_only",
        &src.0,
        true
    )
    .unwrap()
    .passed(true));
}

#[test]
fn invalid_listings_do_not_silently_drop_entries() {
    for value in [
        serde_json::json!({"listing_rule":"key-sha256-v1","keys":1,"objects":{"k":12}}),
        serde_json::json!({"listing_rule":"key-sha256-v1","keys":1,"objects":{}}),
        serde_json::json!({"listing_rule":"key-sha256-v1","keys":1,"objects":{"k":"short"}}),
    ] {
        assert!(Listing::parse(&serde_json::to_vec(&value).unwrap()).is_err());
    }
}

#[test]
fn concurrent_writers_never_replace_the_winner() {
    let f = Fixture::new();
    std::thread::scope(|s| {
        let handles: Vec<_> = (0..12)
            .map(|i| {
                let st = &f.0;
                s.spawn(move || put_once(st, "race", &[i], "application/octet-stream"))
            })
            .collect();
        let outcomes: Vec<_> = handles.into_iter().map(|h| h.join().unwrap()).collect();
        assert_eq!(
            outcomes
                .iter()
                .filter(|r| matches!(r, Ok(PutOutcome::Stored)))
                .count(),
            1
        );
        assert_eq!(
            outcomes
                .iter()
                .filter(|r| matches!(r, Err(ArchiveError::Conflict(_))))
                .count(),
            11
        );
    });
    assert_eq!(f.0.list("").unwrap(), vec!["race"]);
}

#[cfg(unix)]
#[test]
fn python_symlink_escape_is_refused_for_reads_writes_and_listing() {
    let f = Fixture::new();
    let outside = Fixture::new();
    std::os::unix::fs::symlink(&outside.0.root, f.0.root.join("escape")).unwrap();
    assert!(f.0.get("escape/k").is_err());
    assert!(put_once(&f.0, "escape/k", b"fixture_only", "text/plain").is_err());
    assert!(f.0.list("").is_err());
    assert!(outside.0.list("").unwrap().is_empty());
}
