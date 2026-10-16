"""The committed evidence (codegen/evidence/) is what reviewers read at the target SHA.

Checks that every log is present, records a passing run, and leaks nothing (absolute paths of the
machine the logs were made on, obvious secrets, cargo lock noise). Freshness, i.e. that the tree hash
in EVIDENCE.md is the hash of the current tree, is NOT checked here: run
`bash packages/schemas/codegen/tree_hash.sh` and compare by hand; a different value means the logs
must be regenerated with the commands listed in EVIDENCE.md.
"""
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent / "evidence"
LOGS = ["build_check.log", "cargo_test.log", "vocab_check.log", "check_compat.log", "rule02.log"]
# absolute paths, credentials, and the message cargo prints when two builds collide
LEAK = re.compile(
    r"/workspace|/home/|/Users/|[A-Z]:\\\\|AKIA[0-9A-Z]{12}|sk-[A-Za-z0-9]{16}|ghp_[A-Za-z0-9]{20}|"
    r"BEGIN [A-Z ]*PRIVATE KEY|Blocking waiting for file lock"
)
# versioned identifiers of the form name-N.N / name-N-N (tool or model versions quoted verbatim). Only
# the project's own tokens are allowed; tool versions belong in EVIDENCE.md's version table as plain text.
VERSIONED_NAME = re.compile(r"\b[a-z]+(?:-[a-z]+)*-[0-9]+(?:[.-][0-9]+)+\b", re.I)
ALLOWED_VERSIONED = re.compile(r"^(?:contracts-[0-9.]+|rule-0\.[0-9]+)$")


def exit_codes(text):
    return [int(m) for m in re.findall(r"^exit code: (\d+)$", text, re.M)]


class EvidenceFiles(unittest.TestCase):
    def read(self, name):
        path = EVIDENCE / name
        self.assertTrue(path.is_file(), f"missing {path.relative_to(HERE.parent.parent)}")
        return path.read_text(encoding="utf-8")

    def test_every_log_and_the_index_exist(self):
        for name in LOGS + ["EVIDENCE.md"]:
            self.read(name)

    def test_each_log_starts_with_its_command_and_records_exit_codes(self):
        for name in LOGS:
            text = self.read(name)
            self.assertTrue(text.startswith("$ "), f"{name}: first line must be the command")
            self.assertTrue(exit_codes(text), f"{name}: no 'exit code:' line")

    def test_build_check_log_proves_all_three_languages(self):
        text = self.read("build_check.log")
        self.assertIn("ONJ_REQUIRE_TOOLCHAINS=1", text.splitlines()[0])
        self.assertIn("Rust: built", text)
        self.assertIn("TypeScript: built, fixtures type-check", text)
        self.assertIn("Dart: analyzed and round-tripped", text)
        self.assertIn("RESULT: all three languages build", text)
        self.assertNotIn("SKIPPED", text)
        self.assertEqual(exit_codes(text), [0])

    def test_cargo_test_logs_pass(self):
        for name in ("cargo_test.log", "rule02.log"):
            text = self.read(name)
            self.assertNotIn("FAILED", text, name)
            self.assertNotIn("panicked", text, name)
            self.assertRegex(text, r"test result: ok\. \d+ passed; 0 failed", name)
            self.assertTrue(all(c == 0 for c in exit_codes(text)), name)

    def test_rule02_log_is_not_vacuous(self):
        text = self.read("rule02.log")
        self.assertIn("ONJ_REQUIRE_RULE_02=1", text.splitlines()[0])
        self.assertIn("rule_02_contract_effects_round_trip_when_the_engine_supports_them ... ok", text)
        self.assertIn("--nocapture", text, "the uncaptured run is what shows a VACUOUS line would have been visible")
        self.assertNotIn("VACUOUS", text)

    def test_check_compat_log_runs_the_selftest_and_is_honest_about_the_baseline(self):
        text = self.read("check_compat.log")
        self.assertIn("--selftest", text)
        self.assertGreaterEqual(text.count("self-test ok"), 2)
        self.assertIn("structural diff: deleted field detected", text)
        self.assertIn("compile probe: previous client cannot read documents without the deleted field", text)
        # either no tag exists (said so, self-test only) or a real tag was compared
        self.assertTrue("BASELINE: no contracts-* tag exists yet" in text or "compatible with contracts-" in text)
        for code, before in zip(exit_codes(text), text.split("\nexit code: ")):
            if code != 0:  # the only non-zero run allowed is the ONJ_REQUIRE_BASELINE=1 refusal
                self.assertEqual(code, 2)
                self.assertIn("ONJ_REQUIRE_BASELINE=1 forbids the first-release pass", before)

    def test_vocab_check_log_passes(self):
        text = self.read("vocab_check.log")
        self.assertRegex(text, r"vocabulary ok: \d+ axes, \d+ values")
        self.assertEqual(exit_codes(text), [0])

    def test_index_names_every_log_and_pins_the_tree(self):
        text = self.read("EVIDENCE.md")
        for name in LOGS:
            self.assertIn(name, text)
        self.assertRegex(text, r"\b[0-9a-f]{40}\b", "parent commit SHA")
        self.assertRegex(text, r"\b[0-9a-f]{64}\b", "sha256 of the packages/schemas tree")
        self.assertIn("tree_hash.sh", text)
        self.assertIn("T-CT-01", text)

    def test_no_leaks(self):
        # subdirectories hold other tasks' evidence (ct03/) and are held to the same rules
        for path in sorted(p for p in EVIDENCE.rglob("*") if p.is_file()):
            name = str(path.relative_to(EVIDENCE))
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(LEAK.search(text), f"{name}: {LEAK.search(text) and LEAK.search(text).group(0)!r}")
            bad = [m for m in VERSIONED_NAME.findall(text) if not ALLOWED_VERSIONED.match(m)]
            self.assertEqual(bad, [], f"{name}: versioned identifiers quoted verbatim")


if __name__ == "__main__":
    unittest.main()
