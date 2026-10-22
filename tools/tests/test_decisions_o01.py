"""원장 O01(공제·우체국보험 포함 여부)이 D19·ADR-0018 §4로 이미 결정된 범위를 반영하는지 대조한다.

Audit 1 finding: `docs/blueprint/DECISIONS.md:52` O01 행은 아직 열린 질문으로 남아 있지만
ADR-0018 §4(우체국보험 포함·기관 유형 구분, 공제 제외·확보율 분모 제외)가 결정했고, 같은 ADR의
"결과" 절이 그 열린 결정을 명시적으로 닫는다. 원장은 이 finding을 낸 작업의 보호 문서라
고친 행은 docs/review/2026-10-23_audit1_decisions_o01.patch 로 두고 여기서 실제 원장과 대조한다.

시험은 원장의 두 상태에서 모두 통과한다.

* 미수정: 패치 파일이 아직 있고, O01 행이 패치의 `-` 행과 바이트 단위로 같고, 패치의 이전 블록이
  원장에 그대로 있어 아직 적용 가능하며, 패치의 `+` 행이 아래 "닫힌 행" 검사를 이미 만족한다.
* 수정됨: O01 행이 O13처럼 질문에 취소선을 넣고 D19·ADR-0018 §4·D11 구분과 확정 범위를 적는다.

그 밖의 상태(다른 문구로 바뀜, 행 중복, 열 수 변경, 패치가 더는 맞지 않음)는 실패한다.
원장을 닫는 라운드는 패치를 적용한 뒤 패치 파일을 지운다. 패치가 없으면 미수정 상태는 더는
허용되지 않으므로 원래 열린 질문으로 되돌아가는 회귀도 실패한다. 패치가 없을 때 패치를 읽는
시험들은 skip 대신 "원장 O01 행이 닫혀 있다"는 검사로 바뀐다.

닫힌 상태의 검사는 실제 원장에만 기대지 않는다. 매 실행마다 패치를 원장 사본에 적용해 그 결과가
닫힌 행 검사를 만족하는지, 원래 행이 닫힌 행 검사에 실패하는지, 제3의 문구가 두 상태 모두에서
거부되는지를 CI에서 함께 확인한다.
"""
import functools
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
PATCH = ROOT / "docs/review/2026-10-23_audit1_decisions_o01.patch"
ADR_0018 = ROOT / "docs/decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md"

OPEN_QUESTION = "공제·우체국보험의 포함 여부"
STRUCK_QUESTION = f"~~{OPEN_QUESTION}~~"
POST_INCLUDED = "우체국보험 포함(기관 유형 구분)"
MUTUAL_EXCLUDED = "공제 제외(확보율 분모에서도 제외)"
D11_NOTE = "전체 기관·소스 목록 작성 자체는 구현 작업(D11)"
STALE_TIMING = "M3 확장 전"
STALE_RULE = "별도 분모로 조사"


def read(path):
    return path.read_text(encoding="utf-8")


def cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def only_row(lines, ident):
    rows = [line for line in lines if line.startswith(f"| {ident} |")]
    if len(rows) != 1:
        raise AssertionError(f"원장에 {ident} 행이 정확히 하나 있어야 한다 (지금 {len(rows)}개)")
    return rows[0]


def patch_hunk():
    """패치의 유일한 hunk를 (이전 블록, 이후 블록, 지운 행들, 넣은 행들)로 돌려준다."""
    lines = read(PATCH).splitlines()
    if lines[:2] != ["--- a/docs/blueprint/DECISIONS.md", "+++ b/docs/blueprint/DECISIONS.md"]:
        raise AssertionError("패치는 원장 한 파일만 다뤄야 한다")
    if not lines[2].startswith("@@ ") or any(l.startswith("@@ ") for l in lines[3:]):
        raise AssertionError("패치는 hunk 하나여야 한다")
    body = lines[3:]
    # 빈 문맥 행은 편집기가 뒤 공백을 지우면 " "가 아니라 ""로 남을 수 있다.
    context = [l[1:] if l else "" for l in body if l[:1] == " " or l == ""]
    if not context:
        raise AssertionError("문맥 행이 없다")
    old = [l[1:] if l else "" for l in body if l[:1] in (" ", "-") or l == ""]
    new = [l[1:] if l else "" for l in body if l[:1] in (" ", "+") or l == ""]
    removed = [l[1:] for l in body if l.startswith("-")]
    added = [l[1:] for l in body if l.startswith("+")]
    return old, new, removed, added


def occurrences(block, lines):
    n = len(block)
    return [i for i in range(len(lines) - n + 1) if lines[i:i + n] == block]


def contiguous(block, lines):
    return bool(occurrences(block, lines))


def apply_hunk(lines, old, new):
    """이전 블록이 정확히 한 번 나오는 자리에 이후 블록을 넣은 사본을 돌려준다 (git apply와 같은 결과)."""
    hits = occurrences(old, lines)
    if len(hits) != 1:
        raise AssertionError(f"패치의 이전 블록이 원장에 정확히 한 번 있어야 한다 (지금 {len(hits)}번)")
    i = hits[0]
    return lines[:i] + new + lines[i + len(old):]


