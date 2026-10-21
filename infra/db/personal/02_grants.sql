-- 개인 영역 권한 (I12): 이 DB의 테이블에 접근하는 역할은 personal뿐이다. 공개 쓰기 역할(data_writer·knowledge_writer·criteria_writer)은 접속은 못 막아도 읽기·쓰기가 모두 막힌다.
REVOKE ALL ON SCHEMA personal FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA personal FROM PUBLIC, data_writer, knowledge_writer, criteria_writer, personal;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA personal FROM PUBLIC;

GRANT USAGE ON SCHEMA public, personal TO personal;   -- public에는 어휘 도메인만 있다(테이블 없음)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA personal TO personal;
GRANT SELECT, INSERT, UPDATE, DELETE ON personal.profile, personal.consent, personal.upload, personal.contract_snapshot, personal.user_assumption,
      personal.evaluation, personal.conclusion_dependency, personal.plan TO personal;
-- 삭제 작업 표는 보존한다: 삭제(DELETE) 권한이 없다.
GRANT SELECT, INSERT, UPDATE ON personal.deletion_job TO personal;
