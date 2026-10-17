//! Golden: release freeze, r24/r25/r26 checks, scope relation and the 11 questions of
//! `tests/golden/reference_results.txt` (the reference checker's output, base release rel:case-r26).

mod common;
use common::*;
use onjeon_ontology::*;

#[test]
fn releases_reproduce_the_reference_hashes_and_integrity() {
    let a = abox();
    let reference = std::fs::read_to_string(golden_dir().join("reference_results.txt")).unwrap();
    for r in &a.releases {
        let v = release_view(&a, &r.id);
        assert!(v.integrity.is_empty(), "{}: {:?}", r.id, v.integrity);
        // the reference prints the first 16 hex digits of the content hash for each release
        let line = reference
            .lines()
            .find(|l| l.starts_with(&format!("- {}:", r.id)))
            .unwrap();
        assert!(
            line.contains(&format!("내용 해시 {} ", &r.freeze.content_sha256[..16])),
            "{line}"
        );
        // freezing the same members again gives the same hash
        let again = freeze(
            &a,
            &r.freeze.members,
            r.freeze.input_stage_edition.as_deref().unwrap(),
        )
        .unwrap();
        assert_eq!(again, r.freeze, "{}", r.id);
        // the counts of the reference line
        for (section, ids) in &r.freeze.members {
            if !ids.is_empty() {
                assert!(
                    line.contains(&format!("{section} {}", ids.len())),
                    "{line} / {section}"
                );
            }
        }
    }
}

#[test]
fn r24_has_exactly_one_k1_violation_and_r25_r26_none() {
    let a = abox();
    let vs24 = check(&release_view(&a, "rel:case-r24"));
    assert_eq!(vs24.len(), 1, "{vs24:?}");
    assert_eq!(vs24[0].code, "K1");
    assert_eq!(vs24[0].subject, "a:lotte_cond_waiting_v1");
    assert_eq!(
        vs24[0].message,
        "C0 accepted인데 약관 본문 판에 이어진 basis 근거가 없음"
    );
    assert!(check(&release_view(&a, "rel:case-r25")).is_empty());
    assert!(check(&release_view(&a, CURRENT)).is_empty());
}

#[test]
fn correction_history_is_reproduced_per_release() {
    let a = abox();
    let status = |rel: &str| {
        let v = release_view(&a, rel);
        let x = v
            .current()
            .find(|x| x.object.as_deref() == Some("cond:lotte_waiting"))
            .unwrap();
        (x.id.clone(), x.review_status.as_str())
    };
    assert_eq!(status("rel:case-r24").1, "accepted");
    assert_ne!(status("rel:case-r24").0, status("rel:case-r25").0);
    assert_ne!(status("rel:case-r25").1, "accepted");
}

#[test]
fn scope_relation_hana_vs_hyundai_is_narrower_and_needs_a_code_system() {
    let a = abox();
    let v = release_view(&a, CURRENT);
    let (h, hi) = (
        "cat:hana_cancer_x_breast_genital",
        "cat:hi_cancer_x_similar",
    );
    assert_eq!(
        scope_relation(&v, h, hi, Some(&fixture_universe())).unwrap(),
        ScopeRelation::Narrower
    );
    assert_eq!(
        scope_relation(&v, hi, h, Some(&fixture_universe())).unwrap(),
        ScopeRelation::Broader
    );
    assert_eq!(
        scope_relation(&v, h, h, Some(&fixture_universe())).unwrap(),
        ScopeRelation::SameScope
    );
    // without an official code system there is nothing to compute over
    assert_eq!(
        scope_relation(&v, h, hi, None).unwrap(),
        ScopeRelation::NotComparable
    );
}

#[test]
fn scope_relation_with_unknown_membership_is_not_comparable() {
    let a = abox();
    let v = release_view(&a, CURRENT);
    // the Lotte category is defined only by a held claim: its members are unknown
    let r = scope_relation(
        &v,
        "cat:lotte_general_cancer",
        "cat:hi_cancer_x_similar",
        Some(&fixture_universe()),
    )
    .unwrap();
    assert_eq!(r, ScopeRelation::NotComparable);
}

#[test]
fn the_eleven_questions_match_the_reference() {
    let a = abox();
    let v = release_view(&a, CURRENT);
    let qs = questions();
    assert_eq!(qs.len(), 11);
    for q in &qs {
        let ans = answer(&v, q);
        assert_eq!(ans.outcome, q.expect, "{}", q.id);
        assert_eq!(
            ans.engine_calls,
            usize::from(q.expect != Outcome::Blocked),
            "{}",
            q.id
        );
    }
}

#[test]
fn q1_explanation_reaches_page_and_file() {
    let a = abox();
    let v = release_view(&a, CURRENT);
    let ans = answer(&v, &question("Q1"));
    let text = ans.explanation.join("\n");
    assert!(
        text.contains(
            "C16 ∈ 암(유방암및생식기암제외) — 하나 2601 판의 포함 범위 ← 주장 a:hana_cat_inc"
        ),
        "{text}"
    );
    assert!(
        text.contains("PDF 52쪽") || text.contains("PDF 53쪽"),
        "{text}"
    );
    assert_eq!(ans.chain.linked().unwrap().edition, HANA_ED);
    assert_eq!(
        ans.chain.linked().unwrap().link_assertions,
        vec!["a:hana_doc_link"]
    );
}

#[test]
fn judgement_names_trail_and_code_sets() {
    let a = abox();
    let v = release_view(&a, CURRENT);
    let j = membership(
        &v,
        "cat:hana_cancer_x_breast_genital",
        "C44",
        Some("2027-04-20"),
    )
    .unwrap();
    assert_eq!(j.value, onjeon_contracts::Tri::False);
    assert!(j.code_system_refs.contains(&"codes:c44".to_string()));
    assert_eq!(j.judged_as_of.as_deref(), Some("2027-04-20"));
    assert!(membership(&v, "cat:hana_cancer_x_breast_genital", "not-a-code", None).is_err());
}
