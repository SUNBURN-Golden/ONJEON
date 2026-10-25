"""Vocabulary lint fixtures are temporary documents, never canonical contracts."""
import contextlib
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
