-- 공개 영역 DB 역할 4종(I12). 로그인 없는 그룹 역할이다: 서비스 계정은 이 역할의 구성원으로 만든다(README).
-- 역할은 클러스터 전역이다. 이미 있으면 건너뛴다. 비밀값·비밀번호는 이 파일에 없다.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['data_writer', 'knowledge_writer', 'criteria_writer', 'personal'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', r);
    END IF;
  END LOOP;
END $$;
