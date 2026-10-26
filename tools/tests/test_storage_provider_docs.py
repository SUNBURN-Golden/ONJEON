"""Docs must state the storage provider decided in ADR-0016 (R2), not the superseded S3 one (ADR-0015)."""
import json
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
    """The V1 gate and implementation inventory must agree with the R2 evidence."""

    def setUp(self):
        self.text = read(BLUEPRINT)
        self.v1 = next(line for line in self.text.splitlines() if line.startswith("| V1 |"))

    def test_no_pre_r2_storage_claims(self):
        found = [p for p in STALE if p in self.text]
        self.assertEqual(found, [])

    def test_v1_names_r2_and_completed_preservation(self):
        self.assertIn("Cloudflare R2", self.v1)
        self.assertIn("ADR-0016", self.v1)
        self.assertIn("R2에 보존하고 다시 받아 전부 바이트 일치", self.v1)

    def test_v1_remaining_conditions_keep_unverified_work(self):
        remaining = self.v1.split("남은 조건:", 1)[1]
        for phrase in ("파생 6건", "재생성 도구", "재현 검증", "다른 계열 AI 검수", "S1·S6"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, remaining)
        for phrase in ("S3", "자격 증명", "실제 보존", "다운로드 대조"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, remaining)
        self.assertIn("관문 미통과", self.v1)

    def test_tool_inventory_names_current_and_alternative_storage(self):
        # §11 now separates service code from collection/validation tools.
        section = self.text.split("## 11.", 1)[1].split("## 12.", 1)[0]
        line = next(line for line in section.splitlines() if line.startswith("| 수집·검증 도구 |"))
        for phrase in ("tools/source_archive.py", "tools/verify_sources.py", "tools/r2_budget.py",
                       "실행별 제한", "infra/r2/", "대안", "infra/s3/", "미배포"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, line)

    def test_v1_counts_match_r2_records_and_gap_report(self):
        checks = VALIDATION / "source_checks"
        gap = next(line for line in read(VALIDATION / "GAP_REPORT.md").splitlines() if "원본 보관소" in line)
        for name, count, label in (("raw", 58, "원본"), ("derived_v2", 61, "파생 v2")):
            with self.subTest(record=name):
                record = json.loads(read(checks / f"2026-10-09_r2_listing_{name}.json"))
                self.assertTrue(record["destination"].startswith("r2:"))
                self.assertEqual(record["summary"], {"byte_identical": count})
                self.assertEqual(len(record["results"]), count)
                self.assertEqual(record["extra_in_destination"], [])
                for result in record["results"]:
                    self.assertEqual(result["status"], "byte_identical")
                    self.assertEqual(result["sha256_source"], result["sha256_downloaded"])
                for line in (self.v1, gap):
                    self.assertIn(f"{label} {count}키", line)

        samples = json.loads(read(checks / "2026-10-09_r2_verify_samples.json"))
        self.assertTrue(samples["store"].startswith("r2:"))
        self.assertEqual(samples["summary"], {"byte_identical": 14})
        self.assertEqual(len(samples["results"]), 14)
        for result in samples["results"]:
            self.assertEqual(result["status"], "byte_identical")
            self.assertEqual(result["sha256_recorded"], result["sha256_downloaded"])

        reproduction = json.loads(read(checks / "2026-10-09_r2_reproduce_ocr.json"))
        self.assertTrue(reproduction["source"].startswith("r2:"))
        self.assertEqual(reproduction["summary"], {"reproduced": 8, "derived_unverified": 6})
        results = reproduction["results"]
        self.assertEqual(len(results), 14)
        self.assertEqual(sum(r["status"] == "reproduced" for r in results), 8)
        self.assertEqual(sum(r["status"] == "derived_unverified" for r in results), 6)
        for result in results:
            self.assertEqual(result["sha256_recorded"], result["sha256_archived_bytes"])
            self.assertEqual(result["not_found"], 0)
        self.assertIn("원본 해시·인용 14/14", self.v1)
        self.assertIn("완전 재현 8/14", self.v1)
        self.assertIn("나머지 6건은 재생성 도구 없음으로 미검증", self.v1)

    def test_section_11_already_reports_r2(self):
        section = self.text.split("## 11.", 1)[1].split("## 12.", 1)[0]
        lines = [l for l in section.splitlines() if "R2에 보존하고 다시 받아 전부 바이트 일치" in l]
        self.assertTrue(lines)
        self.assertTrue(all("2026-10-09 관측 기록" in line for line in lines))
        # The same line must say it is the R2 round trip, not just contain the byte-match phrase.
        self.assertTrue(all("원본 R2" in l or "R2에 보존" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
