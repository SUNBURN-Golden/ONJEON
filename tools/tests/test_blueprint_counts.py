"""Audit 2: generated counts follow live sources and reject drift in CI."""
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import blueprint_counts as bc

LISTING = """    Finished `test` profile
     Running unittests src/lib.rs (target/debug/deps/example)
alpha: test
beta: test

2 tests, 0 benchmarks
     Running tests/loader.rs (target/debug/deps/loader)
valid: test

1 test, 0 benchmarks
   Doc-tests onjeon_rules_engine
src/rule.rs - Rule (line 1): test

1 test, 0 benchmarks
"""


class SourceCounts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vocab = self.root / "packages/schemas/vocabulary.json"
        self.rules = self.root / "packages/fixtures/rules/real"
        self.vocab.parent.mkdir(parents=True)
        self.rules.mkdir(parents=True)
        self.write(self.vocab, {"axes": {"a": {}, "b": {}}})
        self.write(self.rules / "one.json", {"rule_id": "one", "publication_state": "fixture_only"})
        self.write(self.rules / "one.cases.json", {"cases": [{}, {}]})

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def collect(self):
        with patch.object(bc.validation_check, "mutations", return_value={"a": None, "b": None}):
            return bc.collect(self.root, LISTING)

    def test_live_counts_exclude_case_files_and_split_doctests(self):
        self.assertEqual(self.collect(), dict(rust_tests=3, rust_doctests=1,
                                             real_clause_rules=1, vocabulary_axes=2, tamper_tests=2))

    def test_source_additions_change_the_counts(self):
        self.write(self.vocab, {"axes": {"a": {}, "b": {}, "c": {}}})
        self.write(self.rules / "two.json", {"rule_id": "two", "publication_state": "fixture_only"})
        self.assertEqual(self.collect()["vocabulary_axes"], 3)
        self.assertEqual(self.collect()["real_clause_rules"], 2)

    def test_duplicate_or_publishable_or_missing_rule_ids_fail(self):
        for rule in ({"rule_id": "one", "publication_state": "fixture_only"},
                     {"rule_id": "two", "publication_state": "accepted"},
                     {"publication_state": "fixture_only"}):
            with self.subTest(rule=rule):
                self.write(self.rules / "two.json", rule)
                with self.assertRaises(ValueError):
                    self.collect()

    def test_no_rules_is_an_error(self):
        (self.rules / "one.json").unlink()
        with self.assertRaises(ValueError):
            self.collect()

    def test_empty_vocabulary_is_an_error(self):
        self.write(self.vocab, {"axes": {}})
        with self.assertRaises(ValueError):
            self.collect()

    def test_empty_mutation_inventory_is_an_error(self):
        with patch.object(bc.validation_check, "mutations", return_value={}):
            with self.assertRaises(ValueError):
                bc.collect(self.root, LISTING)

    def test_malformed_or_missing_canonical_source_is_an_error(self):
        self.vocab.write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.collect()
        self.vocab.unlink()
        with self.assertRaises(OSError):
            self.collect()


class CargoListing(unittest.TestCase):
    def test_counts_registered_tests_in_multiple_binaries(self):
        self.assertEqual(bc.cargo_counts(LISTING), dict(rust_tests=3, rust_doctests=1))

    def test_incomplete_or_inconsistent_listings_fail_closed(self):
        for listing in ("", "error: could not compile", "alpha: test\n", "0 tests, 0 benchmarks",
                        LISTING.replace("2 tests,", "9 tests,"),
                        LISTING.replace("2 tests, 0 benchmarks", "2 tests, 1 benchmark"),
                        LISTING.split("   Doc-tests")[0],
                        LISTING.rsplit("1 test, 0 benchmarks", 1)[0],
                        LISTING.replace("2 tests, 0 benchmarks", "")):
            with self.subTest(listing=listing):
                with self.assertRaises(ValueError):
                    bc.cargo_counts(listing)


