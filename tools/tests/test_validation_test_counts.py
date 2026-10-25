"""Rust 시험 수를 말하는 문서가 단위·통합 테스트와 문서 시험(doctest)을 나눠 적는지 대조한다.

`cargo test`는 두 종류를 따로 센다. 합친 숫자만 적으면 한쪽만 세는 사람과 어긋난다
(Audit 1: `docs/BLUEPRINT.md` §11 "Rust 테스트 42개" = 테스트 39 + 문서 시험 3).
1차 근거는 docs/blueprint/validation/evidence/audit1_blueprint_test_count/ 의 `cargo test --workspace` 재실행 로그.
그 요약 행은 docs/blueprint/validation/REVERIFY_87a19c5.md, 수정 검증 기록은
docs/blueprint/validation/REVERIFY_AUDIT1_BLUEPRINT_TEST_COUNT.md.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVERIFY = ROOT / "docs/blueprint/validation/REVERIFY_87a19c5.md"
VALIDATION_README = ROOT / "docs/blueprint/validation/README.md"
VERIFICATION_RECORD = ROOT / "docs/blueprint/validation/REVERIFY_AUDIT1_BLUEPRINT_TEST_COUNT.md"
EVIDENCE = ROOT / "docs/blueprint/validation/evidence/audit1_blueprint_test_count"
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"

# The two 2026-10-09 commits the §11 number comes from: 87a19c5 (REVERIFY subject), 839ecdb (wrote §11).
COMMITS = ("87a19c5", "839ecdb")

BARE = re.compile(r"Rust 테스트 (\d+)개")
SPLIT = re.compile(r"테스트 (\d+)개 \+ 문서 시험\(doctest\) (\d+)개")
RUNNING = re.compile(r"^\s+Running (?:unittests )?(\S+) \(")
DOC_TESTS = re.compile(r"^\s+Doc-tests (\S+)")
RESULT = re.compile(r"^test result: (\w+)\. (\d+) passed; (\d+) failed; ")


def read(path):
    return path.read_text(encoding="utf-8")


def reverify_split():
    """(tests, doctests, total) as written in the CI row of the re-verification record."""
    m = re.search(SPLIT.pattern + r" = (\d+)건", read(REVERIFY))
    assert m, "REVERIFY CI row must split tests from doctests"
    return tuple(map(int, m.groups()))


def parse_log(path):
    """Read a `cargo test --workspace` log.

    Returns a dict: binaries {'src/lib.rs' | 'tests/x.rs': passed}, doctests {crate: passed},
    results [(status, failed)] for every `test result:` line, exit_code (int or None).
    """
    out = {"binaries": {}, "doctests": {}, "results": [], "exit_code": None}
    target = None
    for line in read(path).splitlines():
        if m := RUNNING.match(line):
            target = ("binaries", m.group(1))
        elif m := DOC_TESTS.match(line):
            target = ("doctests", m.group(1))
        elif m := RESULT.match(line):
            status, passed, failed = m.group(1), int(m.group(2)), int(m.group(3))
            out["results"].append((status, failed))
            assert target, f"{path.name}: `test result:` without a Running/Doc-tests header"
            kind, name = target
            out[kind][name] = out[kind].get(name, 0) + passed
            target = None
        elif m := re.match(r"^exit code: (\d+)$", line):
            out["exit_code"] = int(m.group(1))
    return out


def section(text, number):
    start = text.index(f"\n## {number}. ")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else None]


class EvidenceLogs(unittest.TestCase):
    """The 39 + 3 claim is only as good as the re-run logs that back it."""

    def setUp(self):
        self.logs = {c: EVIDENCE / f"cargo_test_{c}.log" for c in COMMITS}
        for c, path in self.logs.items():
            self.assertTrue(path.is_file(), f"missing re-run log for {c}: {path}")

    def test_logs_record_the_command_and_a_clean_exit(self):
        for c, path in self.logs.items():
            text = read(path)
            self.assertIn(f"$ git archive {c}", text, c)
            self.assertIn("$ cargo test --workspace", text, c)
            self.assertEqual(parse_log(path)["exit_code"], 0, c)

    def test_every_section_passed(self):
        for c, path in self.logs.items():
            results = parse_log(path)["results"]
            self.assertGreaterEqual(len(results), 2, f"{c}: expected test binaries and doctests")
            self.assertEqual({r for r in results}, {("ok", 0)}, c)

    def test_split_matches_reverify_row(self):
        tests, docs, total = reverify_split()
        for c, path in self.logs.items():
            log = parse_log(path)
            self.assertEqual(sum(log["binaries"].values()), tests, f"{c}: unit+integration tests")
            self.assertEqual(sum(log["doctests"].values()), docs, f"{c}: doctests")
            self.assertEqual(list(log["doctests"]), ["onjeon_rules_engine"], c)
        self.assertEqual(tests + docs, total)

    def test_both_commits_agree_per_binary(self):
        a, b = (parse_log(self.logs[c])["binaries"] for c in COMMITS)
        self.assertEqual(a, b)

    def test_logs_carry_no_machine_paths(self):
        for c, path in self.logs.items():
            self.assertNotRegex(read(path), r"/home/|/tmp/|/workspace/", c)


class ReverifyRecord(unittest.TestCase):
    def setUp(self):
        self.text = read(REVERIFY)

    def test_no_bare_combined_count(self):
        self.assertNotRegex(self.text, BARE)

    def test_breakdown_adds_up(self):
        tests, docs, total = reverify_split()
        self.assertEqual(tests + docs, total)

    def test_rerun_is_not_passed_off_as_ci_log(self):
        row = next(l for l in self.text.splitlines() if l.startswith("| 일반 CI |"))
        self.assertIn("재실행 값", row)
        self.assertIn("이 저장소에 없", row)
        self.assertIn(EVIDENCE.name + "/", row)


class VerificationRecord(unittest.TestCase):
    def setUp(self):
        self.text = read(VERIFICATION_RECORD)

    def test_corrected_wording_matches_reverify(self):
        tests, docs, _ = reverify_split()
        quoted = " ".join(l for l in self.text.splitlines() if l.startswith("> "))
        self.assertTrue(quoted, "verification record must quote the corrected wording")
        m = SPLIT.search(quoted)
        self.assertIsNotNone(m, "corrected wording must split tests from doctests")
        self.assertEqual(tuple(map(int, m.groups())), (tests, docs))
        self.assertNotRegex(quoted, BARE)

    def test_per_binary_table_matches_logs(self):
        rows = re.findall(r"^\| `((?:src|tests)/[^`]+)`[^|]*\| (\d+) \|$", self.text, re.M)
        table = {name: int(n) for name, n in rows}
        self.assertGreaterEqual(len(table), 2, "re-run table must list the test binaries")
        for c in COMMITS:
            self.assertEqual(table, parse_log(EVIDENCE / f"cargo_test_{c}.log")["binaries"], c)
        _, docs, _ = reverify_split()
        self.assertRegex(self.text, rf"문서 시험\(doctest\) {docs}개")

    def test_points_at_sources(self):
        for needle in ("REVERIFY_87a19c5.md", "docs/BLUEPRINT.md", "318행", "test_validation_test_counts.py",
                       EVIDENCE.name + "/", *(f"cargo_test_{c}.log" for c in COMMITS)):
            self.assertIn(needle, self.text)


class ValidationReadme(unittest.TestCase):
    def test_points_at_verification_record(self):
        self.assertIn(VERIFICATION_RECORD.name, read(VALIDATION_README))


class Blueprint(unittest.TestCase):
    """The §11 row must split tests from doctests and agree with the re-run evidence."""

    def setUp(self):
        rows = [l for l in section(read(BLUEPRINT), 11).splitlines() if l.startswith("| 코드 |")]
        self.assertEqual(len(rows), 1, "§11 must have exactly one 코드 row")
        self.code_row = rows[0]

    def test_count_agrees_with_split_evidence(self):
        tests, docs, _ = reverify_split()
        self.assertNotRegex(self.code_row, BARE, "combined count hides the doctest split")
        m = SPLIT.search(self.code_row)
        self.assertIsNotNone(m, "§11 code row must state tests + doctests")
        self.assertEqual(tuple(map(int, m.groups())), (tests, docs))

    def test_count_has_a_historical_date_and_evidence(self):
        self.assertIn("2026-10-09 기준", self.code_row)
        self.assertIn("재실행 근거", self.code_row)
        self.assertIn("blueprint/validation/REVERIFY_87a19c5.md", self.code_row)

    def test_states_the_count_once(self):
        self.assertEqual(len(BARE.findall(self.code_row)) + len(SPLIT.findall(self.code_row)), 1)


if __name__ == "__main__":
    unittest.main()
