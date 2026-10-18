//! Document model: identity of terms editions (golden D1~D9). Fingerprints are evidence; only a review decision
//! makes two texts the same edition.

mod common;
use common::*;
use onjeon_ontology::*;
use serde_json::json;
use std::collections::BTreeSet;

fn q1_base() -> Outcome {
    answer(&release_view(&abox(), CURRENT), &question("Q1")).outcome
}

fn raws_realizing(v: &View, ed: &str) -> BTreeSet<String> {
    v.current()
        .filter(|a| a.predicate == "realizes" && a.object.as_deref() == Some(ed))
        .map(|a| v.segment(&a.subject).unwrap().raw_asset.clone().unwrap())
        .collect()
}

fn k16_messages(vs: &[Violation]) -> Vec<&str> {
    vs.iter().map(|v| v.message.as_str()).collect()
}

/// test id: edition-repack-same (golden D1)
#[test]
fn edition_repack_same() {
    let mut a = abox();
    repack(&mut a, "repack", None);
    let v = candidate_view(&a).unwrap();
    assert!(check(&v).is_empty());
    assert_eq!(raws_realizing(&v, HANA_ED).len(), 2);
    assert_eq!(
        edition_status(&v, HANA_ED).unwrap().state,
        EditionState::Confirmed
    );
    assert_eq!(answer(&v, &question("Q1")).outcome, q1_base());
}

#[test]
fn d2_raw_hash_alone_cannot_realize_an_edition() {
    let mut a = abox();
    push(
        &mut a,
        "assertions",
        json!({"id": "a:realizes_by_hash", "subject": "seg:hana_annex12", "predicate": "realizes", "object": "ted:hi_r2_5@2608",
        "criticality": "C0", "evidence": [{"ref": "raw:hana_fd9c0133", "role": "observation"}], "value_state": "observed",
        "review_status": "accepted", "origin": "fixture", "decision": {"by": "fixture_assumption"}}),
    );
    let vs = check_candidate(&a);
    assert!(
        vs.iter()
            .any(|v| v.code == "K14" && v.message == "구획 관측 근거 없이 본문 판을 확정"),
        "{vs:?}"
    );
}

/// test id: edition-not-auto-by-fingerprint (golden D3)
#[test]
fn edition_not_auto_by_fingerprint() {
    let mut a = abox();
    repack(&mut a, "auto", None);
    for x in a.section_mut("assertions") {
        if x["id"]
            .as_str()
            .unwrap()
            .starts_with("a:realizes_synthetic_auto")
        {
            x["decision"] = json!({"by": "fingerprint_match"});
        }
    }
    let vs = check_candidate(&a);
    assert_eq!(vs.len(), 3, "{vs:?}");
    assert!(
        vs.iter()
            .all(|v| v.code == "K14"
                && v.message == "승인 결정이 검수 결정이 아님(fingerprint_match)")
    );
    // a hash match is no decision either, and neither is a missing decision
    for by in [json!({"by": "hash_match"}), json!(null)] {
        let mut b = abox();
        set(
            &mut b,
            "assertions",
            "a:realizes_hana_annex1",
            "decision",
            by,
        );
        assert_eq!(codes(&check_candidate(&b)), ["K14"]);
    }
    // the identity itself stays with the review: a differing text is not "different edition" by code either
    let st = edition_status(&candidate_view(&a).unwrap(), HANA_ED).unwrap();
    assert_eq!(
        st.state,
        EditionState::IdentityUnconfirmed,
        "a fingerprint-only approval never confirms an edition (K14 flags it, the input stage blocks)"
    );
    let ans = answer(&candidate_view(&a).unwrap(), &question("Q1"));
    assert_eq!(ans.engine_calls, 0);
    assert_eq!(
        ans.chain.blocked().map(|b| b.reason),
        Some(BlockReason::EditionIdentityUnconfirmed)
    );
}

