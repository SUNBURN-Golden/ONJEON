"""Re-run tools/tests/test_readme_index.py with README:22 truncated to the audited state (ADRs only through 0011)."""
import re, sys, unittest
sys.path.insert(0, "tools/tests")
import test_readme_index as m
row = m.row("docs/decisions/")
cut = re.sub(r", 0012 .*?(?=\. 결정 기록)", "", row)
assert cut != row and "0012" not in cut and "0011 설계도 채택" in cut
m.README = m.README.replace(row, cut)
r = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(m.DecisionsRow))
print("mutant_detected =", not r.wasSuccessful())
sys.exit(0 if not r.wasSuccessful() else 1)
