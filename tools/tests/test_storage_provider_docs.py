"""Docs must state the storage provider decided in ADR-0016 (R2), not the superseded S3 one (ADR-0015)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "docs/blueprint/validation"
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"

# Phrases that were true before ADR-0016 (2026-10-09) and are false now.
STALE = ("보관소는 S3로 결정", "S3 실제 보존", "S3 버킷 정의(미배포)", "자격 증명이 없어 아직 올리지 못")


def read(path):
    return path.read_text(encoding="utf-8")


class GapReport(unittest.TestCase):
    def setUp(self):
        self.text = read(VALIDATION / "GAP_REPORT.md")

    def test_no_pre_r2_storage_claims(self):
        for phrase in STALE:
            self.assertNotIn(phrase, self.text)

    def test_names_r2_decision(self):
        line = next(l for l in self.text.splitlines() if "원본 보관소" in l)
        self.assertIn("Cloudflare R2", line)
        self.assertIn("ADR-0016", line)

    def test_cited_r2_evidence_exists(self):
        evidence = sorted((VALIDATION / "source_checks").glob("2026-10-09_r2_*.json"))
        self.assertTrue(evidence)
        readme = read(VALIDATION / "README.md")
        for path in evidence:
            self.assertIn(path.name, readme)

    def test_full_reproduction_count_matches_check_record(self):
        # 8 of 14 reproduced, the other 6 unverified: the R2 reproduction record is the source.
        record = read(VALIDATION / "source_checks/2026-10-09_r2_reproduce_ocr.json")
        self.assertRegex(record, r'"reproduced"\s*:\s*8\b')
        self.assertRegex(record, r'"derived_unverified"\s*:\s*6\b')
        line = next(l for l in self.text.splitlines() if "원본 보관소" in l)
        self.assertRegex(line, r"완전 재현은 8건, 6건")


class Blueprint(unittest.TestCase):
    """docs/BLUEPRINT.md is protected: the supervisor round that found this could not edit it.

    expectedFailure turns into an "unexpected success" (a failing run) as soon as the V1 row of §9.2
    and the §11 code row are corrected, which is the cue to delete the decorator. The replacement
    wording is in docs/review/2026-10-22_audit1_blueprint_s3_stale.md.
    """

    @unittest.expectedFailure
    def test_no_pre_r2_storage_claims(self):
        text = read(BLUEPRINT)
        found = [p for p in STALE if p in text]
        self.assertEqual(found, [])

    def test_section_11_already_reports_r2(self):
        text = read(BLUEPRINT)
        self.assertRegex(text, r"R2에 보존하고 다시 받아 전부 바이트 일치")
        self.assertIsNotNone(re.search(r"ADR-0016|ADR-0017", text))


if __name__ == "__main__":
    unittest.main()