/// test id: edition-composition-annex (golden D4, D5, D8)
#[test]
fn edition_composition_annex() {
    let a = abox();
    let v = release_view(&a, CURRENT);
    let ed = v.editions.iter().find(|e| e.id == HANA_ED).unwrap();
    // composition = body + referenced annexes, each with a role and a fingerprint
    assert_eq!(ed.parts.len(), 3);
    assert_eq!(ed.parts.iter().filter(|p| p.role == "본문").count(), 1);
    assert_eq!(ed.parts.iter().filter(|p| p.role == "참조 별표").count(), 2);
    let st = edition_status(&v, HANA_ED).unwrap();
    assert_eq!(st.state, EditionState::Confirmed);
    assert_eq!(
        st.accepted_realizes.len(),
        3,
        "bundle = all accepted realizes"
    );
    assert!(st.missing_parts.is_empty() && st.mismatch.is_empty());

    // body fingerprint alone does not make the same edition: a raw file holding only the body covers 1 of 3 parts
    let mut b = abox();
    for id in ["a:realizes_hana_annex1", "a:realizes_hana_annex12"] {
        b.section_mut("assertions").retain(|x| x["id"] != id);
    }
    let vb = candidate_view(&b).unwrap();
    let st = edition_status(&vb, HANA_ED).unwrap();
    assert_eq!(st.state, EditionState::IdentityUnconfirmed);
    assert_eq!(st.missing_parts.len(), 2);
    assert!(st.missing_parts.iter().all(|p| p.role == "참조 별표"));
    assert!(check(&vb)
        .iter()
        .any(|v| v.code == "K16" && v.subject == HANA_ED));
}

/// test id: edition-bundle-split-files (golden D5, review R01 reproduction)
#[test]
fn edition_bundle_split_files() {
    let mut a = abox();
    push(
        &mut a,
        "raw_assets",
        raw_asset(
            "raw:annex_only",
            "자체 시험용 별표 분리 파일",
            &"9".repeat(64),
        ),
    );
    set(
        &mut a,
        "segments",
        "seg:hana_annex12",
        "raw_asset",
        json!("raw:annex_only"),
    );
    let v = candidate_view(&a).unwrap();
    assert_eq!(
        raws_realizing(&v, HANA_ED).len(),
        2,
        "body and annex 12 now live in different raw files"
    );
    assert!(check(&v).is_empty(), "{:?}", check(&v));
    assert_eq!(
        edition_status(&v, HANA_ED).unwrap().state,
        EditionState::Confirmed
    );
    assert_eq!(answer(&v, &question("Q1")).outcome, q1_base());
}

/// test id: edition-annex-missing-unconfirmed (golden D8)
#[test]
fn edition_annex_missing_unconfirmed() {
    let mut a = abox();
    a.section_mut("assertions")
        .retain(|x| x["id"] != "a:realizes_hana_annex1");
    let vs = check_candidate(&a);
    assert!(
        vs.iter()
            .any(|v| v.code == "K16" && v.message.contains("동일성 미확인")),
        "{vs:?}"
    );
    let st = edition_status(&candidate_view(&a).unwrap(), HANA_ED).unwrap();
    assert_eq!(st.state, EditionState::IdentityUnconfirmed);
    assert_eq!(st.missing_parts.len(), 1);

    // as hold: no violation, the input stage blocks and the engine is never called
    for x in a.section_mut("assertions") {
        if x["predicate"] == "realizes" && x["object"] == HANA_ED {
            x["review_status"] = json!("hold");
            x["hold_reason"] = json!("reference_unresolved");
        }
    }
    let v = candidate_view(&a).unwrap();
    // no identity violation (K14/K16); the C0 claims that lost their terms basis are K1's business
    let vs = check(&v);
    assert!(vs.iter().all(|x| x.code == "K1"), "{vs:?}");
    assert_eq!(
        edition_status(&v, HANA_ED).unwrap().state,
        EditionState::IdentityUnconfirmed
    );
    let ans = answer(&v, &question("Q1"));
    assert_eq!(
        ans.chain.blocked().unwrap().reason,
        BlockReason::EditionIdentityUnconfirmed
    );
    assert_eq!(
        ans.chain.blocked().unwrap().held,
        [format!("{HANA_ED}:identity_unconfirmed")]
    );
    assert_eq!(ans.engine_calls, 0);
}

