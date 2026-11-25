use super::*;

fn assert_violation(violations: Vec<Violation>, rule: &str) {
    assert!(
        violations.iter().any(|violation| violation.rule == rule),
        "expected {rule}, got {violations:?}"
    );
}

#[test]
fn view_and_snapshot_fixtures_pass_the_contract_checks() {
    macro_rules! check_fixture {
        ($name:literal, $check:ident) => {
            assert_eq!(
                $check(&serde_json::from_str(fixture!($name)).unwrap()),
                vec![],
                $name
            );
        };
    }
    check_fixture!("PlanView", check_plan_view);
    check_fixture!("CoverageDetail", check_coverage_detail);
    check_fixture!("CompareView", check_compare_view);
    check_fixture!("EvidenceView", check_evidence_view);
    check_fixture!("NeedResult", check_need_result);
    check_fixture!("ReleaseManifest", check_release_manifest);
    check_fixture!("ContractSnapshot", check_contract_snapshot);
}

#[test]
fn every_diff_type_must_use_its_vocabulary_group() {
    let vocabulary: Value = serde_json::from_str(include_str!("../vocabulary.json")).unwrap();
    let diff_types = vocabulary["axes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|axis| axis["id"] == "diff_type")
        .unwrap()["values"]
        .as_array()
        .unwrap();
    let mut plan: PlanView = serde_json::from_str(fixture!("PlanView")).unwrap();
    for entry in diff_types {
        let diff_type = serde_json::from_value(entry["code"].clone()).unwrap();
        let expected: DiffGroup = serde_json::from_value(entry["group"].clone()).unwrap();
        for &group in DiffGroup::ALL {
            let group_under_test = &mut plan.diff.as_mut().unwrap().groups[0];
            group_under_test.group = group;
            group_under_test.items[0].diff_type = diff_type;
            let violations = check_plan_view(&plan);
            if group == expected {
                assert!(violations.is_empty(), "{diff_type:?}: {violations:?}");
            } else {
                assert_eq!(violations.len(), 1, "{diff_type:?} in {group:?}");
                assert_violation(violations, "plan_diff_type_matches_group");
            }
        }
    }
}

#[test]
fn plan_checks_diff_availability_duplicate_groups_and_diff_amounts() {
    let mut plan: PlanView = serde_json::from_str(fixture!("PlanView")).unwrap();
    plan.diff_available = false;
    assert_violation(check_plan_view(&plan), "plan_diff_is_available");
    plan.diff_available = true;
    let diff = plan.diff.as_mut().unwrap();
    diff.groups.push(diff.groups[0].clone());
    assert_violation(check_plan_view(&plan), "plan_diff_group_unique");
    let diff = plan.diff.as_mut().unwrap();
    diff.groups.pop();
    diff.groups[0].items[0].amounts[0].source = "scenario:".into();
    assert_violation(check_plan_view(&plan), "plan_diff_amount_has_source");
    plan.diff = None;
    assert!(check_plan_view(&plan).is_empty()); // Comparison is available via the separate action.
    plan.diff_available = false;
    assert!(check_plan_view(&plan).is_empty());
}

#[test]
fn plan_checks_displayed_and_unavailable_prices() {
    let plan: PlanView = serde_json::from_str(fixture!("PlanView")).unwrap();
    let price = &plan.groups[0].price_line;
    let mut missing_reason = plan.clone();
    missing_reason.groups[1].price_line.price_unavailable_reason = None;
    assert_violation(
        check_plan_view(&missing_reason),
        "plan_price_has_basis_or_unavailable_reason",
    );

    let mut price_with_no_basis = price.clone();
    price_with_no_basis.basis = None;
    let mut price_with_bad_date = price.clone();
    price_with_bad_date.as_of = Some("2026-02-29".into());
    let mut price_with_unavailable_reason = price.clone();
    price_with_unavailable_reason.price_unavailable_reason =
        plan.groups[1].price_line.price_unavailable_reason;
    for invalid in [
        price_with_no_basis,
        price_with_bad_date,
        price_with_unavailable_reason,
    ]
    .into_iter()
    .chain(
        [
            vec![],
            vec![3.0, 2.0],
            vec![1.0, 2.0, 3.0],
            vec![-1.0],
            vec![f64::INFINITY],
        ]
        .into_iter()
        .map(|values| PriceLine {
            man: Some(values),
            ..price.clone()
        }),
    ) {
        let mut plan = plan.clone();
        plan.groups[0].price_line = invalid;
        assert_violation(
            check_plan_view(&plan),
            "plan_price_has_basis_or_unavailable_reason",
        );
    }
    let mut exact_zero = plan.clone();
    exact_zero.groups[0].price_line.man = Some(vec![0.0]);
    assert!(check_plan_view(&exact_zero).is_empty());
}

#[test]
fn plan_checks_nested_reasons_and_unresolved_references() {
    let mut plan: PlanView = serde_json::from_str(fixture!("PlanView")).unwrap();
    plan.groups[0].need.as_mut().unwrap().reasons[0]
        .assertion_refs
        .clear();
    assert_violation(check_plan_view(&plan), "need_reason_has_basis_by_kind");
    plan.groups[1].unresolved_items[0].refs[0] = "unresolved".into();
    assert_violation(check_plan_view(&plan), "plan_unresolved_refs_valid");
    plan.groups[0].need = None;
    plan.groups[1].unresolved_items[0].refs.clear();
    assert!(check_plan_view(&plan).is_empty());
}

#[test]
fn coverage_checks_line_refs_amounts_and_value_sources() {
    let detail: CoverageDetail = serde_json::from_str(fixture!("CoverageDetail")).unwrap();
    for refs in [
        vec![],
        vec!["clause:seg:0123456789ab:p12-14:terms:seg-1.0/art7#p15:docproc-text@1.0".into()],
    ] {
        let mut detail = detail.clone();
        detail.layers[0].lines[0].refs = refs;
        assert_violation(check_coverage_detail(&detail), "coverage_line_has_evidence");
    }
    let mut bad_amount = detail.clone();
    bad_amount.layers[1].lines[0].amounts.as_mut().unwrap()[0].source = "scenario: ".into();
    assert_violation(
        check_coverage_detail(&bad_amount),
        "coverage_line_values_have_sources",
    );
    let mut bad_value = detail.clone();
    bad_value.layers[1].lines[0].values.as_mut().unwrap()[0].source = "".into();
    assert_violation(
        check_coverage_detail(&bad_value),
        "coverage_line_values_have_sources",
    );
    let mut misordered = detail;
    misordered.layers.swap(0, 1);
    assert_violation(
        check_coverage_detail(&misordered),
        "coverage_exclusion_layer_position",
    );
}

#[test]
fn compare_cells_need_evidence_for_facts_applicability_and_amounts() {
    let view: CompareView = serde_json::from_str(fixture!("CompareView")).unwrap();
    for status in [DisplayStatus::Confirmed, DisplayStatus::NotApplicable] {
        for refs in [None, Some(vec![]), Some(vec!["not-evidence".into()])] {
            let mut view = view.clone();
            let cell = &mut view.axes[0].per_column[0];
            cell.display_status = status;
            cell.applicability = "unverified".into();
            cell.refs = refs;
            assert_violation(check_compare_view(&view), "compare_cell_has_evidence");
        }
    }
    let mut view = view;
    for applicability in ["applies", "not_applies"] {
        view.axes[0].per_column[1].applicability = applicability.into();
        assert_violation(check_compare_view(&view), "compare_cell_has_evidence");
    }
    view.axes[0].per_column[1].applicability = "unverified".into();
    let amount = Amount {
        krw: 0,
        source: "scenario:fixture".into(),
        evidence_kind: None,
        applicability: None,
    };
    view.axes[0].per_column[1].amounts = Some(vec![amount.clone()]);
    assert_violation(check_compare_view(&view), "compare_cell_has_evidence");
    view.axes[0].per_column[1].refs = view.axes[0].per_column[0].refs.clone();
    for kind in ["scenario", "premium", "candidate", "clause"] {
        view.axes[0].per_column[1].amounts = Some(vec![Amount {
            source: format!("{kind}:fixture"),
            ..amount.clone()
        }]);
        assert!(check_compare_view(&view).is_empty());
    }
    for bad in [
        Amount {
            source: "estimated:fixture".into(),
            ..amount.clone()
        },
        Amount {
            source: "scenario:".into(),
            ..amount.clone()
        },
        Amount { krw: -1, ..amount },
    ] {
        view.axes[0].per_column[1].amounts = Some(vec![bad]);
        assert_violation(check_compare_view(&view), "compare_cell_amount_has_source");
    }
}

#[test]
fn compare_rejects_dropped_duplicate_and_unknown_columns_or_prices() {
    let view: CompareView = serde_json::from_str(fixture!("CompareView")).unwrap();
    let mut duplicate_column = view.clone();
    duplicate_column.columns.push(view.columns[0].clone());
    assert_violation(
        check_compare_view(&duplicate_column),
        "compare_columns_unique",
    );

    let mut omitted_cell = view.clone();
    omitted_cell.axes[0].per_column.pop();
    assert_violation(
        check_compare_view(&omitted_cell),
        "compare_cells_match_columns",
    );
    let mut foreign_cell = view.clone();
    foreign_cell.axes[0].per_column[0].sc_id = "sc:01J0000000000000000000000A".into();
    assert_violation(
        check_compare_view(&foreign_cell),
        "compare_cells_match_columns",
    );
    let mut duplicate_cell = view.clone();
    duplicate_cell.axes[0]
        .per_column
        .push(view.axes[0].per_column[0].clone());
    assert_violation(
        check_compare_view(&duplicate_cell),
        "compare_cells_match_columns",
    );

    let mut wrong_basis = view.clone();
    wrong_basis.comparison_basis_id = Some("other-basis".into());
    assert_violation(
        check_compare_view(&wrong_basis),
        "compare_price_matches_basis",
    );
    let mut double_counted = view.clone();
    double_counted
        .price
        .as_mut()
        .unwrap()
        .comparable_columns
        .push(view.columns[1].sc_id.clone());
    assert_violation(
        check_compare_view(&double_counted),
        "compare_price_partitions_columns",
    );
    let mut missing_price = view;
    missing_price
        .price
        .as_mut()
        .unwrap()
        .unpriced_columns
        .clear();
    assert_violation(
        check_compare_view(&missing_price),
        "compare_price_partitions_columns",
    );
    missing_price.price = None;
    assert!(check_compare_view(&missing_price).is_empty());
}

#[test]
fn evidence_requires_matching_entry_point_and_typed_chain_steps() {
    let view: EvidenceView = serde_json::from_str(fixture!("EvidenceView")).unwrap();
    let mut empty = view.clone();
    empty.chain.clear();
    assert_violation(check_evidence_view(&empty), "evidence_chain_starts_at_ref");
    let mut wrong_head = view.clone();
    wrong_head.ref_ = view.chain[1].ref_.clone();
    assert_violation(
        check_evidence_view(&wrong_head),
        "evidence_chain_starts_at_ref",
    );
    let mut wrong_level = view;
    wrong_level.chain[2].level = "criterion".into();
    assert_violation(
        check_evidence_view(&wrong_level),
        "evidence_chain_ref_matches_level",
    );
}

#[test]
fn evidence_checks_document_links_and_quote_provenance() {
    let mut view: EvidenceView = serde_json::from_str(fixture!("EvidenceView")).unwrap();
    view.quote_shown = true;
    assert!(check_evidence_view(&view).is_empty());
    for (index, new_ref) in [
        (1, "seg:0123456789ab:p12-16:terms:seg-1.0"),
        (
            2,
            "raw:sha256:1123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ),
        (
            3,
            "obs:src:org:fixture/web/1/2026-10-01T09:00:00Z/1123456789abcdef",
        ),
    ] {
        let mut broken = view.clone();
        broken.chain[index].ref_ = new_ref.into();
        assert_violation(check_evidence_view(&broken), "evidence_document_chain_link");
    }
    let mut truncated = view.clone();
    truncated.chain.pop();
    assert_violation(
        check_evidence_view(&truncated),
        "evidence_document_chain_link",
    );
    view.chain.insert(
        2,
        ChainStep {
            level: "edition".into(),
            ref_: "ted:01BX5ZZKBKACTAV9WEVGEMMVRY".into(),
            display: "fixture edition".into(),
            source_url: None,
            observed_at: None,
        },
    );
    assert!(check_evidence_view(&view).is_empty());
    view.chain.remove(0);
    view.ref_ = view.chain[0].ref_.clone();
    assert_violation(check_evidence_view(&view), "evidence_quote_has_clause");
    view.quote_shown = false;
    assert!(check_evidence_view(&view).is_empty());
}

#[test]
fn need_reasons_require_the_basis_for_each_statement_kind() {
    let mut result: NeedResult = serde_json::from_str(fixture!("NeedResult")).unwrap();
    let fact = result.reasons.remove(0);
    let unknown = result.reasons.remove(0);
    assert_violation(check_need_result(&result), "need_has_reasons");
    let base = NeedReason {
        assertion_refs: vec![],
        ..fact.clone()
    };
    let remove_basis = [
        (fact, base.clone()),
        (
            unknown.clone(),
            NeedReason {
                unknown_overlap: Some(vec![]),
                ..unknown
            },
        ),
        (
            NeedReason {
                statement_kind: "user_assumption".into(),
                user_assumption_ref: Some("assume:01J0000000000000000000000A@1".into()),
                ..base.clone()
            },
            NeedReason {
                statement_kind: "user_assumption".into(),
                user_assumption_ref: Some("assume:01J0000000000000000000000A@x".into()),
                ..base.clone()
            },
        ),
        (
            NeedReason {
                statement_kind: "calc_result".into(),
                eval_ref: Some("eval:01J0000000000000000000000A".into()),
                ..base.clone()
            },
            NeedReason {
                statement_kind: "calc_result".into(),
                ..base.clone()
            },
        ),
        (
            NeedReason {
                statement_kind: "criteria_eval".into(),
                criterion_version_ref: Some("crit:diag@1".into()),
                ..base.clone()
            },
            NeedReason {
                statement_kind: "criteria_eval".into(),
                ..base.clone()
            },
        ),
    ];
    result.criteria_release_id = Some("crel:20261001-1".into());
    for (good, bad) in remove_basis {
        result.reasons = vec![good];
        assert!(
            check_need_result(&result).is_empty(),
            "{:?}",
            result.reasons
        );
        let good = result.reasons[0].clone();
        result.reasons[0].evidence.push("garbled evidence".into());
        assert_violation(check_need_result(&result), "need_reason_has_basis_by_kind");
        result.reasons = vec![bad];
        assert_violation(check_need_result(&result), "need_reason_has_basis_by_kind");
        result.reasons = vec![NeedReason {
            statement_kind: "new_kind".into(),
            ..good
        }];
        assert_violation(check_need_result(&result), "need_reason_has_basis_by_kind");
    }
    result.criteria_release_id = None;
    result.reasons = vec![NeedReason {
        statement_kind: "criteria_eval".into(),
        criterion_version_ref: Some("crit:diag@1".into()),
        ..base
    }];
    assert_violation(check_need_result(&result), "need_criteria_has_release");
}

#[test]
fn release_manifest_checks_canonical_members_and_hashes() {
    let mut manifest: ReleaseManifest = serde_json::from_str(fixture!("ReleaseManifest")).unwrap();
    manifest.members.nodes = vec!["node:a".into(), "node:b".into()];
    assert!(check_release_manifest(&manifest).is_empty());
    for ids in [
        vec!["node:b", "node:a"],
        vec!["node:a", "node:a"],
        vec![" "],
    ] {
        manifest.members.nodes = ids.into_iter().map(String::from).collect();
        assert_violation(
            check_release_manifest(&manifest),
            "release_members_sorted_unique",
        );
    }
    manifest
        .rule_files
        .insert("rules/bad.json".into(), "missing-hash".into());
    assert_violation(check_release_manifest(&manifest), "release_hashes_valid");
    manifest.rule_files.remove("rules/bad.json");
    let mut bad_hash = manifest.clone();
    bad_hash.content_sha256.make_ascii_uppercase();
    assert_violation(check_release_manifest(&bad_hash), "release_hashes_valid");
    let mut bad_model = manifest.clone();
    bad_model.model_versions[0].model_ref_hash.clear();
    assert_violation(check_release_manifest(&bad_model), "release_hashes_valid");
    manifest
        .rule_files
        .insert(" ".into(), manifest.content_sha256.clone());
    assert_violation(check_release_manifest(&manifest), "release_hashes_valid");
}

#[test]
fn release_manifest_checks_withdrawal_and_supersession() {
    let mut manifest: ReleaseManifest = serde_json::from_str(fixture!("ReleaseManifest")).unwrap();
    manifest.superseded_by = Some(manifest.release_id.clone());
    assert_violation(
        check_release_manifest(&manifest),
        "release_cannot_supersede_itself",
    );
    manifest.superseded_by = Some("rel:20261002-1".into());
    manifest.withdrawal_reason = Some("fixture correction".into());
    assert_violation(
        check_release_manifest(&manifest),
        "release_withdrawal_has_time_and_reason",
    );
    manifest.withdrawn_at = Some("2026-10-02T12:00:00+09:00".into());
    assert!(check_release_manifest(&manifest).is_empty());
    for reason in [None, Some(" ".into())] {
        manifest.withdrawal_reason = reason;
        assert_violation(
            check_release_manifest(&manifest),
            "release_withdrawal_has_time_and_reason",
        );
    }
    manifest.withdrawal_reason = Some("fixture correction".into());
    manifest.withdrawn_at = Some("2026-10-32T12:00:00Z".into());
    assert_violation(
        check_release_manifest(&manifest),
        "release_withdrawal_has_time_and_reason",
    );
    manifest.frozen_at = "2026-02-30T09:00:00Z".into();
    assert_violation(
        check_release_manifest(&manifest),
        "release_timestamps_valid",
    );
}

#[test]
fn snapshot_checks_sensitivity_edition_evidence_and_periods() {
    let mut snapshot: ContractSnapshot =
        serde_json::from_str(fixture!("ContractSnapshot")).unwrap();
    for sensitivity in [Sensitivity::GeneticPrivate, Sensitivity::PublicProduct] {
        snapshot.sensitivity = sensitivity;
        assert_violation(
            check_contract_snapshot(&snapshot),
            "contract_snapshot_sensitivity_private",
        );
    }
    snapshot.sensitivity = Sensitivity::PrivateHealth;
    snapshot.applied_editions[0].to = Some(snapshot.applied_editions[0].from.clone());
    assert!(check_contract_snapshot(&snapshot).is_empty());
    for end in ["2024-02-30", "2023-12-31"] {
        snapshot.applied_editions[0].to = Some(end.into());
        assert_violation(
            check_contract_snapshot(&snapshot),
            "contract_edition_period_valid",
        );
    }
    snapshot.applied_editions[0].basis_evidence.clear();
    assert_violation(
        check_contract_snapshot(&snapshot),
        "contract_edition_has_evidence",
    );
    snapshot.sales_config_ref.match_ = ContractVersionMatch::Unmatched;
    snapshot.applied_editions.clear();
    assert!(check_contract_snapshot(&snapshot).is_empty());
}

#[test]
fn snapshot_checks_component_amounts_and_user_confirmation() {
    let snapshot: ContractSnapshot = serde_json::from_str(fixture!("ContractSnapshot")).unwrap();
    let component = &snapshot.components[0];
    for invalid in [
        SnapshotComponent {
            cov_ref: "cov:latest".into(),
            ..component.clone()
        },
        SnapshotComponent {
            insured_amount_krw: -1,
            ..component.clone()
        },
        SnapshotComponent {
            as_of: "2026-10-32".into(),
            ..component.clone()
        },
    ] {
        let mut snapshot = snapshot.clone();
        snapshot.components[0] = invalid;
        assert_violation(
            check_contract_snapshot(&snapshot),
            "contract_component_valid",
        );
    }
    let mut snapshot = snapshot;
    snapshot.components[0].confirm_party = ConfirmParty::Document;
    assert_violation(
        check_contract_snapshot(&snapshot),
        "contract_component_confirmed_by_user",
    );
    snapshot.components[0].fact_source = FactSource::PdfExtracted;
    snapshot.user_confirmed_at = None;
    assert!(check_contract_snapshot(&snapshot).is_empty());
    snapshot.user_confirmed_at = Some("2026-10-01".into());
    assert_violation(
        check_contract_snapshot(&snapshot),
        "contract_confirmation_time_valid",
    );
}
