-- 기존 릴리스 식별자를 보존하면서 엔진 빌드 메타데이터(+snapshot-json-1)를 허용한다.
ALTER TABLE public.release_manifest
    DROP CONSTRAINT release_manifest_engine_version_check,
    ADD CONSTRAINT chk_release_engine_version
        CHECK (engine_version ~ '^[A-Za-z0-9._-]+([+][A-Za-z0-9.-]+)?$');
