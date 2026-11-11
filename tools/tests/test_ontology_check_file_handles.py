"""File-handle hygiene for ontology_check.py: the module loads and rule reads
used bare open(), so the suite surfaced ResourceWarning noise (unclosed tbox,
abox and 규칙 JSON files). These tests pin the context-manager behaviour:
importing the checker and running its constraint/resolve paths must not leave
unclosed files behind."""
import copy
import gc
import subprocess
import sys
import unittest
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECK_DIR = REPO / "docs/blueprint/proposals/온톨로지/검증"
sys.path.insert(0, str(CHECK_DIR))
import ontology_check as check  # noqa: E402


def leaked(caught, *names):
    return [str(w.message) for w in caught
            if issubclass(w.category, ResourceWarning)
            and any(name in str(w.message) for name in names)]


class FileHandleHygiene(unittest.TestCase):
    def test_import_closes_tbox_and_abox(self):
        # The module-level loads run at import time, so a fresh interpreter
        # with ResourceWarning promoted to error is the only way to pin them.
        code = "import sys; sys.path.insert(0, sys.argv[1]); import ontology_check"
        p = subprocess.run([sys.executable, "-B", "-W", "error::ResourceWarning",
                            "-c", code, str(CHECK_DIR)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_rule_files_hashes_without_leaking_handles(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            hashes = check._rule_files(check.ABOX["assertions"])
            gc.collect()
        self.assertEqual(leaked(caught, "규칙"), [])
        self.assertTrue(hashes)
        for value in hashes.values():
            self.assertTrue(value is None or (len(value) == 64 and
                                              all(c in "0123456789abcdef" for c in value)))

    def test_constraints_and_resolve_do_not_leak_rule_handles(self):
        v = check.view(check.ABOX, check.CURRENT)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            violations = check.check_constraints(v)
            result = check.resolve(v, copy.deepcopy(check.QUESTIONS[0]))
            gc.collect()
        self.assertEqual(leaked(caught, "규칙"), [])
        self.assertIsInstance(violations, list)
        self.assertIn("steps", result)


if __name__ == "__main__":
    unittest.main()