class DocumentCounts(unittest.TestCase):
    def setUp(self):
        self.counts = dict(rust_tests=3, rust_doctests=1, real_clause_rules=7,
                           vocabulary_axes=49, tamper_tests=38)
        self.prefix = "# Blueprint\n\n## 6. Vocabulary\nunchanged\n\n## 11. 현재 위치 (2026-10-27)\nstatus\n\n"
        self.suffix = "\n\n## 12. Gates\npending\n"
        self.text = self.prefix + bc.render(self.counts) + self.suffix

    def test_matching_block_passes(self):
        self.assertEqual(bc.check(self.text, self.counts), [])

    def test_each_live_count_change_requires_refresh(self):
        for key in self.counts:
            with self.subTest(key=key):
                changed = {**self.counts, key: self.counts[key] + 1}
                self.assertTrue(bc.check(self.text, changed))
                refreshed = bc.refresh(self.text, changed)
                self.assertEqual(bc.check(refreshed, changed), [])
                self.assertTrue(refreshed.startswith(self.prefix))
                self.assertTrue(refreshed.endswith(self.suffix))

    def test_stale_audit_numbers_are_rejected(self):
        for before, after in (("| 3 |", "| 42 |"), ("| 7 |", "| 8 |"),
                              ("| 38 |", "| 28 |"), ("| 49 |", "| 31 |")):
            with self.subTest(after=after):
                self.assertTrue(bc.check(self.text.replace(before, after), self.counts))

    def test_missing_duplicate_reversed_or_misplaced_markers_fail(self):
        for text in (self.text.replace(bc.START, ""), self.text.replace(bc.END, ""),
                     self.text + bc.START, self.text + bc.END,
                     self.prefix + bc.END + bc.START + self.suffix,
                     self.prefix + self.suffix + bc.render(self.counts)):
            with self.subTest(text=text):
                self.assertTrue(bc.check(text, self.counts))
                with self.assertRaises(ValueError):
                    bc.refresh(text, self.counts)

    def test_cli_is_read_only_until_explicit_write_and_returns_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "docs/BLUEPRINT.md"
            path.parent.mkdir()
            stale = self.text.replace("| 38 |", "| 28 |")
            path.write_text(stale, encoding="utf-8")
            with patch.object(bc, "ROOT", root), patch.object(bc, "collect", return_value=self.counts), \
                    patch.object(bc.subprocess, "run", return_value=subprocess.CompletedProcess(bc.CARGO, 0, LISTING)) as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bc.main([]), 1)
                self.assertEqual(path.read_text(encoding="utf-8"), stale)
                self.assertEqual(bc.main(["--write"]), 0)
                self.assertEqual(path.read_text(encoding="utf-8"), self.text)
                self.assertEqual(bc.main([]), 0)
                self.assertEqual(run.call_args.args[0], bc.CARGO)
                self.assertTrue(run.call_args.kwargs["check"])

    def test_cli_discovery_failure_preserves_document_even_with_write(self):
        path = ROOT / "docs/BLUEPRINT.md"
        before = path.read_bytes()
        for error in (OSError("cargo missing"), subprocess.CalledProcessError(101, bc.CARGO)):
            with self.subTest(error=error), patch.object(bc.subprocess, "run", side_effect=error), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bc.main(["--write"]), 2)
                self.assertEqual(path.read_bytes(), before)


class InventoryDocumentation(unittest.TestCase):
    def test_adr_0014_real_clause_count_matches_fixture_inventory(self):
        text = (ROOT / "docs/decisions/ADR-0014-V1-검증-결과의-설계-반영.md").read_text(encoding="utf-8")
        counts = re.findall(r"^- 실제 조항 규칙 (\d+)건은 `fixture_only`", text, re.M)
        rules = [path for path in (ROOT / "packages/fixtures/rules/real").glob("*.json")
                 if not path.name.endswith(".cases.json")]
        self.assertTrue(rules)
        self.assertEqual(counts, [str(len(rules))])

    def test_validation_readme_tamper_count_matches_mutations(self):
        text = (ROOT / "docs/blueprint/validation/README.md").read_text(encoding="utf-8")
        counts = re.findall(r"`--selftest` (\d+)종", text)
        self.assertEqual(counts, [str(len(bc.validation_check.mutations()))])

    def test_ci_runs_counts_check_and_existing_discovery_tests(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("run: python3 -I tools/blueprint_counts.py\n", workflow)
        self.assertIn("python3 -m unittest discover -s tools/tests -v", workflow)

    def test_blueprint_records_r2_tools_and_load_time_type_check(self):
        text = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        code = next(line for line in text.splitlines() if line.startswith("| 코드 |"))
        self.assertIn("로드 단계 타입 검사(#40", code)
        self.assertIn("packages/rules-engine/tests/static_types.rs", code)
        self.assertTrue((ROOT / "packages/rules-engine/tests/static_types.rs").is_file())
        inventory = next(line for line in text.splitlines() if line.startswith("| 수집·검증 도구 |"))
        for name in ("tools/source_archive.py", "tools/verify_sources.py", "tools/r2_budget.py", "infra/r2/"):
            with self.subTest(name=name):
                self.assertIn(name, inventory)
                self.assertTrue((ROOT / name).exists())


if __name__ == "__main__":
    unittest.main()
