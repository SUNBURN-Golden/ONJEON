-- 개인 영역 DB 스키마 (T-CT-05, 02_구현계약 §1.4~§1.6·§7). 공개 영역 DB와 다른 DB에 둔다(I12).
-- 이 DB의 행은 private_policy 이상 민감도다: 공개 DB·캐시·릴리스·로그로 나가지 못한다. 공개 지식은 release_id·ID로만 참조하고 복제하지 않는다.
-- PDF 비밀번호를 담는 열은 없다(메모리에서만, 처리 직후 폐기). 신고 자유 입력 격리 테이블은 이 과제 범위 밖이다.
CREATE SCHEMA personal;

-- 어휘 도메인 (정본: packages/schemas/vocabulary.json; tests/test_vocab_sync.py가 대조)
CREATE DOMAIN vocab_fact_source AS text CHECK (VALUE IN ('pdf_extracted', 'user_stated', 'user_confirmed_extract', 'assumed', 'release_derived'));
CREATE DOMAIN vocab_fact_kind AS text CHECK (VALUE IN ('actual', 'hypothetical'));
CREATE DOMAIN vocab_confirm_party AS text CHECK (VALUE IN ('user', 'insurer', 'document', 'none'));
CREATE DOMAIN vocab_contract_version_match AS text CHECK (VALUE IN ('matched', 'ambiguous', 'unmatched'));
CREATE DOMAIN vocab_freshness AS text CHECK (VALUE IN ('fresh', 'stale'));
CREATE DOMAIN vocab_knowledge_freshness AS text CHECK (VALUE IN ('fresh', 'stale', 'withdrawn'));
CREATE DOMAIN vocab_usage_restriction AS text CHECK (VALUE IN ('none', 'hold', 'circuit_breaker'));
CREATE DOMAIN vocab_sensitivity AS text CHECK (VALUE IN ('public_product', 'private_policy', 'private_health', 'genetic_private'));
CREATE DOMAIN vocab_plan_action AS text CHECK (VALUE IN ('keep', 'add', 'remove', 'modify'));

