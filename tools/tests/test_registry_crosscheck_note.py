"""The FSS note describes committed evidence, not an expired retry promise.

Offline repository snapshot checks; no regulator or insurer requests are made.
"""
import csv
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data/registry"
AUTHORITY_HOSTS = {"www.fss.or.kr", "fine.fss.or.kr", "fisis.fss.or.kr"}


def rows(name):
    with (REG / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class CrosscheckNote(unittest.TestCase):
    def setUp(self):
        self.text = (REG / "README.md").read_text(encoding="utf-8")
        self.gaps = self.text.split("## 알려진 공백", 1)[1].split("\n## ", 1)[0]
        self.fss_note = next(line for line in self.gaps.splitlines() if line.startswith("1. "))

    def test_note_distinguishes_last_attempt_from_unperformed_followup(self):
        for phrase in ("2026-11-04", "후속 교차검증은 미수행", "2026-10-09",
                       "현재 서비스 중단 여부는 확인하지 않았다", "협회 + KIDI/DART",
                       "감독당국 허가 목록과 대조한 결과가 아니다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.fss_note)
        self.assertNotIn("2026-10-11 이후", self.gaps)
        self.assertNotIn("감독당국 목록이 복구되면", self.gaps)

    def test_historical_outage_is_the_only_committed_authority_attempt(self):
        attempts = [r for r in rows("access_log") if r["host"] in AUTHORITY_HOSTS]
        self.assertEqual(len(attempts), 4)  # One redirect plus three outage notices.
        self.assertEqual({r["attempted_at"][:10] for r in attempts}, {"2026-10-09"})
        self.assertEqual(Counter(r["result"] for r in attempts),
                         Counter({"307": 1, "200_service_outage_notice": 3}))
        sources = [r for r in rows("sources")
                   if urlsplit(r["url"]).hostname in AUTHORITY_HOSTS]
        self.assertEqual(len(sources), 3)
        for source in sources:
            with self.subTest(source=source["source_id"]):
                self.assertEqual(source["http_status"], "200_service_outage_notice")
                self.assertEqual(source["retrieved_at"][:10], "2026-10-09")
                self.assertIn("서비스 중단 안내", source["what_it_lists"])
        # DART is recorded, but is not a licensing-list cross-check.
        self.assertTrue(any(urlsplit(r["url"]).hostname == "dart.fss.or.kr"
                            for r in rows("sources")))

    def test_product_enumeration_is_separate_and_still_unqueried(self):
        insurers = rows("insurers")
        self.assertEqual(Counter(r["product_list_status"] for r in insurers),
                         Counter(unqueried=53))
        for phrase in ("기관 목록 대조", "상품 목록 열거", "53곳 모두 `unqueried`",
                       "T-DT-04", "D-04", "O19"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.fss_note)

    def test_followup_requires_retrieval_and_comparison_evidence(self):
        for phrase in ("FISIS 보험회사 목록", "파인 금융회사 조회", "조회 시각·URL·응답 해시",
                       "기관별 일치·누락·명칭 차이", "sources.csv", "access_log.csv"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.fss_note)
        small_insurers = next(line for line in self.gaps.splitlines() if line.startswith("10. "))
        self.assertIn("공백 1의 후속 교차검증", small_insurers)


if __name__ == "__main__":
    unittest.main()
