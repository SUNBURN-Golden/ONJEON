"""R2 버킷 안내의 원장 키 목록을 실제 허용 접두어와 대조한다."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import r2_budget as b  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


class LedgerBucketLayout(unittest.TestCase):
    def test_readme_lists_every_control_prefix_in_ledger_bucket_row(self):
        readme = (ROOT / "infra/r2/README.md").read_text(encoding="utf-8")
        rows = [line for line in readme.splitlines()
                if line.startswith("| `onjeon-budget-ledger` |")]
        self.assertEqual(len(rows), 1, "expected one ledger bucket row")
        keys = rows[0].split("|")[3]
        documented = re.findall(r"`([a-z]+/v\d+/)[^`]*`", keys)
        self.assertCountEqual(documented, b.CONTROL_PREFIXES,
                              "R2 README ledger keys differ from allowed control prefixes")


if __name__ == "__main__":
    unittest.main()
