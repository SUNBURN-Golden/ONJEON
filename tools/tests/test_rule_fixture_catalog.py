"""Active rule sources must never silently fall back to superseded fixtures."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from rule_fixture_catalog import MANIFEST, load_rules


class RuleFixtureCatalog(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for directory in ("packages/fixtures/rules/real", "packages/rules-engine/fixtures/rules"):
            shutil.copytree(ROOT / directory, self.root / directory)
        self.manifest = json.loads((self.root / MANIFEST).read_text())
        self.entries = list(self.manifest["replacements"].values())

    def test_active_catalog_has_seven_rules_and_only_corrected_wholelife_sources(self):
        rules = load_rules(self.root)
        self.assertEqual(len(rules), 7)
        for entry in self.entries:
            self.assertNotIn(entry["supersedes"], rules)
            self.assertIn({"gte": ["death_date", "coverage_start_date"]},
                          rules[entry["source"]]["eligibility"]["all"])

    def test_missing_manifest_or_replacement_fails_without_fallback(self):
        for relative in (MANIFEST, *(entry["source"] for entry in self.entries)):
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    load_rules(self.root)
                path.write_bytes(original)

    def test_removing_guard_is_detected_by_the_replacement_pin(self):
        for entry in self.entries:
            with self.subTest(source=entry["source"]):
                path = self.root / entry["source"]
                original = path.read_text()
                rule = json.loads(original)
                rule["eligibility"]["all"].pop(0)
                path.write_text(json.dumps(rule))
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    load_rules(self.root)
                path.write_text(original)

    def test_stale_superseded_source_is_detected(self):
        path = self.root / self.entries[0]["supersedes"]
        rule = json.loads(path.read_text())
        rule["rule_version"] = "unexpected"
        path.write_text(json.dumps(rule))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_rules(self.root)

    def test_replacement_identity_and_publication_state_are_checked(self):
        path = self.root / self.entries[0]["source"]
        original = path.read_text()
        for key, value in (("rule_id", "wrong"), ("publication_state", "published")):
            with self.subTest(key=key):
                rule = json.loads(original)
                rule[key] = value
                path.write_text(json.dumps(rule))
                with self.assertRaisesRegex(ValueError, "identity, state or hash mismatch"):
                    load_rules(self.root)

    def test_validation_metadata_uses_the_active_sources(self):
        import validation_check
        data = validation_check.load()
        active = load_rules(ROOT)
        self.assertEqual(data["rules"], active)
        for rule in data["families"]["kyobo_wholelife"]["rules"]:
            if rule["status"] != "not_expressible":
                self.assertIn(rule["file"], active)


if __name__ == "__main__":
    unittest.main()
