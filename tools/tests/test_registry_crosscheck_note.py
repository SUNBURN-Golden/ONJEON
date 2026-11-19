"""The registry README distinguishes the 2026-10-09 outage from the 2026-11-10 re-check.

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
        self.fss_note = self.text.split("## 감독당국 교차검증 (2026-11-10)", 1)[1].split("\n## ", 1)[0]

    def test_note_records_the_2026_11_10_recheck_as_done_and_bounded(self):
        for phrase in ("공백 1 해소", "2026-11-10에 수행했다", "기준년월 202606",
                       "파인 제도권 금융회사 조회", "authority_crosscheck_2026-11-10.csv",
                       "`insurers.csv` 53곳은 모두 두 목록에 있다",
                       "젠워스", "동경해상일동화재보험", "다시 계산하지 않았다",
                       "기관 목록에 한정", "당시 상품 목록은 53곳 모두 `unqueried`",
                       "T-DT-04", "D-04", "O19", "Audit 5", "Audit 7"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.fss_note)
        self.assertNotIn("후속 교차검증은 미수행", self.gaps)
        self.assertNotIn("2026-10-11 이후", self.gaps)
        self.assertNotIn("감독당국 목록이 복구되면", self.gaps)
        self.assertFalse(any(line.startswith("1. ") for line in self.gaps.splitlines()))

    def test_two_or_more_sources_keeps_its_old_meaning(self):
        for phrase in ("two_or_more_sources", "`entity_evidence`는 기존 협회·KIDI·DART 조사 기준으로 계산했다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.fss_note)

    def test_2026_10_09_outage_attempts_are_preserved(self):
        attempts = [r for r in rows("access_log") if r["host"] in AUTHORITY_HOSTS
                    and r["attempted_at"][:10] == "2026-10-09"]
        self.assertEqual(len(attempts), 4)  # One redirect plus three outage notices.
        self.assertEqual(Counter(r["result"] for r in attempts),
                         Counter({"307": 1, "200_service_outage_notice": 3}))
        sources = [r for r in rows("sources")
                   if urlsplit(r["url"]).hostname in AUTHORITY_HOSTS
                   and r["retrieved_at"][:10] == "2026-10-09"]
        self.assertEqual(len(sources), 3)
        for source in sources:
            with self.subTest(source=source["source_id"]):
                self.assertEqual(source["http_status"], "200_service_outage_notice")
                self.assertIn("서비스 중단 안내", source["what_it_lists"])
        # DART is recorded, but is not a licensing-list cross-check.
        self.assertTrue(any(urlsplit(r["url"]).hostname == "dart.fss.or.kr"
                            for r in rows("sources")))

    def test_product_enumeration_has_separate_evidence_from_the_crosscheck(self):
        # The crosscheck note keeps the historical "all unqueried" framing; the
        # 2026-11-19 initial discovery superseded it for the 8 verified entries.
        insurers = rows("insurers")
        self.assertEqual(Counter(r["product_list_status"] for r in insurers),
                         Counter(unqueried=45, failed=7, blocked=1))
        for phrase in ("이 대조는 기관 목록에 한정", "당시 상품 목록은 53곳 모두 `unqueried`",
                       "T-DT-04", "D-04", "O19", "초기 상품 목록 관측"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.fss_note)

    def test_small_insurer_gap_names_the_two_unresolved_entities(self):
        small_insurers = next(line for line in self.gaps.splitlines() if line.startswith("10. "))
        for phrase in ("FISIS에만 있는 젠워스", "파인에만 있는 동경해상일동화재보험(주)서울지점",
                       "Aioi", "`insurers.csv` 분모"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, small_insurers)
        self.assertNotIn("공백 1의 후속 교차검증", small_insurers)


if __name__ == "__main__":
    unittest.main()