/// test id: edition-ocr-normalization (golden D9)
#[test]
fn edition_ocr_normalization() {
    let mut a = abox();
    let mut seg = get(&a, "segments", "seg:hana_annex1");
    seg["id"] = json!("seg:synthetic_ocr_annex1");
    seg["raw_asset"] = json!("raw:hana_fd9c0133");
    seg["fingerprint"] = json!({"rule": "fp-ocr-0.1", "sha256": "7".repeat(64)});
    push(&mut a, "segments", seg);
    push(
        &mut a,
        "assertions",
        realizes("seg:synthetic_ocr_annex1", HANA_ED, "fixture_assumption"),
    );

    let v = candidate_view(&a).unwrap();
    let st = edition_status(&v, HANA_ED).unwrap();
    assert_eq!(st.state, EditionState::IdentityUnconfirmed);
    assert_eq!(st.mismatch.len(), 1);
    assert_eq!(st.mismatch[0].kind, MismatchKind::NotComparable);
    assert_eq!(st.mismatch[0].part.as_ref().unwrap().rule, "fp-ocr-0.1");
    let vs = check(&v);
    assert_eq!(codes(&vs), ["K16"]);
    assert!(vs[0].message.contains("비교 불가"), "{vs:?}");

    // a review decision naming [rule, fingerprint] of the part it covers makes it the same
    let ed = v.editions.iter().find(|e| e.id == HANA_ED).unwrap();
    let p1 = ed
        .parts
        .iter()
        .find(|p| p.fingerprint.sha256.starts_with("f3e220"))
        .unwrap();
    set(
        &mut a,
        "assertions",
        "a:realizes_synthetic_ocr_annex1",
        "decision",
        json!({"by": "review_decision", "covers": [p1.fingerprint.rule, p1.fingerprint.sha256], "note": "자체 시험: 검수 결정"}),
    );
    let v = candidate_view(&a).unwrap();
    assert!(check(&v).is_empty(), "{:?}", check(&v));
    assert_eq!(
        edition_status(&v, HANA_ED).unwrap().state,
        EditionState::Confirmed
    );

    // `covers` without a review decision (fixture assumption) does not count
    set(
        &mut a,
        "assertions",
        "a:realizes_synthetic_ocr_annex1",
        "decision",
        json!({"by": "fixture_assumption", "covers": [p1.fingerprint.rule, p1.fingerprint.sha256]}),
    );
    assert_eq!(codes(&check_candidate(&a)), ["K16"]);
}

/// test id: edition-annex-content-changed (golden D4)
#[test]
fn edition_annex_content_changed() {
    let mut a = abox();
    repack(&mut a, "annexdiff", Some("seg:hana_annex12"));
    let v = candidate_view(&a).unwrap();
    let st = edition_status(&v, HANA_ED).unwrap();
    assert_eq!(st.state, EditionState::IdentityUnconfirmed);
    assert_eq!(st.mismatch.len(), 1);
    assert_eq!(
        st.mismatch[0].kind,
        MismatchKind::ContentDifferenceCandidate
    );
    let vs = check(&v);
    assert_eq!(codes(&vs), ["K16"]);
    assert!(
        vs[0].message.contains("내용 차이 후보"),
        "{:?}",
        k16_messages(&vs)
    );
    assert!(vs[0]
        .message
        .ends_with("검수 결정 없이 같은 판으로 승인할 수 없음"));

    // the review decision for "different edition" is a new TermsEdition + realizes, not a code verdict
    let base_ed = get(&a, "terms_editions", HANA_ED);
    let mut parts = base_ed["parts"].clone();
    parts[2]["fingerprint"] = json!({"rule": "fp-0.1", "sha256": "f".repeat(64)});
    push(
        &mut a,
        "terms_editions",
        with(
            &base_ed,
            &[("id", json!("ted:hana_r2_1@annexdiff")), ("parts", parts)],
        ),
    );
    for x in a.section_mut("assertions") {
        if x["id"]
            .as_str()
            .unwrap()
            .starts_with("a:realizes_synthetic_annexdiff")
        {
            x["object"] = json!("ted:hana_r2_1@annexdiff");
        }
    }
    let v = candidate_view(&a).unwrap();
    assert!(check(&v).is_empty(), "{:?}", check(&v));
    assert_eq!(
        edition_status(&v, "ted:hana_r2_1@annexdiff").unwrap().state,
        EditionState::Confirmed
    );
    assert_eq!(
        edition_status(&v, HANA_ED).unwrap().state,
        EditionState::Confirmed
    );
}

