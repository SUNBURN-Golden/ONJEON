"""Keep the audit's evidence harness runnable as purpose-row wording changes."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
HARNESS = TOOLS / "evidence/audit2-purpose-gate-unimplemented/purpose_mutation.py"
spec = importlib.util.spec_from_file_location("purpose_mutation", HARNESS)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class PurposeMutationTests(unittest.TestCase):
    def test_scope_targets_row_and_header_instead_of_wording_or_position(self):
        text = ("| # | 축소·후속(근거) | 목적 |\n"
                "|---|---|---|\n"
                "| P08 | revised wording | revised wording |\n"
                "| P09 | revised wording | revised wording |\n")
        self.assertEqual(text.replace("| P09 | revised wording |", "| P09 | no basis |"),
                         M.scope("P09", "no basis")({}, text))

    def test_scope_rejects_missing_duplicate_rows_or_missing_column(self):
        header = "| # | 축소·후속(근거) |\n"
        row = "| P09 | basis |\n"
        for text in (header, header + row + row, "| # | 목적 |\n" + row):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                M.scope("P09", "no basis")({}, text)

    def test_live_p09_mutation_changes_only_its_scope_cell(self):
        mutated = M.scope("P09", "no basis")({}, M.PURPOSE)
        original_lines, mutated_lines = M.PURPOSE.splitlines(), mutated.splitlines()
        self.assertEqual(len(original_lines), len(mutated_lines))
        changed = [(before, after) for before, after in zip(original_lines, mutated_lines) if before != after]
        self.assertEqual(1, len(changed))
        before, after = changed[0]
        self.assertTrue(before.startswith("| P09 |"))
        self.assertEqual(before.split("|")[:-2], after.split("|")[:-2])
        self.assertEqual(" no basis ", after.split("|")[-2])

    def test_live_harness_finishes_all_cases_and_checker_rejects_each_mutation(self):
        result = subprocess.run([sys.executable, "-I", str(HARNESS), str(TOOLS / "ci")],
                                capture_output=True, text=True, timeout=150)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        cases = result.stdout.split("== mutation: ")[1:]
        self.assertEqual(12, len(cases), result.stdout)
        self.assertIn("exit=0\n", cases[0])
        for case in cases[1:]:
            with self.subTest(mutation=case.splitlines()[0]):
                self.assertIn("exit=1\n", case)
        self.assertIn("PURPOSE-SCOPE", cases[3])
        self.assertIn("P09", cases[3])
        self.assertIn("PURPOSE-SCOPE", cases[4])
        self.assertIn("P19", cases[4])
        self.assertIn("11/12 runs exited nonzero", result.stdout)

    def test_stalled_checker_fails_promptly_and_names_the_running_case(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "check_product_purpose.py").write_text(
                "import time\ntime.sleep(600)\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-I", str(HARNESS), directory, "--timeout", "0.1"],
                capture_output=True, text=True, timeout=5)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("== mutation: none (live repo copy)", result.stdout)
        self.assertIn("TIMEOUT: checker exceeded 0.1s for none (live repo copy)", result.stdout)
        self.assertEqual(1, result.stdout.count("== mutation:"))
        self.assertNotIn("runs exited nonzero", result.stdout)
        self.assertEqual("", result.stderr)

    def test_timeout_must_be_finite_and_positive(self):
        for value in ("0", "-1", "nan", "inf", "-inf"):
            with self.subTest(value=value):
                result = subprocess.run(
                    [sys.executable, "-I", str(HARNESS), str(TOOLS / "ci"), f"--timeout={value}"],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(2, result.returncode)
                self.assertIn("timeout must be finite and positive", result.stderr)
                self.assertNotIn("== mutation:", result.stdout)


if __name__ == "__main__":
    unittest.main()
