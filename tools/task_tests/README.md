# 제품 과제별 필수 ID 시험

`tasks.json`의 모든 제품 과제(T-OP-00·T-OP-09 제외)는 다음 명령을
`tests`와 개별 `done_criteria`에 가진다. 감독 실행기가 `시험 …` 설명을
건너뛰어도 이 명령은 실행해야 한다.

```sh
python3 -I tools/task_test_coverage.py --task T-AP-02
```

필수 ID가 있으면 과제 구현자가 `tools/task_tests/T-AP-02/coverage.py`를
제품 구현과 함께 작성한다. 이 과제별 경로는 수정 허용·충돌 경로에 포함된다.
파일은 Python 표준 라이브러리의 unittest를 사용하며 다음 구조를 따른다.

```python
import unittest

TEST_IDS = [
    ("decisive-conditions-not-hidden", "CoverageContract.test_decisive_conditions"),
]

class CoverageContract(unittest.TestCase):
    def test_decisive_conditions(self):
        # 실제 API 응답과 조건 제거 변이에 대한 계약 검증을 구현한다.
        # 이 문서의 예시는 실행용 성공 시험이 아니다.
        raise NotImplementedError("제품 계약 검증을 구현해야 한다")
```

등록은 리터럴 목록이며 ID별로 이 파일에 정의된 `TestCase.test_method`를
하나씩 가리킨다. 서로 다른 ID를 같은 메서드에 배정할 수 없다. 별칭
(`test_b = test_a`), 클래스 생성 후 대입, 상속으로 같은 함수를 가리키는
등록도 이름이 달라도 같은 구현의 재사용이므로 거부한다. 한 메서드는
필요한 정상·음성·변이 사례를 `subTest` 등으로 함께 검사할 수 있다.
네이티브 Rust·Flutter·웹 시험은 이 메서드에서 어댑터로 실행할 수 있다.
어댑터는 필터에 맞는 시험이 실제로 실행됐는지(0개 통과 금지), 종료 코드,
실패·skip과 필요한 결과·캡처를 검증해야 한다. 단순 명령 실행·종료 코드 0만으로
제품 요구 의미가 검증되는 것은 아니다. 실제 사례와 변이 검출은 리뷰 대상이다.

필수 ID 목록과 등록이 정확히 같아야 실행한다. 등록 파일·함수 부재,
누락·미등록·중복 ID, 재사용 메서드(별칭·상속 포함), 실행 실패·오류·skip·expectedFailure,
실행 개수 불일치, unittest assertion을 한 번도 호출하지 않은 빈 시험은 종료 코드 1이다.
assertion은 등록된 시험 메서드 실행 중에 호출해야 하며, `setUp`·`tearDown`·cleanup
픽스처의 assertion은 빈 메서드를 통과시키지 않는다.
어댑터도 `self.assertEqual`·`self.assertTrue` 등 unittest assertion으로 결과를 검사한다. 실행기에서 일부 ID만 선택하는 기능은 없다.
필수 ID가 빈 목록이면 그 사실을 출력한다. ID를 추가하면 등록 파일이 없는
경우부터 실패한다. ID 없는 `시험 …` 설명도 실패한다.

수동 수행 과제의 시험은 실제 측정·점검·사용자 시험·운영 기록의 내용과
사전 수락 기준을 검증한다. 검증 시험 자체가 실제 수행, 정책 결정, 승인,
사용자 시험 결과를 대신하지 않는다. 해당 결정 관문은 그대로 적용된다.

G12c와 CI 회귀 시험은 모든 과제에 이 의무가 들어 있는지 검사한다.
이는 아직 수행하지 않은 제품 과제의 시험 결과를 통과로 만드는 검사가 아니다.
현재 미구현 과제에 빈 등록 파일이나 성공 대역 시험을 만들지 않는다.
제품 완료 증거는 계속 09_제품목적_대응표를 따른다.
