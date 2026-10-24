//! `config_select`: the sales configuration applicable on the contract date — sorted,
//! order-independent, ambiguity only when several configurations apply.

mod common;
use common::*;
use onjeon_twin_runtime::*;
use serde_json::json;

#[test]
fn selects_the_configuration_in_force_on_the_contract_date() {
    let snap = release_snapshot();
    // Q1: both Hana configurations are candidates; only v20260701 is in force on 08-20
    match config_select(&snap, &[HANA_NEW, HANA_OLD], "2026-08-20") {
        ConfigSelection::Selected {
            sales_config,
            link_assertions,
        } => {
            assert_eq!(sales_config, HANA_NEW);
            assert_eq!(link_assertions, ["a:hana_doc_link"]);
        }
        other => panic!("expected selected, got {other:?}"),
    }
    // on 2026-03-15 only the old configuration applies (its link is held + object-less)
    match config_select(&snap, &[HANA_NEW, HANA_OLD], "2026-03-15") {
        ConfigSelection::Selected { sales_config, .. } => assert_eq!(sales_config, HANA_OLD),
        other => panic!("expected selected, got {other:?}"),
    }
}

#[test]
fn candidate_order_and_duplicates_change_nothing() {
    let snap = release_snapshot();
    let fwd = config_select(&snap, &[HANA_NEW, HANA_OLD], "2026-08-20");
    let rev = config_select(&snap, &[HANA_OLD, HANA_NEW, HANA_NEW], "2026-08-20");
    assert_eq!(fwd, rev);
}

#[test]
fn several_applicable_configurations_block() {
    let mut a = abox();
    push(
        &mut a,
        "nodes",
        json!({"id": "sc:synthetic_overlap", "class": "SalesConfiguration", "label": "자체 시험용 겹치는 판매 구성"}),
    );
    let hl = get(&a, "assertions", "a:hana_doc_link");
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:synthetic_overlap_link")),
                ("subject", json!("sc:synthetic_overlap")),
            ],
        ),
    );
    let snap = candidate_snapshot(&a);
    match config_select(&snap, &[HANA_NEW, "sc:synthetic_overlap"], "2026-08-20") {
        ConfigSelection::Blocked(ConfigBlock::MultipleCandidates { candidates, held }) => {
            assert_eq!(
                candidates,
                ["sc:hana_2601_3d_v20260701", "sc:synthetic_overlap"]
            );
            // each competing link is reported with its review status
            assert_eq!(held.len(), 2);
            assert!(held
                .iter()
                .all(|h| h.applies_on_date && h.status == "accepted"));
        }
        other => panic!("expected multiple_candidates, got {other:?}"),
    }
}

#[test]
fn one_configuration_using_several_editions_is_not_ambiguous() {
    // S01: a configuration linked to 보통약관 + 특약 editions stays a single selection.
    let mut a = abox();
    let hl = get(&a, "assertions", "a:hana_doc_link");
    let ed = get(&a, "terms_editions", HANA_ED);
    push(
        &mut a,
        "terms_editions",
        with(
            &ed,
            &[
                ("id", json!("ted:synthetic_main@2607")),
                ("parts", json!([])),
            ],
        ),
    );
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:synthetic_main_link")),
                ("object", json!("ted:synthetic_main@2607")),
            ],
        ),
    );
    let snap = candidate_snapshot(&a);
    match config_select(&snap, &[HANA_NEW], "2026-08-20") {
        ConfigSelection::Selected {
            sales_config,
            link_assertions,
        } => {
            assert_eq!(sales_config, HANA_NEW);
            assert_eq!(
                link_assertions,
                ["a:hana_doc_link", "a:synthetic_main_link"]
            );
        }
        other => panic!("expected selected, got {other:?}"),
    }
}

#[test]
fn no_applicable_configuration_reports_the_considered_links() {
    let snap = release_snapshot();
    // no link of either candidate covers the contract date
    match config_select(&snap, &[HANA_NEW, HANA_OLD], "2020-01-01") {
        ConfigSelection::Blocked(ConfigBlock::NoApplicableConfig { held }) => {
            assert_eq!(held.len(), 2);
            assert!(held.iter().all(|h| !h.applies_on_date));
            // sorted by (sales_config, assertion_id): v20260101 before v20260701
            assert_eq!(held[0].assertion_id, "a:hana_old_doc_link");
            assert_eq!(held[1].assertion_id, "a:hana_doc_link");
        }
        other => panic!("expected no_applicable_config, got {other:?}"),
    }
    // and the request maps to no_uses_edition with zero engine calls
    let mut q = question("Q1");
    q.contract_date = "2020-01-01";
    let out = run(&snap, &q);
    assert_eq!(blocked(&out).reason, BlockReason::NoUsesEdition);
}

#[test]
fn a_configuration_without_any_link_blocks() {
    let snap = release_snapshot();
    match config_select(&snap, &["sc:no_such_config"], "2026-08-20") {
        ConfigSelection::Blocked(ConfigBlock::NoApplicableConfig { held }) => {
            assert!(held.is_empty())
        }
        other => panic!("expected no_applicable_config, got {other:?}"),
    }
}
