-- 공개 영역 권한 (I12). 기본 권한을 모두 닫고 역할마다 필요한 것만 연다. DELETE·TRUNCATE는 누구에게도 주지 않는다.
-- 쓰기 주체: data_writer = 수집·복원·구획(관측), knowledge_writer = 판단(주장·검수 결정·릴리스).
-- personal 역할은 공개 지식을 읽을 수만 있고 쓸 수 없다. 이 파일은 criteria 스키마 적용 전에도 후에도 다시 실행할 수 있다.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, data_writer, knowledge_writer, criteria_writer, personal;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO data_writer, knowledge_writer, criteria_writer, personal;
-- 트리거 함수가 호출자 권한으로 돌므로 쓰기 역할에는 검사에 필요한 함수 실행 권한이 있어야 한다.
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO data_writer, knowledge_writer, criteria_writer, personal;

-- 수집·복원: 관측, 구획, 조항, 원시 가격 관측, 공백, 확보 작업.
GRANT SELECT, INSERT ON raw_asset, observation, document_segment, clause, premium_observation, gap TO data_writer;
GRANT SELECT, INSERT, UPDATE ON acquisition_task TO data_writer;
GRANT SELECT ON terms_edition, terms_lineage, node, assertion, review_decision, conflict, conflict_member, code_system, release_manifest TO data_writer;

-- 판단: 본문 판·계열, 노드, 코드 체계, 주장, 검수 결정, 충돌, 릴리스. 가격 비교 자격(accepted)은 검수 결정이 있는 새 행으로 넣는다.
GRANT SELECT, INSERT ON terms_edition, terms_lineage, node, code_system, review_decision, assertion, premium_observation,
                        conflict, conflict_member, gap, release_manifest TO knowledge_writer;
GRANT UPDATE (superseded_by, withdrawn_at, withdrawal_reason) ON release_manifest TO knowledge_writer;   -- 철회·대체 표시만
GRANT SELECT, INSERT, UPDATE ON acquisition_task TO knowledge_writer;
GRANT SELECT ON raw_asset, observation, document_segment, clause TO knowledge_writer;

-- 개인 영역 서비스: 공개 지식 읽기 전용. 원본·관측·검수 결정·확보 작업은 읽지 못한다.
GRANT SELECT ON release_manifest, terms_edition, terms_lineage, node, clause, document_segment, assertion,
                premium_observation, conflict, conflict_member, gap, code_system TO personal;

-- 임시 테이블로 가드 함수가 읽는 표를 가리지 못하게 한다(가드 함수도 search_path를 고정한다).
DO $$ BEGIN EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database()); END $$;
