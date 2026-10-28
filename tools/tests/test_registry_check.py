"""Registry references: disposable fixtures, real-data regressions and CLI/CI wiring."""
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_check as rc

ROOT = Path(__file__).resolve().parents[2]


class CrossReferences(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.reg = Path(tmp.name)
        self.write("insurers.csv", [dict(insurer_id="nonlife-mitsuisumitomo-kr", listed_in="association;regulator")])
        self.write("cooperatives_and_others.csv", [dict(insurer_id="public-epost", listed_in="association"),
                                                  dict(insurer_id="seed-other", listed_in="")])
        self.write("excluded_or_historical.csv", [dict(insurer_id="hist-old", listed_in="regulator")])
        sources = [dict(source_id=s) for s in ("association", "regulator")]
        purposes = [dict(purpose="source:original_scratch_file.html"),
                    dict(purpose="wikipedia_search (tertiary source attempt)")]
        for entity in ("nonlife-mitsuisumitomo-kr", "public-epost", "hist-old"):
            for kind in rc.KINDS:
                sources.append(dict(source_id=f"{kind}_{entity}"))
                purposes.append(dict(purpose=f"{kind}:{entity}"))
        self.write("sources.csv", sources)
        self.write("access_log.csv", purposes)

    def write(self, name, rows, fields=None):
        with (self.reg / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def change(self, name, old, new):
        path = self.reg / name
        path.write_bytes(path.read_bytes().replace(old.encode(), new.encode()))

    def test_valid_references_include_all_entity_tables_kinds_and_seed(self):
        before = {p.name: p.read_bytes() for p in self.reg.iterdir()}
        self.assertEqual(rc.check(self.reg), [])
        self.assertEqual({p.name: p.read_bytes() for p in self.reg.iterdir()}, before)

    def test_audit_id_mismatches_report_file_line_and_reference(self):
        self.change("sources.csv", "homepage_nonlife-mitsuisumitomo-kr", "homepage_nonlife-mitsuisumitomo")
        self.change("access_log.csv", "homepage:nonlife-mitsuisumitomo-kr", "homepage:nonlife-mitsuisumitomo")
        self.change("access_log.csv", "homepage:public-epost", "homepage:other-epost")
        problems = rc.check(self.reg)
        self.assertEqual(len(problems), 3)
        for message, location, bad in zip(problems, ("sources.csv:5:", "access_log.csv:5:", "access_log.csv:8:"),
                                          ("nonlife-mitsuisumitomo", "nonlife-mitsuisumitomo", "other-epost")):
            self.assertIn(location, message)
            self.assertIn(f"unknown insurer_id '{bad}'", message)

    def test_unknown_entity_in_every_structured_prefix_is_rejected(self):
        for name, field, separator in (("sources.csv", "source_id", "_"), ("access_log.csv", "purpose", ":")):
            for kind in rc.KINDS:
                with self.subTest(name=name, kind=kind):
                    self.write(name, [{field: kind + separator + "missing"}])
                    self.assertTrue(any(f"{name}:2:" in p and "unknown insurer_id 'missing'" in p
                                        for p in rc.check(self.reg)))

    def test_listed_in_is_checked_in_all_three_tables(self):
        for name in rc.ENTITY_FILES:
            with self.subTest(name=name):
                self.change(name, "association", "unknown")
                self.change(name, "regulator", "unknown")
                self.assertTrue(any(p.startswith(f"{name}:2: listed_in references unknown source_id 'unknown'")
                                    for p in rc.check(self.reg)))

    def test_empty_or_whitespace_reference_components_are_rejected(self):
        for value in ("association;", ";association", "association;;regulator", " association"):
            with self.subTest(value=value):
                self.write("insurers.csv", [dict(insurer_id="nonlife-mitsuisumitomo-kr", listed_in=value)])
                self.assertTrue(any("listed_in references unknown source_id" in p for p in rc.check(self.reg)))
        for kind in rc.KINDS:
            for suffix in ("", " public-epost", "public-epost "):
                with self.subTest(kind=kind, suffix=suffix):
                    self.write("access_log.csv", [dict(purpose=kind + ":" + suffix)])
                    self.assertTrue(any("unknown insurer_id" in p for p in rc.check(self.reg)))

    def test_duplicate_entity_ids_within_and_across_tables_are_rejected(self):
        for name in ("insurers.csv", "cooperatives_and_others.csv"):
            with self.subTest(name=name):
                self.write(name, [dict(insurer_id="nonlife-mitsuisumitomo-kr", listed_in=""),
                                  dict(insurer_id="nonlife-mitsuisumitomo-kr", listed_in="")])
                self.assertTrue(any("duplicate insurer_id" in p and name in p for p in rc.check(self.reg)))

    def test_duplicate_source_ids_are_rejected(self):
        self.write("sources.csv", [dict(source_id="association"), dict(source_id="association")])
        self.assertIn("sources.csv:3: duplicate source_id 'association' (first at sources.csv:2)", rc.check(self.reg))

    def test_empty_and_whitespace_ids_are_rejected(self):
        for name, field, extra in (("sources.csv", "source_id", {}),
                                   ("insurers.csv", "insurer_id", dict(listed_in=""))):
            for value in ("", " ", " public-epost", "public-epost "):
                with self.subTest(name=name, value=value):
                    self.write(name, [dict(extra, **{field: value})])
                    self.assertTrue(any(f"{field} must be non-empty" in p for p in rc.check(self.reg)))

    def test_missing_each_input_and_required_column_fails(self):
        for name, field in [(n, "listed_in") for n in rc.ENTITY_FILES] + [("sources.csv", "source_id"),
                                                                       ("access_log.csv", "purpose")]:
            with self.subTest(name=name):
                path = self.reg / name
                before = path.read_bytes()
                path.unlink()
                self.assertTrue(any(f"{name}: cannot read CSV" in p for p in rc.check(self.reg)))
                self.write(name, [dict(unrelated="value")])
                self.assertTrue(any(name in p and "missing required columns" in p and field in p
                                    for p in rc.check(self.reg)))
                path.write_bytes(before)

    def test_malformed_csv_fails_with_location(self):
        for content, expected in (("", "missing or empty CSV header"),
                                  ("purpose,\n", "missing or empty CSV header"),
                                  ("purpose,purpose\n", "duplicate CSV column"),
                                  ("purpose\na,b\n", "expected 1 cells, got 2"),
                                  ('purpose\n"unterminated\n', "invalid CSV")):
            with self.subTest(content=content):
                (self.reg / "access_log.csv").write_text(content, encoding="utf-8")
                self.assertTrue(any(p.startswith("access_log.csv:") and expected in p for p in rc.check(self.reg)))
        (self.reg / "access_log.csv").write_bytes(b"purpose\n\xff\n")
        self.assertIn("access_log.csv: cannot read CSV (UnicodeDecodeError)", rc.check(self.reg))

    def test_physical_line_number_accounts_for_quoted_newline(self):
        self.write("access_log.csv", [dict(purpose="historical\nprobe"), dict(purpose="homepage:missing")])
        self.assertTrue(any(p.startswith("access_log.csv:4:") for p in rc.check(self.reg)))

    def test_header_only_access_log_is_valid(self):
        self.write("access_log.csv", [], ["purpose"])
        self.assertEqual(rc.check(self.reg), [])

    def test_cli_success_failure_and_read_only_operation(self):
        command = [sys.executable, "-I", str(ROOT / "tools/registry_check.py"), "--registry-dir", str(self.reg)]
        good = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr + good.stdout)
        self.assertIn("registry cross-references ok", good.stdout)
        self.change("access_log.csv", "homepage:public-epost", "homepage:other-epost")
        before = {p.name: p.read_bytes() for p in self.reg.iterdir()}
        bad = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stderr + bad.stdout)
        self.assertIn("unknown insurer_id 'other-epost'", bad.stdout)
        self.assertNotIn("Traceback", bad.stderr)
        self.assertEqual({p.name: p.read_bytes() for p in self.reg.iterdir()}, before)


class LiveRegistry(unittest.TestCase):
    def test_repository_cross_references(self):
        self.assertEqual(rc.check(), [])

    def test_ci_runs_cross_reference_checker(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("        run: python3 -I tools/registry_check.py\n", workflow)


if __name__ == "__main__":
    unittest.main()
