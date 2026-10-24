"""Vocabulary lint fixtures are temporary documents, never canonical contracts."""
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

    def test_no_matching_contracts_is_clean(self):
        self.assertEqual(vc.lint(self.vocab), [])


if __name__ == "__main__":
    unittest.main()
