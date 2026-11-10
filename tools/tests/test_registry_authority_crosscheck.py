"""The 2026-11-10 FISIS/Fine cross-check is committed, institution-level evidence.

Reads registry CSVs and README only; no network requests are made.
"""
import csv
import re
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data/registry"
CROSSCHECK = REG / "authority_crosscheck_2026-11-10.csv"
AUTHORITY_HOSTS = {"fisis.fss.or.kr", "fine.fss.or.kr"}
OFFICIAL_DATE = "2026-11-10"


def rows(name):
    with (REG / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def crosscheck_rows():
    with CROSSCHECK.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class CrosscheckTable(unittest.TestCase):
    def setUp(self):
        self.rows = crosscheck_rows()
        self.insurers = rows("insurers")
        self.excluded = rows("excluded_or_historical")

    def test_shape_and_authority_category_counts(self):
        self.assertEqual(len(self.rows), 57)
        self.assertEqual(Counter(r["category"] for r in self.rows),
                         Counter(life_domestic=14, life_foreign=8,
                                 nonlife_domestic=18, nonlife_foreign=17))
        for column in ("fisis_id", "fine_id"):
            ids = [r[column] for r in self.rows if r[column]]
            self.assertEqual(len(ids), 56, column)
            self.assertEqual(len(set(ids)), len(ids), f"duplicate {column}")

    def test_every_insurer_appears_once_and_only_as_matched(self):
        matched = [r for r in self.rows if r["comparison"] == "matched"]
        self.assertEqual(len(matched), 53)
        insurer_ids = {r["insurer_id"] for r in self.insurers}
        self.assertEqual({r["registry_id"] for r in matched}, insurer_ids)
        self.assertEqual(len({r["registry_id"] for r in matched}), 53)
        self.assertEqual({r["registry_table"] for r in matched}, {"insurers.csv"})
        names = {r["insurer_id"]: r["name_ko"] for r in self.insurers}
        for row in matched:
            with self.subTest(insurer=row["registry_id"]):
                self.assertEqual(row["registry_name"], names[row["registry_id"]])

    def test_excluded_rows_map_to_the_excluded_file(self):
        nonmatched = [r for r in self.rows if r["comparison"] != "matched"]
        self.assertEqual(Counter(r["comparison"] for r in nonmatched),
                         Counter(excluded=3, missing=1))
        excluded_ids = {r["insurer_id"] for r in self.excluded}
        excluded = [r for r in self.rows if r["comparison"] == "excluded"]
        self.assertEqual({r["registry_id"] for r in excluded},
                         {"dart-df7015d9", "hist-nonlife-mg", "hist-nonlife-carrot"})
        self.assertTrue({r["registry_id"] for r in excluded} <= excluded_ids)

    def test_missing_entity_is_genworth_and_does_not_change_the_denominator(self):
        missing = [r for r in self.rows if r["comparison"] == "missing"]
        self.assertEqual(len(missing), 1)
        row = missing[0]
        self.assertIn("젠워스", row["authority_name"])
        self.assertEqual(row["fisis_id"], "0011909")
        self.assertEqual(row["fine_id"], "")
        self.assertEqual(row["registry_table"], "")
        self.assertEqual(row["registry_id"], "")
        self.assertIn("fisis", row["note"].lower())

    def test_fine_only_aioi_row_is_explicitly_unresolved(self):
        aioi = [r for r in self.rows if r["fine_id"] == "18749"]
        self.assertEqual(len(aioi), 1)
        row = aioi[0]
        self.assertEqual(row["fisis_id"], "")
        self.assertEqual(row["comparison"], "excluded")
        self.assertEqual(row["registry_id"], "dart-df7015d9")
        self.assertIn("Aioi", row["registry_name"])
        self.assertIn("미확정", row["note"])

    def test_name_match_classes_are_documented_values(self):
        self.assertEqual(Counter(r["name_match"] for r in self.rows),
                         Counter({"legal_suffix": 31, "alias": 18, "exact": 4, "": 4}))
        self.assertEqual({r["name_match"] for r in self.rows},
                         {"exact", "legal_suffix", "alias", ""})


class RetrievalEvidence(unittest.TestCase):
    def test_nine_authority_sources_were_retrieved_on_the_recheck_date(self):
        recheck = [r for r in rows("sources")
                   if r["source_id"].startswith(("fisis_20261110_", "fine_20261110_"))]
        self.assertEqual(len(recheck), 9)
        self.assertEqual({r["http_status"] for r in recheck}, {"200"})
        self.assertEqual({r["retrieved_at"][:10] for r in recheck}, {OFFICIAL_DATE})
        for source in recheck:
            with self.subTest(source=source["source_id"]):
                self.assertIn(urlsplit(source["url"]).hostname, AUTHORITY_HOSTS)
                self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(source["what_it_lists"].strip())
        self.assertEqual(len({r["source_id"] for r in recheck}), 9)

    def test_fourteen_authority_requests_succeeded_without_an_outage_page(self):
        recheck = [r for r in rows("access_log")
                   if r["host"] in AUTHORITY_HOSTS and r["attempted_at"][:10] == OFFICIAL_DATE]
        self.assertEqual(len(recheck), 14)
        self.assertEqual({r["http_code"] for r in recheck}, {"200"})
        self.assertEqual({r["curl_exit"] for r in recheck}, {"0"})
        self.assertEqual({r["result"] for r in recheck}, {"200"})
        self.assertEqual({r["host_access"] for r in recheck}, {"reachable"})
        self.assertEqual(Counter(r["purpose"].split(":", 1)[0] for r in recheck),
                         Counter(probe=2, discover=1, meta=2, source=9))
        source_rows = [r for r in recheck if r["purpose"].startswith("source:")]
        source_ids = {r["source_id"] for r in rows("sources")
                      if r["source_id"].startswith(("fisis_20261110_", "fine_20261110_"))}
        for row in source_rows:
            with self.subTest(purpose=row["purpose"]):
                self.assertTrue(any(source_id in row["purpose"] for source_id in source_ids))

    def test_fisis_posts_name_the_part_and_base_month(self):
        posts = [r for r in rows("access_log")
                 if r["attempted_at"][:10] == OFFICIAL_DATE
                 and r["url"].endswith("fsv302_getFinanceList.do")]
        self.assertEqual(len(posts), 2)
        self.assertEqual({r["detail"] for r in posts},
                         {"POST partDiv=H&baseMonth=202606", "POST partDiv=I&baseMonth=202606"})


class ReadmeTally(unittest.TestCase):
    HOME_ROW = re.compile(r"^\| `([a-z_]+)` \| (\d+) \|", re.MULTILINE)
    HOME_TOTAL = re.compile(r"^\| \*\*점검 계\*\* \| \*\*(\d+)\*\*", re.MULTILINE)

    def setUp(self):
        self.text = (REG / "README.md").read_text(encoding="utf-8")
        self.insurers = rows("insurers")

    def test_home_access_table_reconciles_with_insurers_csv(self):
        section = self.text.split("회사 홈페이지 접근", 1)[1].split("\n\n- 지시문", 1)[0]
        stated = Counter({code: int(count) for code, count in self.HOME_ROW.findall(section)})
        actual = Counter(r["home_access"] for r in self.insurers)
        self.assertEqual(stated, Counter({k: v for k, v in actual.items() if k != "not_checked"}))
        total = int(self.HOME_TOTAL.search(section).group(1))
        self.assertEqual(total, sum(stated.values()))
        self.assertEqual(total, 42)
        self.assertEqual(actual["not_checked"], 11)
        self.assertEqual(total + actual["not_checked"], len(self.insurers))

    def test_tls_error_is_listed_once_and_names_three_companies(self):
        self.assertEqual(self.text.count("`tls_error`"), 1)
        row = next(line for line in self.text.splitlines() if line.startswith("| `tls_error` |"))
        self.assertIn("| 3 |", row)
        for company in ("한화생명", "동양생명", "현대해상"):
            with self.subTest(company=company):
                self.assertIn(company, row)

    def test_authority_section_states_the_crosscheck_counts_and_scope(self):
        section = self.text.split("## 감독당국 교차검증 (2026-11-10)", 1)[1].split("\n## ", 1)[0]
        for phrase in ("생명보험(`PART_DIV=H`) 22행", "손해보험(`PART_DIV=I`) 34행",
                       "기준년월 202606", "56행", "55곳", "합집합 57곳",
                       "MG손해보험", "캐롯손해보험", "젠워스", "동경해상일동화재보험",
                       "`product_list_status`는 53곳 모두 `unqueried`",
                       "`entity_evidence` 값도 이번 교차검증으로 다시 계산하지 않았다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)

    def test_file_table_counts_match_the_committed_csvs(self):
        line = next(line for line in self.text.splitlines() if line.startswith("| `sources.csv` |"))
        self.assertIn(f"{len(rows('sources'))}건", line)
        line = next(line for line in self.text.splitlines() if line.startswith("| `access_log.csv` |"))
        self.assertIn(f"{len(rows('access_log'))}건", line)
        line = next(line for line in self.text.splitlines()
                    if line.startswith("| `authority_crosscheck_2026-11-10.csv` |"))
        self.assertIn(f"{len(crosscheck_rows())}행", line)


if __name__ == "__main__":
    unittest.main()