def section(text, heading, next_heading):
    start = text.index(heading)
    end = text.index(next_heading, start)
    return text[start:end]


def assert_closed(tc, row, where):
    """O13 양식: 취소선 친 질문 → 결정 근거, 확정 범위, D11 구현 작업 구분, 오래된 후속 열 제거."""
    c = cells(row)
    tc.assertEqual(5, len(c), f"{where}: 다섯 열 원장 양식을 지켜야 한다")
    tc.assertTrue(c[1].startswith(STRUCK_QUESTION), f"{where}: 질문에 취소선을 넣고 시작해야 한다 (O13처럼)")
    tc.assertIn("D19", c[1], where)
    tc.assertIn("ADR-0018 §4", c[1], where)
    tc.assertIn(POST_INCLUDED, c[1], where)
    tc.assertIn(MUTUAL_EXCLUDED, c[1], where)
    tc.assertIn(D11_NOTE, c[1], f"{where}: 전체 목록 작성이 구현 작업(D11)이라는 구분은 보존한다")
    tc.assertEqual("제품 책임자", c[2], where)
    tc.assertNotIn(STALE_TIMING, c[3], f"{where}: 범위 결정은 이미 끝났다")
    tc.assertIn("ADR-0018", c[3], f"{where}: 결정 시점은 ADR-0018로 적는다")
    tc.assertNotIn(STALE_RULE, c[4], f"{where}: 공제는 확보율 분모에서 제외됐다")
    tc.assertIn("우체국보험 포함", c[4], where)
    tc.assertIn("공제", c[4], where)
    tc.assertIn("분모 제외", c[4], where)


def without_patch_require_closed(test):
    """패치 파일이 없으면(원장을 닫은 뒤) 패치 기반 시험은 원장 O01 행이 닫혔는지만 본다. skip이 아니다."""
    @functools.wraps(test)
    def wrapper(self):
        if PATCH.exists():
            return test(self)
        assert_closed(self, only_row(read(LEDGER).splitlines(), "O01"), "원장 O01 행(패치 없음)")
    return wrapper


def check_state(tc, lines, old, removed, added, patch_present):
    """원장(또는 그 사본)의 O01 행이 어느 상태인지 판정한다. 'open' 또는 'closed'; 그 밖에는 실패."""
    row = only_row(lines, "O01")
    tc.assertEqual(5, len(cells(row)), "O01 행은 다섯 열이어야 한다")
    if patch_present and row == removed[0]:
        # 미수정: 패치가 아직 그대로 적용돼야 하고, 적용 결과는 닫힌 행이어야 한다.
        tc.assertTrue(contiguous(old, lines), "원장 O01 주변이 바뀌어 패치가 더는 적용되지 않는다. 패치를 갱신하라")
        assert_closed(tc, added[0], "패치의 + 행")
        tc.assertNotIn(STRUCK_QUESTION, row)
        return "open"
    assert_closed(tc, row, "원장 O01 행")
    return "closed"


class Premise(unittest.TestCase):
    """O01이 묻는 것은 ADR-0018에 기록된 사용자 결정이 이미 답했고, 원장 D19가 그대로 옮겼다."""

    def test_d19_records_the_decided_scope(self):
        d19 = only_row(read(LEDGER).splitlines(), "D19")
        self.assertIn("우체국보험(기관 유형 구분)", d19)
        self.assertIn("공제(분모에서도 제외)", d19)
        self.assertIn("ADR-0018", d19)

    def test_adr_0018_section_4_decides_both_institution_types(self):
        scope = section(read(ADR_0018), "### 4. 포괄 범위", "### 5. ")
        self.assertRegex(scope, r"(?m)^\| 우체국보험 \| \*\*포함\.\*\* .*기관 유형은 구분")
        self.assertRegex(scope, r"(?m)^\| 공제 \| \*\*제외\.\*\* .*확보율 분모에서도 제외")

    def test_adr_0018_closes_the_open_question(self):
        self.assertIn('열린 결정 "공제·우체국보험 포함 여부"를 닫는다', read(ADR_0018))


class PatchFile(unittest.TestCase):
    """커밋된 패치 자체: 원장 한 파일, hunk 하나, O01 한 행 교체. `-` 행은 감사가 지적한 문구, `+` 행은 닫힌 행."""

    def setUp(self):
        self.old, self.new, self.removed, self.added = patch_hunk() if PATCH.exists() else ([], [], [], [])

    @without_patch_require_closed
    def test_patch_replaces_exactly_the_o01_row(self):
        self.assertEqual(1, len(self.removed), "패치는 행 하나만 지운다")
        self.assertEqual(1, len(self.added), "패치는 행 하나만 넣는다")
        self.assertTrue(self.removed[0].startswith("| O01 |"))
        self.assertTrue(self.added[0].startswith("| O01 |"))
        self.assertEqual(5, len(cells(self.removed[0])))

    @without_patch_require_closed
    def test_patch_removes_the_audited_wording(self):
        stale = cells(self.removed[0])
        self.assertTrue(stale[1].startswith(OPEN_QUESTION), "패치가 지우는 행은 감사가 지적한 열린 질문이어야 한다")
        self.assertEqual(STALE_TIMING, stale[3])
        self.assertIn(STALE_RULE, stale[4])

    @without_patch_require_closed
    def test_patch_row_is_the_decided_scope(self):
        assert_closed(self, self.added[0], "패치의 + 행")

    @without_patch_require_closed
    def test_stale_row_fails_the_closed_checks(self):
        with self.assertRaises(self.failureException):
            assert_closed(self, self.removed[0], "패치의 - 행")


