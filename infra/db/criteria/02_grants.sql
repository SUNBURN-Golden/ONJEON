-- criteria 스키마 권한: criteria_writer만 쓴다(삭제·수정 없음). 읽기는 지식 쓰기 역할과 개인 영역 서비스(적용 승인분 해석은 서비스 몫)에 연다.
REVOKE ALL ON SCHEMA criteria FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA criteria FROM PUBLIC, data_writer, knowledge_writer, criteria_writer, personal;
GRANT USAGE ON SCHEMA criteria TO criteria_writer, knowledge_writer, personal;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA criteria TO criteria_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA criteria TO knowledge_writer, personal;
