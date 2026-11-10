"""감리 지적 상태를 메모리에서 재현해 README 회귀 시험이 검출하는지 확인한다.

실제 README 파일은 바꾸지 않는다. 저장소 루트에서 실행한다.
"""
import re
import sys
import unittest

sys.path.insert(0, "tools/tests")
import test_readme_index as m  # noqa: E402

OLD_PRIORITY = (
    "우선순위는 불변 원칙 → 제2부 → 제3부 → 제1부 순이다. "
    "제3부 §56의 사용자 결정은 이 순서보다 우선한다."
)
CURRENT_PRIORITY = (
    "문서 간 우선순위와 사용자 결정의 적용은 "
    "[BLUEPRINT §0.1 문서 위계](docs/BLUEPRINT.md#01-문서-위계)를 따른다."
)


def truncate_adr_list(text):
    decisions = m.row("docs/decisions/", text)
    cut = re.sub(r", 0012 .*?(?=\. 결정 기록)", "", decisions)
    assert cut != decisions and "0012" not in cut and "0011 설계도 채택" in cut
    return text.replace(decisions, cut)


def drop_dec_families(text):
    decisions = m.row("docs/decisions/", text)
    cut = decisions.replace(
        "`DEC-D-xx`·`DEC-Oxx`, `DEC-CANON-*`, 묶음 상태 `DEC-BUNDLE-STATUS`", ""
    )
    assert cut != decisions and "DEC-D-xx" not in cut
    return text.replace(decisions, cut)


def restore_old_priority(text):
    assert CURRENT_PRIORITY in text
    return text.replace(CURRENT_PRIORITY, OLD_PRIORITY)


def append_old_priority(text):
    assert CURRENT_PRIORITY in text
    return text.replace(CURRENT_PRIORITY, f"{CURRENT_PRIORITY} {OLD_PRIORITY}")


MUTATIONS = (
    (
        "ADR 목록을 0011까지만 남김",
        truncate_adr_list,
        [(m.DecisionsRow, "test_every_adr_number_is_listed")],
    ),
    (
        "DEC 기록 계열 안내를 지움",
        drop_dec_families,
        [(m.DecisionsRow, "test_dec_record_families_are_named_and_cover_every_record")],
    ),
    (
        "감사 당시 우선순위 복원",
        restore_old_priority,
        [
            (m.DocumentHierarchy, "test_priority_points_to_blueprint_section_0_1"),
            (m.DocumentHierarchy, "test_replaced_masterplan_priority_is_not_present"),
        ],
    ),
    (
        "BLUEPRINT 링크 유지 중에도 옛 우선순위 재삽입",
        append_old_priority,
        [(m.DocumentHierarchy, "test_replaced_masterplan_priority_is_not_present")],
    ),
)


def main():
    failed = False
    for label, mutate, cases in MUTATIONS:
        original = m.README
        m.README = mutate(original)
        suite = unittest.TestSuite(
            [case(name) for case, name in cases]
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        m.README = original
        detected = {
            test.id().rsplit(".", 1)[-1].split(" ", 1)[0]
            for test, _ in result.failures
        }
        expected = {name for _, name in cases}
        ok = not result.wasSuccessful() and detected == expected
        print(
            f"{label}: {len(cases)}개 실행, 실패 {len(result.failures)}건, "
            f"검출 {sorted(detected)}, 판정 {'OK' if ok else 'MISMATCH'}"
        )
        failed = failed or not ok
    print("모든 변이 검출 성공. README 파일 변경 없음." if not failed else "변이 검출 실패")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
