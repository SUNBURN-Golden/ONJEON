-- 개인 영역 DB 역할. 공개 영역과 같은 네 이름을 쓰되(클러스터가 같을 때 중복 없이 재사용), 이 DB에서 권한을 갖는 것은 personal뿐이다.
-- 비밀값·비밀번호는 이 파일에 없다.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['data_writer', 'knowledge_writer', 'criteria_writer', 'personal'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', r);
    END IF;
  END LOOP;
END $$;