class LedgerCopyAfterPatch(unittest.TestCase):
    """패치를 원장 사본에 적용한 결과를 매 실행마다 검사한다 (닫힌 상태의 CI 검증)."""

    def setUp(self):
        self.lines = read(LEDGER).splitlines()
        if not PATCH.exists():
            return
        self.old, self.new, self.removed, self.added = patch_hunk()
        self.open = contiguous(self.old, self.lines)
        self.applied = apply_hunk(self.lines, self.old, self.new) if self.open else list(self.lines)

    @without_patch_require_closed
    def test_applied_copy_is_closed(self):
        self.assertEqual("closed", check_state(self, self.applied, self.old, self.removed, self.added, patch_present=True))
        self.assertNotIn(self.removed[0], self.applied)

    @without_patch_require_closed
    def test_applied_copy_changes_only_the_o01_row(self):
        self.assertEqual(len(self.lines), len(self.applied), "패치는 행 수를 바꾸지 않는다")
        diffs = [i for i, (a, b) in enumerate(zip(self.lines, self.applied)) if a != b]
        if self.open:
            self.assertEqual(1, len(diffs), "패치는 원장에서 정확히 한 행만 바꾼다")
            self.assertEqual(self.removed[0], self.lines[diffs[0]])
            self.assertEqual(self.added[0], self.applied[diffs[0]])
        else:
            self.assertEqual([], diffs, "원장이 이미 닫혔으면 사본은 원장과 같다")

    @without_patch_require_closed
    def test_stale_row_is_rejected_once_the_patch_is_gone(self):
        """닫는 라운드가 패치를 지운 뒤에는 원래 열린 질문으로 되돌리는 회귀가 실패한다."""
        self.assertTrue(self.added[0] in self.applied, "패치 적용 사본에 닫힌 O01 행이 있어야 한다")
        reopened = [self.removed[0] if line == self.added[0] else line for line in self.applied]
        with self.assertRaises(self.failureException):
            check_state(self, reopened, self.old, self.removed, self.added, patch_present=False)

    @without_patch_require_closed
    def test_reworded_row_is_rejected_in_both_states(self):
        """질문만 바꿔 쓴 제3의 문구는 패치 유무와 무관하게 실패한다."""
        reworded = self.removed[0].replace(OPEN_QUESTION, "공제·우체국보험 포함 여부 재검토", 1)
        self.assertNotEqual(reworded, self.removed[0])
        self.assertTrue(self.added[0] in self.applied, "패치 적용 사본에 닫힌 O01 행이 있어야 한다")
        tampered = [reworded if line == self.added[0] else line for line in self.applied]
        for patch_present in (True, False):
            with self.assertRaises(self.failureException):
                check_state(self, tampered, self.old, self.removed, self.added, patch_present)

    @without_patch_require_closed
    def test_duplicate_o01_row_is_rejected(self):
        self.assertTrue(self.added[0] in self.applied, "패치 적용 사본에 닫힌 O01 행이 있어야 한다")
        duplicated = list(self.applied)
        duplicated.insert(duplicated.index(self.added[0]) + 1, self.added[0])
        with self.assertRaises(self.failureException):
            check_state(self, duplicated, self.old, self.removed, self.added, patch_present=True)


class O01Row(unittest.TestCase):
    """실제 원장의 O01 행은 정확히 하나, 다섯 열이며 미수정 상태 아니면 닫힌 상태다."""

    def setUp(self):
        self.lines = read(LEDGER).splitlines()
        self.row = only_row(self.lines, "O01")
        self.old, self.new, self.removed, self.added = patch_hunk() if PATCH.exists() else ([], [], [""], [""])

    def test_ledger_row_is_stale_or_closed(self):
        state = check_state(self, self.lines, self.old, self.removed, self.added, PATCH.exists())
        self.assertIn(state, ("open", "closed"))

    def test_ledger_keeps_five_columns(self):
        self.assertEqual(5, len(cells(self.row)))

    def test_closed_ledger_does_not_keep_the_stale_wording(self):
        """원장이 닫혔으면 오래된 시점·임시 규칙은 사라졌어야 한다. 미수정이면 패치의 + 행에서 같은 것을 확인한다."""
        target = self.added[0] if (PATCH.exists() and self.row == self.removed[0]) else self.row
        self.assertNotIn(STALE_TIMING, target)
        self.assertNotIn(STALE_RULE, target)


if __name__ == "__main__":
    unittest.main()
