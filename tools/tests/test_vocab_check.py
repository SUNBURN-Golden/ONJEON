"""Vocabulary lint fixtures are temporary documents, never canonical contracts."""
import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import vocab_check as vc


class Lint(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, value in (("ROOT", self.root), ("DOC", self.root / "contracts/generated.md"),
                            ("CONTRACT_DOCS", ["contracts/*.md"])):
            patcher = mock.patch.object(vc, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.vocab = dict(axes=[dict(id="state", field_aliases=["old_field"], forbidden_codes=["banned_state"],
                                    values=[dict(code="current", deprecated_aliases=["old_state", "OLD", "old", "cross_live"])]),
                               dict(id="other", values=[dict(code="cross_live", deprecated_aliases=[])])],
                          timestamps=[dict(field="observed_at", deprecated_aliases=["old_timestamp"])])

    def document(self, text, name="contracts/a.md"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_reports_aliases_forbidden_codes_fields_and_timestamps_with_line_numbers(self):
        self.document("# title\n`old_state`\n| banned_state | old_field | old_timestamp |\n")
        self.assertEqual(vc.lint(self.vocab), [
            "contracts/a.md:2: `old_state` -> use state.current",
            "contracts/a.md:3: `banned_state` -> use forbidden in state",
            "contracts/a.md:3: `old_field` -> use field state",
            "contracts/a.md:3: `old_timestamp` -> use timestamp observed_at",
        ])

    def test_live_alias_in_another_axis_is_allowed(self):
        self.document("`cross_live` current cross_live\n")
        self.assertEqual(vc.lint(self.vocab), [])

    def test_explicit_allow_marker_skips_only_its_own_line(self):
        self.document("old_state <!-- vocab:allow -->\nold_state\n")
        self.assertEqual(vc.lint(self.vocab), ["contracts/a.md:2: `old_state` -> use state.current"])

    def test_generated_doc_and_files_outside_contract_globs_are_excluded(self):
        self.document("old_state", "contracts/generated.md")
        self.document("old_state", "history/background.md")
        self.assertEqual(vc.lint(self.vocab), [])

    def test_tokens_are_deduplicated_per_line_and_sorted_per_file(self):
        self.document("old_state `old_state` old_field\nold_state", "contracts/z.md")
        self.document("old_state", "contracts/a.md")
        self.assertEqual(vc.lint(self.vocab), [
            "contracts/a.md:1: `old_state` -> use state.current",
            "contracts/z.md:1: `old_field` -> use field state",
            "contracts/z.md:1: `old_state` -> use state.current",
            "contracts/z.md:2: `old_state` -> use state.current",
        ])

    def test_word_boundaries_do_not_match_paths_or_longer_identifiers(self):
        self.document("prefix_old_state old_state_suffix xold_state old_state2\n"
                      "dir/old_state ./old_state file-old_state a.old_state\n")
        self.assertEqual(vc.lint(self.vocab), [])

    def test_backticks_match_uppercase_and_short_aliases(self):
        self.document("OLD old\n`OLD` `old`\n")
        self.assertEqual(vc.lint(self.vocab), [
            "contracts/a.md:2: `OLD` -> use state.current",
            "contracts/a.md:2: `old` -> use state.current",
        ])

    def test_forbidden_reason_takes_precedence_over_alias_reason(self):
        self.vocab["axes"][0]["values"][0]["deprecated_aliases"].append("banned_state")
        self.document("banned_state")
        self.assertEqual(vc.lint(self.vocab), ["contracts/a.md:1: `banned_state` -> use forbidden in state"])

    def test_stale_axis_count_next_to_a_vocabulary_pointer_is_reported(self):
        self.document("ok\n전체 31개 축과 화면 문구는 VOCABULARY.md에 있다.\n상태 어휘 정본(5개의 축)\n")
        self.assertEqual(vc.lint(self.vocab), [
            "contracts/a.md:2: says 31 axes, vocabulary.json has 2; drop the number (a count in prose goes stale)",
            "contracts/a.md:3: says 5 axes, vocabulary.json has 2; drop the number (a count in prose goes stale)",
        ])

    def test_axis_count_matching_vocabulary_or_unrelated_or_opted_out_is_allowed(self):
        self.document("전체 2개 축은 VOCABULARY.md에 있다.\n화면은 3개 축으로 나눈다.\n"
                      "전체 31개 축 VOCABULARY.md <!-- vocab:allow -->\n전체 축은 VOCABULARY.md에 있다.\n")
        self.assertEqual(vc.lint(self.vocab), [])

    def test_stale_blueprint_or_proposal_count_fails_the_cli(self):
        for name in ("docs/BLUEPRINT.md", "docs/blueprint/proposals/인계_설계책임/README.md"):
            with self.subTest(name=name):
                self.document("전체 31개 축은 VOCABULARY.md에 있다.\n", name)
                rendered = "전체 2개 축.\n"
                self.document(rendered, "contracts/generated.md")
                output = io.StringIO()
                with mock.patch.object(vc, "CONTRACT_DOCS", ["docs/BLUEPRINT.md"]), \
                     mock.patch.object(vc, "load", return_value=self.vocab), \
                     mock.patch.object(vc, "validate", return_value=[]), \
                     mock.patch.object(vc, "render", return_value=rendered), \
                     mock.patch.object(sys, "argv", ["vocab_check.py"]), \
                     contextlib.redirect_stdout(output):
                    self.assertEqual(vc.main(), 1)
                self.assertIn(f"{name}:1: says 31 axes, vocabulary.json has 2", output.getvalue())
                (self.root / name).unlink()

    def test_proposal_count_scan_is_separate_from_deprecated_status_lint(self):
        name = "docs/blueprint/proposals/example/README.md"
        self.document("old_state\n상태 어휘 정본(31개 축)\n", name)
        self.assertEqual(vc.lint(self.vocab), [
            f"{name}:2: says 31 axes, vocabulary.json has 2; drop the number (a count in prose goes stale)"])
        self.document("old_state\n상태 어휘 정본(31개 축) <!-- vocab:allow -->\n", name)
        self.assertEqual(vc.lint(self.vocab), [])

    def test_no_matching_contracts_is_clean(self):
        self.assertEqual(vc.lint(self.vocab), [])


class RegistryLint(unittest.TestCase):
    def setUp(self):
        self.vocab = vc.load()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.object(vc, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def document(self, text, name="sample.csv"):
        path = self.root / "data/registry" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_all_registry_state_columns_accept_only_their_own_axis(self):
        columns = {"entity_evidence": "entity_evidence", "home_access": "host_access",
                   "disclosure_access": "host_access", "host_access": "host_access",
                   "disclosure_status": "acquisition_status", "product_list_status": "acquisition_status"}
        for column, axis_id in columns.items():
            axis = next(a for a in self.vocab["axes"] if a["id"] == axis_id)
            for value in axis["values"]:
                self.document(f"{column}\n{value['code']}\n")
                self.assertEqual(vc.lint_registry(self.vocab), [], (column, value))
            aliases = [al for value in axis["values"] for al in value["deprecated_aliases"]]
            for value in [*aliases, "unknown_value", "", " " + axis["values"][0]["code"],
                          "reachable" if axis_id != "host_access" else "archived"]:
                with self.subTest(column=column, value=value):
                    self.document(f'{column},notes\n{value},kept\n')
                    problems = vc.lint_registry(self.vocab)
                    self.assertEqual(len(problems), 1)
                    self.assertIn(f"data/registry/sample.csv:2: {column}=", problems[0])
                    self.assertIn(f"expected {axis_id} code", problems[0])

    def test_old_status_header_fails_even_when_empty_or_with_canonical_values(self):
        for body in ("", "verified_1_source\n", "one_source\n"):
            self.document("status\n" + body)
            self.assertEqual(vc.lint_registry(self.vocab), [
                "data/registry/sample.csv:1: deprecated field `status` -> use entity_evidence"])

    def test_required_state_columns_cannot_be_dropped_from_known_registries(self):
        required = {
            "insurers.csv": ["entity_evidence", "home_access", "disclosure_access",
                             "disclosure_status", "product_list_status"],
            "cooperatives_and_others.csv": ["entity_evidence", "home_access", "disclosure_access",
                                           "disclosure_status", "product_list_status"],
            "excluded_or_historical.csv": ["entity_evidence", "home_access", "disclosure_access"],
            "access_log.csv": ["host_access"],
        }
        for name, columns in required.items():
            for missing in columns:
                with self.subTest(name=name, missing=missing):
                    path = self.document(",".join(["notes", *(c for c in columns if c != missing)]) + "\n", name)
                    self.assertEqual(vc.lint_registry(self.vocab), [
                        f"data/registry/{name}:1: missing required vocabulary column `{missing}`"])
                    path.unlink()

    def test_raw_results_details_notes_and_sources_are_preserved(self):
        self.document('host_access,result,home_access_detail,notes\n'
                      'reachable,200,403_origin,"verified_1_source,\nvocab:allow"\n')
        self.document('source_id,http_status,notes\nlist,200,verified_2_sources\n', "sources.csv")
        self.assertEqual(vc.lint_registry(self.vocab), [])
        # A prose allow marker cannot exempt a structured status value.
        self.document('entity_evidence,notes\nverified_1_source,vocab:allow\n')
        self.assertTrue(vc.lint_registry(self.vocab))

    def test_csv_structure_errors_cannot_hide_invalid_values(self):
        for text, expected in (
                ("", "missing CSV header"),
                ("entity_evidence,entity_evidence\nverified_1_source,one_source\n", "duplicate CSV column"),
                ("entity_evidence,notes\none_source\n", "expected 2 cells, got 1"),
                ("entity_evidence\none_source,verified_1_source\n", "expected 1 cells, got 2"),
                ('entity_evidence,notes\none_source,"unterminated\n', "invalid CSV")):
            with self.subTest(text=text):
                self.document(text)
                self.assertTrue(any(expected in p for p in vc.lint_registry(self.vocab)))

    def test_diagnostic_uses_physical_line_after_a_multiline_cell(self):
        self.document('entity_evidence,notes\none_source,"first\nsecond"\nverified_1_source,old\n')
        problems = vc.lint_registry(self.vocab)
        self.assertEqual(len(problems), 1)
        self.assertIn("data/registry/sample.csv:4: entity_evidence=", problems[0])

    def test_repository_registries_are_canonical_and_excluded_rows_remain_excluded(self):
        root = Path(__file__).resolve().parents[2]
        with mock.patch.object(vc, "ROOT", root):
            self.assertEqual(vc.lint_registry(self.vocab), [])
        with (root / "data/registry/excluded_or_historical.csv").open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        self.assertNotIn("status", reader.fieldnames)
        self.assertNotIn("product_list_status", reader.fieldnames)
        self.assertEqual(len(rows), 49)
        self.assertEqual(sum(r["entity_evidence"] == "two_or_more_sources" for r in rows), 2)
        self.assertEqual(sum(r["entity_evidence"] == "one_source" for r in rows), 47)
        self.assertTrue(all(r["in_current_assoc_list"] == "false" for r in rows))

    def test_cli_fails_on_registry_regression_without_changing_csv_even_with_write(self):
        path = self.document("status\nverified_1_source\n")
        before = path.read_bytes()
        doc = self.root / "generated.md"
        doc.write_text(vc.render(self.vocab), encoding="utf-8")
        for args in ([], ["--write"]):
            output = io.StringIO()
            with mock.patch.object(vc, "DOC", doc), \
                 mock.patch.object(sys, "argv", ["vocab_check.py", *args]), \
                 contextlib.redirect_stdout(output):
                self.assertEqual(vc.main(), 1)
            self.assertIn("data/registry/sample.csv:1: deprecated field `status`", output.getvalue())
            self.assertEqual(path.read_bytes(), before)


class GeneratedDoc(unittest.TestCase):
    """The generated document must exactly match render(), including the live axis count."""

    def vocab(self, n):
        return dict(version="1.0.0", updated="2026-01-01", rules=[], timestamps=[],
                    axes=[dict(id=f"axis_{i}", name_ko="이름", applies_to="대상", layer="L0",
                               concept_ko="개념",
                               values=[dict(code="on", concept_ko="개념", screen_ko=None,
                                            deprecated_aliases=[])])
                          for i in range(n)])

    def test_render_states_the_live_count_on_its_own_line(self):
        self.assertIn("\n전체 3개 축.\n", vc.render(self.vocab(3)))

    def test_a_missing_count_line_is_drift(self):
        v = self.vocab(3)
        older = vc.render(v).replace("\n전체 3개 축.\n", "")
        self.assertTrue(vc.generated_doc_problems(older, vc.render(v), 3))

    def test_adding_an_axis_requires_regeneration_and_updates_the_count(self):
        old = vc.render(self.vocab(3))
        new = vc.render(self.vocab(4))
        self.assertTrue(vc.generated_doc_problems(old, new, 4))
        self.assertIn("\n전체 4개 축.\n", new)
        self.assertEqual(vc.generated_doc_problems(new, new, 4), [])

    def test_cli_repairs_count_left_stale_by_target_branch_merge(self):
        # A clean text merge can add all four new axes while retaining the old count.
        v = self.vocab(49)
        rendered = vc.render(v)
        merged = rendered.replace("전체 49개 축.", "전체 45개 축.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "docs/blueprint/VOCABULARY.md"
            source = root / "packages/schemas/vocabulary.json"
            doc.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            doc.write_text(merged, encoding="utf-8")
            source.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
            source_before = source.read_bytes()
            with mock.patch.object(vc, "ROOT", root), \
                 mock.patch.object(vc, "DOC", doc), \
                 mock.patch.object(vc, "VOCAB", source):
                output = io.StringIO()
                with mock.patch.object(sys, "argv", ["vocab_check.py"]), \
                     contextlib.redirect_stdout(output):
                    self.assertEqual(vc.main(), 1)
                self.assertIn("axis count [45], vocabulary.json has 49", output.getvalue())
                self.assertEqual(doc.read_text(encoding="utf-8"), merged)
                for args in (["--write"], [], ["--write"]):
                    with mock.patch.object(sys, "argv", ["vocab_check.py", *args]), \
                         contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(vc.main(), 0)
                    self.assertEqual(doc.read_text(encoding="utf-8"), rendered)
                    self.assertEqual(source.read_bytes(), source_before)

    def test_a_stale_or_doubled_count_line_is_drift(self):
        v = self.vocab(3)
        rendered = vc.render(v)
        stale = rendered.replace("전체 3개 축.", "전체 2개 축.")
        doubled = rendered + "전체 3개 축.\n"
        self.assertTrue(vc.generated_doc_problems(stale, rendered, 3))
        self.assertTrue(vc.generated_doc_problems(doubled, rendered, 3))

    def test_any_other_difference_is_out_of_date(self):
        v = self.vocab(3)
        drifted = vc.render(v).replace("## 축 목록", "## axes")
        self.assertTrue(vc.generated_doc_problems(drifted, vc.render(v), 3))


if __name__ == "__main__":
    unittest.main()
