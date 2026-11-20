# Audit 7 — 표본 행별 SHA-256 확인 후 보관·복원

`audit7-archive-samples-hash-before-put` · BLUEPRINT A1·Q7·L1·I6·M1 · 09 P02·P03

기준 코드에 두 쓰기 전 검증이 이미 적용돼 있다. `cmd_archive_samples`는 캐시를
한 번 읽고 해당 `samples.csv` 행의 SHA-256과 일치할 때만 같은 바이트를 저장한다.
`cmd_fetch`는 저장소에서 읽은 바이트를 직접 해시하고 해당 행과 다르면 복원
디렉터리 생성이나 파일 쓰기 전에 종료 코드 1을 반환한다.
[보관·복원 코드](../../../tools/source_archive.py).

## 회귀 검증

- `test_hash_differs_from_samples_csv_when_cached_originals_are_swapped`는 두 표본의
  캐시 파일을 맞바꾼다. 두 해시 모두 목록에 있지만 각 행의 기대값과 다르므로 종료
  코드 1과 각 행의 `hash_differs_from_samples_csv` 및 실제 해시를 확인한다. 원본,
  관측, 파생물을 담는 저장소 디렉터리도 생기지 않는다.
- `test_fetch_rejects_bytes_for_another_row_and_stops_before_later_rows`는 첫 표본의
  키에 다음 표본의 바이트를 넣는다. 종료 코드 1과 기대·실제 해시를 확인하고 복원
  경로가 생성되지 않으며 다음 표본의 정상 객체도 복원되지 않는지 검사한다.

[회귀 시험](../../../tools/tests/test_source_archive_commands.py).

두 시험에 각각 세 가지 변이를 적용해 6건 모두 assertion 실패로 검출했다. 검사
제거와 쓰기 뒤 이동은 기존 변이 도구를 재사용했다. 세 번째 변이는 행별 비교를
`digest not in {row["sha256"] for row in rows}`로 바꿨다. 변이는 메모리에서만
적용했고 원본과 복원 경로에는 합성 바이트를 사용했다.
[변이 도구](../../../tools/evidence/audit6-archive-verify-before-put/check_mutations.py).

| 실행 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 76개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,726개 실행, 1,720개 통과, 기존 건너뜀 6개 |
| `cargo test --all --locked --offline` | Rust 536개 통과, 기존 무시 1개 |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4개 통과 |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline --target-dir target/ontology-runner` | 4개 통과 |

Rust 1.98.1과 boto3 1.43.100을 사용했다. Python 전체 시험에는 작업 트리에서
빌드한 `ontology-case-runner`를 지정했다. 09 제품 목적 연결, 설계 묶음 119개
검사, V1 내부 일관성 및 변조 40개, 어휘와 온톨로지 검사도 통과했다.

이 기록은 보관 도구의 로컬 검증이다. 실제 공시 확보율, R2 관측 목록 대조,
트윈과 소비자 화면의 출시 판정은 09의 완료 증거를 따른다.
[제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
