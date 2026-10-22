"""원장 O01(공제·우체국보험 포함 여부)이 D19·ADR-0018 §4로 이미 결정된 범위를 반영하는지 대조한다.

Audit 1 finding: `docs/blueprint/DECISIONS.md:52` O01 행은 아직 열린 질문으로 남아 있지만
ADR-0018 §4(우체국보험 포함·기관 유형 구분, 공제 제외·확보율 분모 제외)가 결정했고, 같은 ADR의
"결과" 절이 그 열린 결정을 명시적으로 닫는다. 원장은 이 finding을 낸 작업의 보호 문서라
고친 행은 docs/review/2026-10-23_audit1_decisions_o01.patch 로 두고 여기서 실제 원장과 대조한다.

시험은 원장의 두 상태에서 모두 통과한다.

* 미수정: O01 행이 패치의 `-` 행과 바이트 단위로 같고, 패치의 이전 블록이 원장에 그대로 있어
  아직 적용 가능하며, 패치의 `+` 행이 아래 "닫힌 행" 검사를 이미 만족한다.
* 수정됨: O01 행이 O13처럼 질문에 취소선을 넣고 D19·ADR-0018 §4·D11 구분과 확정 범위를 적는다.

그 밖의 상태(다른 문구로 바뀜, 행 중복, 열 수 변경, 패치가 더는 맞지 않음)는 실패한다.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
PATCH = ROOT / "docs/review/2026-10-23_audit1_decisions_o01.patch"
ADR_0018 = ROOT / "docs/decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md"

STRUCK_QUESTION = "~~공제·우체국보험의 포함 여부~~"
POST_INCLUDED = "우체국보험 포함(기관 유형 구분)"
MUTUAL_EXCLUDED = "공제 제외(확보율 분모에서도 제외)"
D11_NOTE = "전체 기관·소스 목록 작성 자체는 구현 작업(D11)"


def read(path):
    return path.read_text(encoding="utf-8")


def cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def only_row(lines, ident):
    rows = [line for line in lines if line.startswith(f"| {ident} |")]
    assert len(rows) == 1, f"원장에 {ident} 행이 정확히 하나 있어야 한다 (지금 {len(rows)}개)"
    return rows[0]


def patch_hunk():
    """패치의 유일한 hunk를 (이전 블록, 이후 블록, 지운 행들, 넣은 행들)로 돌려준다."""
    lines = read(PATCH).splitlines()
    assert lines[:2] == ["--- a/docs/blueprint/DECISIONS.md", "+++ b/docs/blueprint/DECISIONS.md"], \
        "패치는 원장 한 파일만 다뤄야 한다"
    assert lines[2].startswith("@@ ") and not any(l.startswith("@@ ") for l in lines[3:]), \
        "패치는 hunk 하나여야 한다"
    body = lines[3:]
    # 빈 문맥 행은 편집기가 뒤 공백을 지우면 " "가 아니라 ""로 남을 수 있다.
    context = [l[1:] if l else "" for l in body if l[:1] == " " or l == ""]
    assert context, "문맥 행이 없다"
    old = [l[1:] if l else "" for l in body if l[:1] in (" ", "-") or l == ""]
    new = [l[1:] if l else "" for l in body if l[:1] in (" ", "+") or l == ""]
    removed = [l[1:] for l in body if l.startswith("-")]
    added = [l[1:] for l in body if l.startswith("+")]
    return old, new, removed, added


def contiguous(block, lines):
    n = len(block)
    return any(lines[i:i + n] == block for i in range(len(lines) - n + 1))


def section(text, heading, next_heading):
    start = text.index(heading)
    end = text.index(next_heading, start)
    return text[start:end]


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


class O01Row(unittest.TestCase):
    """O01 행은 정확히 하나, 다섯 열이며 미수정 상태 아니면 닫힌 상태다."""

    def setUp(self):
        self.lines = read(LEDGER).splitlines()
        self.row = only_row(self.lines, "O01")
        self.old, self.new, self.removed, self.added = patch_hunk()

    def assert_closed(self, row, where):
        """O13 양식: 취소선 친 질문 → 결정 근거, 확정 범위, D11 구현 작업 구분, 오래된 후속 열 제거."""
        c = cells(row)
        self.assertEqual(5, len(c), f"{where}: 다섯 열 원장 양식을 지켜야 한다")
        self.assertTrue(c[1].startswith(STRUCK_QUESTION), f"{where}: 질문에 취소선을 넣고 시작해야 한다 (O13처럼)")
        self.assertIn("D19", c[1], where)
        self.assertIn("ADR-0018 §4", c[1], where)
        self.assertIn(POST_INCLUDED, c[1], where)
        self.assertIn(MUTUAL_EXCLUDED, c[1], where)
        self.assertIn(D11_NOTE, c[1], f"{where}: 전체 목록 작성이 구현 작업(D11)이라는 구분은 보존한다")
        self.assertEqual("제품 책임자", c[2], where)
        self.assertNotIn("M3 확장 전", c[3], f"{where}: 범위 결정은 이미 끝났다")
        self.assertIn("ADR-0018", c[3], f"{where}: 결정 시점은 ADR-0018로 적는다")
        self.assertNotIn("별도 분모로 조사", c[4], f"{where}: 공제는 확보율 분모에서 제외됐다")
        self.assertIn("우체국보험 포함", c[4], where)
        self.assertIn("공제", c[4], where)
        self.assertIn("분모 제외", c[4], where)

    def test_patch_replaces_exactly_the_o01_row(self):
        self.assertEqual(1, len(self.removed), "패치는 행 하나만 지운다")
        self.assertEqual(1, len(self.added), "패치는 행 하나만 넣는다")
        self.assertTrue(self.removed[0].startswith("| O01 |"))
        self.assertTrue(self.added[0].startswith("| O01 |"))
        self.assertEqual(5, len(cells(self.removed[0])))

    def test_patch_row_is_the_decided_scope(self):
        self.assert_closed(self.added[0], "패치의 + 행")

    def test_ledger_row_is_stale_or_closed(self):
        if self.row == self.removed[0]:
            # 미수정: 패치가 아직 그대로 적용돼야 하고, 적용 결과는 닫힌 행이어야 한다.
            self.assertTrue(contiguous(self.old, self.lines),
                            "원장 O01 주변이 바뀌어 패치가 더는 적용되지 않는다. 패치를 갱신하라")
            self.assert_closed(self.added[0], "패치의 + 행")
            self.assertNotIn(STRUCK_QUESTION, self.row)
        else:
            self.assert_closed(self.row, "원장 O01 행")

    def test_ledger_keeps_five_columns(self):
        self.assertEqual(5, len(cells(self.row)))


if __name__ == "__main__":
    unittest.main()