/// test id: edition-integrated-vs-separate-file (golden D6)
#[test]
fn edition_integrated_vs_separate_file() {
    let mut a = abox();
    repack(&mut a, "separate", None);
    push(
        &mut a,
        "raw_assets",
        raw_asset(
            "raw:synthetic_integrated",
            "자체 시험용 합성 통합약관",
            &"1".repeat(64),
        ),
    );
    for (k, sid) in ["seg:hana_r2_1", "seg:hana_annex1", "seg:hana_annex12"]
        .iter()
        .enumerate()
    {
        let id = format!("seg:synthetic_integrated_{k}");
        let seg = with(
            &get(&a, "segments", sid),
            &[
                ("id", json!(id)),
                ("raw_asset", json!("raw:synthetic_integrated")),
                ("pages", json!([400 + k, 400 + k])),
            ],
        );
        push(&mut a, "segments", seg);
        push(
            &mut a,
            "assertions",
            realizes(&id, HANA_ED, "fixture_assumption"),
        );
    }
    // another rider inside the same integrated file: a segment with its own fingerprint, tied to no edition
    let other = with(
        &get(&a, "segments", "seg:hana_r2_1"),
        &[
            ("id", json!("seg:synthetic_integrated_other")),
            ("raw_asset", json!("raw:synthetic_integrated")),
            ("pages", json!([10, 11])),
            (
                "fingerprint",
                json!({"rule": "fp-0.1", "sha256": "2".repeat(64)}),
            ),
        ],
    );
    push(&mut a, "segments", other);
    let v = candidate_view(&a).unwrap();
    assert!(check(&v).is_empty(), "{:?}", check(&v));
    assert_eq!(
        raws_realizing(&v, HANA_ED).len(),
        3,
        "original, separate rider file, integrated terms"
    );
    assert_eq!(
        edition_status(&v, HANA_ED).unwrap().state,
        EditionState::Confirmed
    );
    // same role and same period are no reason for a Conflict
    assert!(v.conflicts.is_empty());
    assert_eq!(answer(&v, &question("Q1")).outcome, q1_base());
}

/// test id: edition-one-rider-revised-in-integrated (golden D7)
#[test]
fn edition_one_rider_revised_in_integrated() {
    let mut a = abox();
    push(
        &mut a,
        "raw_assets",
        raw_asset(
            "raw:synthetic_rev",
            "자체 시험용 합성 개정 통합약관",
            &"3".repeat(64),
        ),
    );
    let mut new_parts = Vec::new();
    for (k, sid) in ["seg:hana_r2_1", "seg:hana_annex1", "seg:hana_annex12"]
        .iter()
        .enumerate()
    {
        let mut sg = with(
            &get(&a, "segments", sid),
            &[
                ("id", json!(format!("seg:synthetic_rev_{k}"))),
                ("raw_asset", json!("raw:synthetic_rev")),
                ("pages", json!([50 + k, 50 + k])),
            ],
        );
        if k == 0 {
            sg["fingerprint"] = json!({"rule": "fp-0.1", "sha256": "4".repeat(64)});
            // body revised
        }
        new_parts.push(json!({"role": if k == 0 { "본문" } else { "참조 별표" }, "label": sg["doc_role"], "fingerprint": sg["fingerprint"]}));
        push(&mut a, "segments", sg);
    }
    // tying the revised body to the old edition is a K16 violation
    let mut wrong = a.clone();
    for k in 0..3 {
        push(
            &mut wrong,
            "assertions",
            realizes(
                &format!("seg:synthetic_rev_{k}"),
                HANA_ED,
                "fixture_assumption",
            ),
        );
    }
    let vs = check_candidate(&wrong);
    assert!(vs.iter().any(|v| v.code == "K16"), "{vs:?}");

    // the review decision "new edition of the same lineage" = new TermsEdition + realizes
    let ed0 = get(&a, "terms_editions", HANA_ED);
    push(
        &mut a,
        "terms_editions",
        with(
            &ed0,
            &[
                ("id", json!("ted:hana_r2_1@rev")),
                ("parts", json!(new_parts)),
                ("label", json!("자체 시험용 개정 판")),
            ],
        ),
    );
    for k in 0..3 {
        push(
            &mut a,
            "assertions",
            realizes(
                &format!("seg:synthetic_rev_{k}"),
                "ted:hana_r2_1@rev",
                "fixture_assumption",
            ),
        );
    }
    let v = candidate_view(&a).unwrap();
    assert!(check(&v).is_empty(), "{:?}", check(&v));
    let lineage = |id: &str| {
        v.editions
            .iter()
            .find(|e| e.id == id)
            .unwrap()
            .lineage
            .clone()
    };
    assert_eq!(lineage("ted:hana_r2_1@rev"), lineage(HANA_ED));
    assert!(lineage(HANA_ED).is_some());
    assert_eq!(
        edition_status(&v, "ted:hana_r2_1@rev").unwrap().state,
        EditionState::Confirmed
    );
    assert_eq!(
        edition_status(&v, HANA_ED).unwrap().state,
        EditionState::Confirmed,
        "the other edition is untouched"
    );
    // the frozen release does not change
    assert_eq!(
        answer_all(&release_view(&abox(), CURRENT)),
        answer_all(&release_view(&a, CURRENT))
    );
}

#[test]
fn unknown_edition_is_an_error_and_unconfirmed_when_resolving() {
    let v = release_view(&abox(), CURRENT);
    assert!(edition_status(&v, "ted:nope").is_err());
    assert_eq!(edition_statuses(&v).len(), 2);
}