-- JSON 목록의 각 원소가 object이고, 지정한 키가 어휘 도메인 값인지 확인한다(잘못된 값이면 도메인 위반으로 거부).
CREATE FUNCTION personal.components_valid(c jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE e jsonb;
BEGIN
  IF jsonb_typeof(c) <> 'array' THEN RETURN false; END IF;
  FOR e IN SELECT value FROM jsonb_array_elements(c) LOOP
    IF jsonb_typeof(e) <> 'object' OR NOT (e ?& ARRAY['cov_ref', 'insured_amount_krw', 'fact_source', 'confirm_party', 'as_of']) THEN RETURN false; END IF;
    PERFORM (e ->> 'fact_source')::vocab_fact_source, (e ->> 'confirm_party')::vocab_confirm_party;
    IF jsonb_typeof(e -> 'insured_amount_krw') <> 'number' OR (e ->> 'insured_amount_krw')::numeric < 0 THEN RETURN false; END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE FUNCTION personal.plan_items_valid(c jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE e jsonb;
BEGIN
  IF jsonb_typeof(c) <> 'array' THEN RETURN false; END IF;
  FOR e IN SELECT value FROM jsonb_array_elements(c) LOOP
    IF jsonb_typeof(e) <> 'object' OR NOT (e ? 'action') THEN RETURN false; END IF;
    PERFORM (e ->> 'action')::vocab_plan_action;
  END LOOP;
  RETURN true;
END $$;

CREATE FUNCTION personal.unknown_overlap_valid(c jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE e jsonb;
BEGIN
  IF jsonb_typeof(c) <> 'array' THEN RETURN false; END IF;
  FOR e IN SELECT value FROM jsonb_array_elements(c) LOOP
    IF jsonb_typeof(e) <> 'object' OR NOT (e ?& ARRAY['ref', 'state'])
       OR (e ->> 'state') NOT IN ('not_found', 'hold', 'conflicting', 'ambiguous', 'input_missing') THEN RETURN false; END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE FUNCTION personal.deletion_steps_valid(c jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE e jsonb;
BEGIN
  IF jsonb_typeof(c) <> 'array' THEN RETURN false; END IF;
  FOR e IN SELECT value FROM jsonb_array_elements(c) LOOP
    IF jsonb_typeof(e) <> 'object' OR NOT (e ?& ARRAY['target', 'state'])
       OR (e ->> 'target') NOT IN ('raw', 'extracted', 'index', 'cache', 'derived', 'external')
       OR (e ->> 'state') NOT IN ('pending', 'done', 'failed') THEN RETURN false; END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE TABLE personal.profile (
    person_id   text PRIMARY KEY CHECK (person_id ~ '^person:[0-9A-HJKMNP-TV-Z]{26}$'),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE personal.consent (
    id          text PRIMARY KEY CHECK (id ~ '^consent:[0-9A-HJKMNP-TV-Z]{26}$'),
    person_id   text NOT NULL REFERENCES personal.profile (person_id),
    purpose     text NOT NULL CHECK (purpose IN ('service_required', 'document_processing', 'external_ai', 'family_history', 'family_link')),   -- family_link는 골격(비활성)
    granted_at  timestamptz NOT NULL,
    withdrawn_at timestamptz,
    version     text NOT NULL CHECK (version <> ''),
    CHECK (withdrawn_at IS NULL OR withdrawn_at >= granted_at)
);

CREATE TABLE personal.upload (
    id           text PRIMARY KEY CHECK (id ~ '^upload:[0-9A-HJKMNP-TV-Z]{26}$'),
    person_id    text NOT NULL REFERENCES personal.profile (person_id),
    received_at  timestamptz NOT NULL,
    byte_length  bigint NOT NULL CHECK (byte_length > 0),
    sha256       text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    storage_ref  text NOT NULL CHECK (storage_ref <> ''),                  -- 개인 영역 객체 저장소의 키. 공개 원본 보관소(R2)가 아니다
    state        text NOT NULL DEFAULT 'received' CHECK (state IN ('received', 'extracted', 'confirmed', 'discarded')),
    sensitivity  vocab_sensitivity NOT NULL DEFAULT 'private_policy' CHECK (sensitivity IN ('private_policy', 'private_health'))
);

CREATE TABLE personal.contract_snapshot (
    id               text PRIMARY KEY CHECK (id ~ '^contract:[0-9A-HJKMNP-TV-Z]{26}$'),
    person_id        text NOT NULL REFERENCES personal.profile (person_id),
    upload_id        text REFERENCES personal.upload (id),
    release_id       text CHECK (release_id ~ '^rel:[0-9]{8}-[0-9]+$'),         -- 공개 지식 릴리스는 ID로만 참조한다
    sales_config_id  text CHECK (sales_config_id ~ '^sc:[0-9A-HJKMNP-TV-Z]{26}$'),
    version_match    vocab_contract_version_match NOT NULL,
    applied_editions jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(applied_editions) = 'array'),   -- [{ted_id, basis_evidence, from, to}]. 최신 판 자동 적용 금지
    components       jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (personal.components_valid(components)),
    special_conditions jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(special_conditions) = 'array'),
    usage_counters   jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(usage_counters) = 'array'),
    sensitivity      vocab_sensitivity NOT NULL DEFAULT 'private_policy' CHECK (sensitivity IN ('private_policy', 'private_health')),
    user_confirmed_at timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_snapshot_match_has_config CHECK (version_match <> 'matched' OR (release_id IS NOT NULL AND sales_config_id IS NOT NULL))
);

-- 사용자 직접 가정의 판(§1.5). 고치지 않고 새 판 + supersedes. 가정은 항상 가정(hypothetical)이다.
CREATE TABLE personal.user_assumption (
    id                text NOT NULL CHECK (id ~ '^assume:[0-9A-HJKMNP-TV-Z]{26}$'),
    version           integer NOT NULL CHECK (version >= 1),
    person_id         text NOT NULL REFERENCES personal.profile (person_id),
    kind              text NOT NULL CHECK (kind <> ''),
    value             jsonb NOT NULL CHECK (jsonb_typeof(value) = 'object'),
    scope             jsonb NOT NULL CHECK (jsonb_typeof(scope) = 'object'),
    fact_kind         vocab_fact_kind NOT NULL DEFAULT 'hypothetical' CHECK (fact_kind = 'hypothetical'),
    recorded_at       timestamptz NOT NULL,
    supersedes_version integer,
    PRIMARY KEY (id, version),
    CONSTRAINT chk_assumption_supersedes_older CHECK ((supersedes_version IS NULL) = (version = 1) AND (supersedes_version IS NULL OR supersedes_version < version)),
    CONSTRAINT fk_assumption_supersedes FOREIGN KEY (id, supersedes_version) REFERENCES personal.user_assumption (id, version)
);

CREATE TABLE personal.evaluation (
    id                  text PRIMARY KEY CHECK (id ~ '^eval:[0-9A-HJKMNP-TV-Z]{26}$'),
    person_id           text NOT NULL REFERENCES personal.profile (person_id),
    contract_snapshot_id text REFERENCES personal.contract_snapshot (id),
    release_id          text NOT NULL CHECK (release_id ~ '^rel:[0-9]{8}-[0-9]+$'),     -- I16: 결과는 릴리스에 고정된다
    criteria_release_id text CHECK (criteria_release_id ~ '^crel:[0-9]{8}-[0-9]+$'),
    input_hash          text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
    result              jsonb NOT NULL CHECK (jsonb_typeof(result) = 'object'),
    input_freshness     vocab_freshness NOT NULL,
    knowledge_freshness vocab_knowledge_freshness NOT NULL,
    usage_restriction   vocab_usage_restriction NOT NULL,
    reproducible        boolean NOT NULL,
    computed_at         timestamptz NOT NULL
);

-- 결론별 의존 기록(§1.6). 기록이 없는 결론은 "의존 미확인"으로 넓게 보류된다(D5): 이 테이블의 부재 자체가 의미다.
CREATE TABLE personal.conclusion_dependency (
    conclusion_id  text PRIMARY KEY CHECK (conclusion_id ~ '^[^[:space:]]+$'),
    evaluation_id  text NOT NULL REFERENCES personal.evaluation (id),
    deps           jsonb NOT NULL CHECK (jsonb_typeof(deps) = 'object' AND deps ?& ARRAY['assertions', 'facts', 'rules', 'criteria']),
    unknown_overlap jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (personal.unknown_overlap_valid(unknown_overlap)),
    produced_by    text NOT NULL CHECK (produced_by IN ('engine_trace', 'compare', 'need_assessment', 'compose')),
    computed_at    timestamptz NOT NULL
);

CREATE TABLE personal.plan (
    id                   text PRIMARY KEY CHECK (id ~ '^plan:[0-9A-HJKMNP-TV-Z]{26}$'),
    person_id            text NOT NULL REFERENCES personal.profile (person_id),
    contract_snapshot_id text REFERENCES personal.contract_snapshot (id),
    release_id           text NOT NULL CHECK (release_id ~ '^rel:[0-9]{8}-[0-9]+$'),
    items                jsonb NOT NULL CHECK (personal.plan_items_valid(items)),
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- 삭제 작업 표는 삭제 뒤에도 보존한다(§7.2): person_id에 FK를 걸지 않는다. 삭제 순서: 원본 → 추출값 → 색인 → 캐시 → 파생 결과 → 외부 처리본.
CREATE TABLE personal.deletion_job (
    id                        text PRIMARY KEY CHECK (id ~ '^del:[0-9A-HJKMNP-TV-Z]{26}$'),
    person_id                 text NOT NULL CHECK (person_id ~ '^person:[0-9A-HJKMNP-TV-Z]{26}$'),
    requested_at              timestamptz NOT NULL,
    steps                     jsonb NOT NULL CHECK (personal.deletion_steps_valid(steps)),
    late_writes_rejected_count integer NOT NULL DEFAULT 0 CHECK (late_writes_rejected_count >= 0)
);
CREATE UNIQUE INDEX deletion_job_person_idx ON personal.deletion_job (person_id);

-- 삭제 시작 뒤 도착한 쓰기는 거부한다(ONJ-PS-S-031). 거부 횟수는 서비스가 별도 트랜잭션으로 올린다(이 트리거의 예외는 같은 트랜잭션을 되돌린다).
CREATE FUNCTION personal.reject_late_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE pid text;
BEGIN
  pid := to_jsonb(NEW) ->> 'person_id';
  IF pid IS NULL THEN
    SELECT e.person_id INTO pid FROM personal.evaluation e WHERE e.id = to_jsonb(NEW) ->> 'evaluation_id';
  END IF;
  IF pid IS NOT NULL AND EXISTS (SELECT 1 FROM personal.deletion_job j WHERE j.person_id = pid) THEN
    RAISE EXCEPTION 'ONJ-PS-S-031: write after deletion started on personal.%', TG_TABLE_NAME
      USING ERRCODE = '55000', CONSTRAINT = 'chk_no_late_write';
  END IF;
  RETURN NEW;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['upload', 'contract_snapshot', 'user_assumption', 'evaluation', 'conclusion_dependency', 'plan'] LOOP
    EXECUTE format('CREATE TRIGGER reject_late_write BEFORE INSERT OR UPDATE ON personal.%I FOR EACH ROW EXECUTE FUNCTION personal.reject_late_write()', t);
  END LOOP;
END $$;
