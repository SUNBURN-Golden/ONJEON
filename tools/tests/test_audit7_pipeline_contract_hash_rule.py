"""Track the deferred HTML rebaseline: decision, preserved v1 baselines, disclosed drift."""

import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import html_content_hash as hch  # noqa: E402
import source_archive as sa  # noqa: E402

DECISION = Path("docs/decisions/audit7-pipeline-contract-hash-rule.md")
AUDIT = Path("docs/blueprint/audits/2026-11-20_pipeline_contract_hash_rule.md")
VALIDATION = Path("docs/blueprint/validation/README.md")
CONTRACT = Path("docs/data/DATA_PIPELINE_CONTRACT.md")
LISTING = Path("docs/blueprint/validation/source_checks/archive_listing_raw.json")
EVIDENCE = Path("tools/evidence/audit7-pipeline-contract-hash-rule/README.md")
PENDING = "위임 결정·가역·사용자 확정 아님"

# Preserved 2026-10-09 observations (samples.csv rows 12-14): byte SHA-256 key and
# v1 content baseline. When the authorized operator rebaselines with verified local
# copies (tools/rebaseline_html_samples.py), update these pins in the same change
# as the execution evidence, per docs/decisions/audit7-pipeline-contract-hash-rule.md.
PRESERVED = {
    "klia_pub_cancer_compare": (
        "2d384476ec877db49fa7bb28488777c6040dc43e298f71703ec52f64bc598ff5",
        "eff6ca84c098d6c310bc5ef6e48839a13f4e940c44827bb09dd8bb9639158a2a",
    ),
    "klia_pub_cancer_criteria": (
        "200da98f6bde03bc5ee5c4f38b0ff192ab4653fb037e26ac47d13593e9798b35",
        "ee2cc37083c9e25b6dab250fd489bfa64445b0876bdb38a4565aac8c2a3bbb60",
    ),
    "kb_caregiver_cost_html": (
        "6ade7ccbb07bfa9ae002ec686131167fa308e6a2d0b7730d85b34698b13ed0b2",
        "39c2939717910c4e027fccd84e91b73eaac017df10f2173d10df83dd853b75ff",
    ),
}


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class DeferredHtmlRebaseline(unittest.TestCase):
    def test_decision_fixes_the_operator_copy_path(self):
        text = read(DECISION)
        for phrase in (PENDING, "지정 실행 환경", "SHA-256", "objects/sha256/<aa>/<bb>/<sha256>",
                       "재수집으로 대체하지 않는다", "DEC-D-04", "후속 작업",
                       "rebaseline_html_samples.py", DECISION.stem):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        for sample_id, (digest, _) in PRESERVED.items():
            with self.subTest(sample_id=sample_id):
                self.assertIn(sample_id, text)
                self.assertIn(digest, text)
        self.assertIn(AUDIT.name, text)
        self.assertIn(EVIDENCE.parent.name, text)

    def test_preserved_v1_baselines_match_the_fixed_archive_keys(self):
        with (ROOT / "docs/blueprint/validation/samples.csv").open(encoding="utf-8", newline="") as f:
            rows = {r["sample_id"]: r for r in csv.DictReader(f)}
        self.assertEqual({sid for sid, r in rows.items() if r["format"] == "html"}, set(PRESERVED))
        listing = json.loads(read(LISTING))["objects"]
        for sample_id, (digest, baseline_v1) in PRESERVED.items():
            with self.subTest(sample_id=sample_id):
                row = rows[sample_id]
                self.assertEqual(row["sha256"], digest)
                self.assertEqual(row["content_hash_rule"], "html-visible-text-v1")
                self.assertEqual(row["content_sha256"], baseline_v1)
                self.assertEqual(listing.get(sa.object_key(digest)), digest)

    def test_protected_contract_lines_await_authorized_correction(self):
        # docs/data/ is protected for this node. When the authorized correction
        # lands, flip these two pins to hch.RULE in the same change.
        lines = read(CONTRACT).splitlines()
        for number in (40, 55):
            with self.subTest(line=number):
                self.assertIn("html-visible-text-v1", lines[number - 1])
        paragraph = next(line for line in read("docs/BLUEPRINT.md").splitlines()
                         if line.startswith("동적 HTML의 현재 본문 해시 규칙"))
        self.assertIn(f"`{hch.RULE}`", paragraph)
        self.assertIn("`DATA_PIPELINE_CONTRACT` §3·§3.1", paragraph)
        self.assertIn(DECISION.name, paragraph)

    def test_pending_state_is_disclosed_and_linked(self):
        section = read(VALIDATION).split("### HTML 본문 해시", 1)[1].split("### 검증 이력", 1)[0]
        for phrase in ("40·55", "v1 기준값", "changed", "rebaseline_html_samples.py", DECISION.name):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)
        for path in (AUDIT, EVIDENCE):
            with self.subTest(record=path):
                self.assertIn(DECISION.name, read(path))


if __name__ == "__main__":
    unittest.main()