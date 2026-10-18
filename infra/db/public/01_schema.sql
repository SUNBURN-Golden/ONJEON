-- 공개 영역 DB 스키마 (T-CT-05). 근거: 02_구현계약 §1.2~§1.3·§6·§8.2, 온톨로지 onto-0.2.
-- 공개 영역에는 개인 식별자(contract:/person:/upload:/del:/consent:/assume:)가 들어가지 못한다(K8, I12).
-- 이 파일은 단일 트랜잭션으로 적용한다(apply.sh). 어휘 값은 packages/schemas/vocabulary.json에서 온다:
-- vocab_* 도메인은 tests/test_vocab_sync.py가 정본과 대조한다. 값을 여기서 바꾸지 않는다.

-- ---------------------------------------------------------------------------------------------
-- 어휘 도메인 (정본: packages/schemas/vocabulary.json)
-- ---------------------------------------------------------------------------------------------
CREATE DOMAIN vocab_review_status AS text CHECK (VALUE IN ('pending', 'accepted', 'hold', 'rejected'));
CREATE DOMAIN vocab_criticality AS text CHECK (VALUE IN ('c0', 'c1', 'c2'));
CREATE DOMAIN vocab_value_state AS text CHECK (VALUE IN ('observed', 'derived', 'not_found', 'unreadable', 'conflicting', 'not_applicable', 'not_disclosed'));
CREATE DOMAIN vocab_hold_reason AS text CHECK (VALUE IN ('agent_disagreement', 'counterexample', 'quote_mismatch', 'code_check_failed', 'reference_unresolved', 'conflicting_sources', 'circuit_breaker', 'extraction_uncertain'));
CREATE DOMAIN vocab_correction_reason AS text CHECK (VALUE IN ('error_correction', 'source_changed', 'interpretation_improved', 'rule_changed'));
CREATE DOMAIN vocab_assertion_origin AS text CHECK (VALUE IN ('pipeline', 'fixture'));
CREATE DOMAIN vocab_evidence_role AS text CHECK (VALUE IN ('basis', 'cross_check', 'observation'));
CREATE DOMAIN vocab_doc_role AS text CHECK (VALUE IN ('terms', 'rider_terms', 'annex', 'business_method', 'summary', 'price_table', 'standard_terms', 'disclosure_page', 'notice', 'disclosure_list', 'guide_page'));
CREATE DOMAIN vocab_price_basis AS text CHECK (VALUE IN ('illustrative', 'table_derived', 'contract_observed', 'quoted'));
CREATE DOMAIN vocab_acquisition_status AS text CHECK (VALUE IN ('unqueried', 'blocked', 'failed', 'not_found', 'not_disclosed', 'archived'));

-- ---------------------------------------------------------------------------------------------
-- 공통 함수
-- ---------------------------------------------------------------------------------------------

-- jsonb 안의 모든 문자열(값과 키). chk_no_private_ids가 중첩 값까지 본다.
CREATE FUNCTION jsonb_all_strings(j jsonb) RETURNS SETOF text LANGUAGE sql IMMUTABLE AS $$
  WITH RECURSIVE t(v) AS (
    SELECT j
    UNION ALL
    SELECT c.value
    FROM t, LATERAL (
      SELECT value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t.v) = 'array' THEN t.v ELSE '[]'::jsonb END)
      UNION ALL
      SELECT value FROM jsonb_each(CASE WHEN jsonb_typeof(t.v) = 'object' THEN t.v ELSE '{}'::jsonb END)
    ) c
  )
  SELECT v #>> '{}' FROM t WHERE jsonb_typeof(v) = 'string'
  UNION ALL
  SELECT k FROM t, LATERAL jsonb_object_keys(CASE WHEN jsonb_typeof(t.v) = 'object' THEN t.v ELSE '{}'::jsonb END) k
$$;

-- K8: 공개 스키마의 모든 텍스트 열(jsonb·배열 안 포함)에 개인 식별자 접두어를 넣지 못한다.
-- 접두어는 값의 시작이거나 영문·숫자·밑줄이 아닌 문자 바로 뒤에 올 때 걸린다("model:"의 "del:"은 걸리지 않는다).
CREATE FUNCTION chk_no_private_ids() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE hit text;
BEGIN
  SELECT s INTO hit FROM jsonb_all_strings(to_jsonb(NEW)) AS s
   WHERE s ~* '(^|[^a-z0-9_])(contract|person|upload|del|consent|assume):' LIMIT 1;
  IF hit IS NOT NULL THEN
    RAISE EXCEPTION 'chk_no_private_ids: private identifier prefix in %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME
      USING ERRCODE = '23514', CONSTRAINT = 'chk_no_private_ids';
  END IF;
  RETURN NEW;
END $$;

-- 불변 행(관측·판단·주장·근거). 정정은 새 행이다(K15: 제자리 변경은 저장소 오류).
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'append_only: % on %.% is not allowed; write a new row instead', TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
    USING ERRCODE = '55000', CONSTRAINT = 'append_only';
END $$;

-- evidence: [{ref, role}] 1개 이상. basis·cross_check는 조항(clause:)만, observation은 obs:·seg:·raw:·clause:(공시 행)만(02 §6.1).
CREATE FUNCTION evidence_valid(ev jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE e jsonb; r text; f text;
BEGIN
  IF ev IS NULL OR jsonb_typeof(ev) <> 'array' OR jsonb_array_length(ev) < 1 THEN RETURN false; END IF;
  FOR e IN SELECT value FROM jsonb_array_elements(ev) LOOP
    IF jsonb_typeof(e) <> 'object' OR (SELECT count(*) FROM jsonb_object_keys(e)) <> 2
       OR NOT (e ?& ARRAY['ref', 'role'])
       OR jsonb_typeof(e -> 'ref') <> 'string' OR jsonb_typeof(e -> 'role') <> 'string' THEN
      RETURN false;
    END IF;
    r := e ->> 'role'; f := e ->> 'ref';
    BEGIN
      PERFORM r::vocab_evidence_role;
    EXCEPTION WHEN check_violation THEN
      RETURN false;
    END;
    IF f !~ '^(seg|clause|ted|premium|assertion|rule|obs|raw|eval|crit):[^[:space:]]+$' THEN RETURN false; END IF;
    IF r IN ('basis', 'cross_check') AND f !~ '^clause:' THEN RETURN false; END IF;
    IF r = 'observation' AND f !~ '^(obs|seg|raw|clause):' THEN RETURN false; END IF;
  END LOOP;
  RETURN true;
END $$;

-- 검수 결정의 모델 계열 라벨이 서로 다른 값 두 개 이상인지(families_count ≥ 2, ADR-0006).
CREATE FUNCTION distinct_label_count(a text[]) RETURNS integer LANGUAGE sql IMMUTABLE AS $$
  SELECT count(DISTINCT x)::integer FROM unnest(a) AS x WHERE x IS NOT NULL AND x <> ''
$$;

-- ---------------------------------------------------------------------------------------------
-- 관측(불변): raw_asset, observation
-- ---------------------------------------------------------------------------------------------
CREATE TABLE raw_asset (
    id           text PRIMARY KEY CHECK (id ~ '^raw:sha256:[0-9a-f]{64}$'),
    sha256       text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_length  bigint NOT NULL CHECK (byte_length > 0),
    media_type   text NOT NULL CHECK (media_type ~ '^[a-z0-9.+-]+/[a-z0-9.+-]+$'),
    storage_key  text NOT NULL CHECK (storage_key <> ''),     -- 원본 보관소의 객체 키. 접속 정보·토큰은 싣지 않는다
    recorded_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_raw_asset_id_is_hash CHECK (id = 'raw:sha256:' || sha256)  -- 키 = 바이트 해시(onto-0.2). 판매 구성·약관 판의 식별자가 아니다
);

CREATE TABLE observation (
    id            text PRIMARY KEY CHECK (id ~ '^obs:src:[^[:space:]]+/[0-9]{4}-[0-9]{2}-[0-9]{2}T[^[:space:]/]+/[0-9a-f]{16}$'),
    source_id     text NOT NULL CHECK (source_id ~ '^src:[^[:space:]]+$'),
    raw_asset_id  text NOT NULL REFERENCES raw_asset (id),
    observed_at   timestamptz NOT NULL,
    url           text NOT NULL CHECK (url ~ '^https?://'),
    recorded_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_observation_id_source CHECK (starts_with(id, 'obs:' || source_id || '/'))
);

-- ---------------------------------------------------------------------------------------------
-- 문서 구획·조항(불변): document_segment, clause
-- ---------------------------------------------------------------------------------------------
CREATE TABLE document_segment (
    id                 text PRIMARY KEY CHECK (id ~ '^seg:[0-9a-f]{12,64}:p[0-9]+-[0-9]+:[a-z][a-z0-9_]*:[A-Za-z0-9._-]+$'),
    raw_asset_id       text NOT NULL,                                 -- fk_segment_raw
    page_from          integer NOT NULL CHECK (page_from >= 1),
    page_to            integer NOT NULL,
    doc_role           vocab_doc_role NOT NULL,
    seg_rule_ver       text NOT NULL CHECK (seg_rule_ver ~ '^[A-Za-z0-9._-]+$'),
    fingerprint_rule   text CHECK (fingerprint_rule ~ '^[A-Za-z0-9._-]+$'),       -- 예: fp-0.1
    fingerprint_sha256 text CHECK (fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
    boundary           text NOT NULL DEFAULT 'confirmed' CHECK (boundary IN ('confirmed', 'unconfirmed')),
    recorded_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_segment_raw FOREIGN KEY (raw_asset_id) REFERENCES raw_asset (id),
    CONSTRAINT chk_segment_pages CHECK (page_to >= page_from),
    CONSTRAINT chk_segment_fingerprint_pair CHECK ((fingerprint_rule IS NULL) = (fingerprint_sha256 IS NULL)),
    -- ID가 자기 필드를 거짓으로 말하지 못하게 한다: seg:<raw_sha12+>:p<from>-<to>:<doc_role>:<seg_rule_ver>
    CONSTRAINT chk_segment_id_fields CHECK (
        split_part(id, ':', 3) = 'p' || page_from || '-' || page_to
        AND split_part(id, ':', 4) = doc_role
        AND split_part(id, ':', 5) = seg_rule_ver
        AND starts_with(substr(raw_asset_id, 12), split_part(id, ':', 2))
    )
);

CREATE TABLE clause (
    id                 text PRIMARY KEY CHECK (id ~ '^clause:seg:[0-9a-f]{12,64}:p[0-9]+-[0-9]+:[a-z][a-z0-9_]*:[A-Za-z0-9._-]+/[^[:space:]#]+#p[0-9]+:[A-Za-z0-9._-]+@[A-Za-z0-9._-]+(@[0-9.]+,[0-9.]+,[0-9.]+,[0-9.]+)?$'),
    segment_id         text NOT NULL,                                 -- fk_clause_segment
    page               integer NOT NULL CHECK (page >= 1),
    -- 원문 인용은 저장하지 않는다(O16, 저장소 public). 인용 지문과 위치만 둔다.
    quote_sha256       text NOT NULL CHECK (quote_sha256 ~ '^[0-9a-f]{64}$'),
    recorded_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_clause_segment FOREIGN KEY (segment_id) REFERENCES document_segment (id),
    CONSTRAINT chk_clause_in_segment CHECK (starts_with(id, 'clause:' || segment_id || '/'))
);

-- ---------------------------------------------------------------------------------------------
-- 약관 본문 판과 계열(불변): terms_edition, terms_lineage. 파일 해시가 아니라 판단이다(K14).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE terms_lineage (
    id           text PRIMARY KEY CHECK (id ~ '^tl:[0-9A-HJKMNP-TV-Z]{26}$'),
    org_id       text NOT NULL CHECK (org_id ~ '^org:[a-z0-9-]+$'),
    label        text NOT NULL CHECK (label <> ''),
    recorded_at  timestamptz NOT NULL DEFAULT now()
);

-- parts: 판의 구성(본문·참조 별표·참조 정의). 부분마다 role과 지문 {rule, sha256}. 완전성(K16) 판정은 적재기·릴리스 빌더 몫이다.
CREATE FUNCTION edition_parts_valid(p jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE e jsonb;
BEGIN
  IF p IS NULL OR jsonb_typeof(p) <> 'array' OR jsonb_array_length(p) < 1 THEN RETURN false; END IF;
  FOR e IN SELECT value FROM jsonb_array_elements(p) LOOP
    IF jsonb_typeof(e) <> 'object' OR jsonb_typeof(e -> 'role') IS DISTINCT FROM 'string'
       OR (e ->> 'role') !~ '^[a-z][a-z0-9_]*$'
       OR jsonb_typeof(e -> 'fingerprint') IS DISTINCT FROM 'object'
       OR (e #>> '{fingerprint,rule}') IS NULL OR (e #>> '{fingerprint,sha256}') !~ '^[0-9a-f]{64}$' THEN
      RETURN false;
    END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE TABLE terms_edition (
    id           text PRIMARY KEY CHECK (id ~ '^ted:[0-9A-HJKMNP-TV-Z]{26}$'),
    label        text NOT NULL CHECK (label <> ''),
    parts        jsonb NOT NULL CHECK (edition_parts_valid(parts)),
    recorded_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------------------------
-- 노드·코드 체계(불변)
-- ---------------------------------------------------------------------------------------------
-- 참조 노드: 온톨로지 onto-0.2 클래스 중 전용 테이블이 없는 것. 목록은 tests/test_vocab_sync.py가 tbox.json과 대조한다.
CREATE TABLE node (
    id           text PRIMARY KEY CHECK (id ~ '^[^[:space:]]+$'),
    kind         text NOT NULL CHECK (kind IN ('Organization', 'Source', 'SalesConfiguration', 'ProductFamily', 'Component', 'CoverageOccurrence',
                                              'DiseaseCategory', 'CodeSet', 'EventType', 'Condition', 'TimeAnchor', 'CoverageConcept', 'Rule')),
    label        text,
    attrs        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(attrs) = 'object'),
    onto_version text NOT NULL CHECK (onto_version ~ '^onto-[0-9]+\.[0-9]+$'),
    origin       vocab_assertion_origin NOT NULL,
    recorded_at  timestamptz NOT NULL DEFAULT now()
);

-- 서비스 CodeSystem은 공식 출처 원본(RawAsset)과 코드 목록 해시가 있어야 한다(B8). 근사 우주는 픽스처다.
CREATE TABLE code_system (
    id              text PRIMARY KEY CHECK (id ~ '^codesys:[a-z0-9._-]+$'),
    name            text NOT NULL CHECK (name <> ''),
    revision        text NOT NULL CHECK (revision <> ''),
    effective_from  date,
    raw_asset_id    text REFERENCES raw_asset (id),
    codes_sha256    text CHECK (codes_sha256 ~ '^[0-9a-f]{64}$'),
    origin          vocab_assertion_origin NOT NULL,
    recorded_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_code_system_official_source CHECK (origin = 'fixture' OR (raw_asset_id IS NOT NULL AND codes_sha256 IS NOT NULL)),
    CONSTRAINT chk_code_system_fixture_name CHECK ((origin = 'fixture') = (id LIKE 'codesys:fixture-%'))
);

-- ---------------------------------------------------------------------------------------------
-- 검수 결정(불변): review_decision. 가정 승인을 적는 필드는 없다(§8.2 B3).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE review_decision (
    id                      text PRIMARY KEY CHECK (id ~ '^rd:[0-9A-HJKMNP-TV-Z]{26}$'),
    environment             text NOT NULL CHECK (environment IN ('test', 'production')),
    outcome                 text NOT NULL CHECK (outcome IN ('accepted', 'hold', 'rejected')),
    provider_family_labels  text[] NOT NULL,                        -- 계열 라벨만. 모델 식별자 원문은 두지 않는다
    families_count          integer NOT NULL,
    code_checks_passed      boolean NOT NULL,
    redteam_counterexamples integer NOT NULL CHECK (redteam_counterexamples >= 0),
    cross_doc_conflict_free boolean NOT NULL,
    prompt_version          text NOT NULL CHECK (prompt_version <> ''),
    audit_log_sha256        text NOT NULL CHECK (audit_log_sha256 ~ '^[0-9a-f]{64}$'),   -- 손으로 만들 수 없게 실행 기록과 잇는다
    decided_at              timestamptz NOT NULL,
    recorded_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_review_families CHECK (families_count >= 2 AND families_count = distinct_label_count(provider_family_labels)),
    CONSTRAINT chk_review_accepted_complete CHECK (
        outcome <> 'accepted' OR (code_checks_passed AND redteam_counterexamples = 0 AND cross_doc_conflict_free)
    )
);

-- ---------------------------------------------------------------------------------------------
-- 주장(불변): assertion. 속성 값 주장과 관계 주장을 한 테이블로 둔다(02 §1.2).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE assertion (
    id                 text PRIMARY KEY CHECK (id ~ '^a:[0-9A-HJKMNP-TV-Z]{26}$'),
    subject            text NOT NULL CHECK (subject ~ '^[^[:space:]]+$'),
    predicate          text NOT NULL CHECK (predicate ~ '^[^[:space:]]+$'),
    object             text CHECK (object ~ '^[^[:space:]]+$'),
    value              jsonb CHECK (jsonb_typeof(value) = 'object' AND value ? 'raw'),   -- {raw, normalized, unit, value_kind, amount_form}
    scope              jsonb NOT NULL CHECK (jsonb_typeof(scope) = 'object'),
    effective_from     date,
    effective_to       date,
    recorded_at        timestamptz NOT NULL,
    observed_at        timestamptz NOT NULL,
    judged_as_of       date,
    evidence           jsonb NOT NULL CHECK (evidence_valid(evidence)),
    criticality        vocab_criticality NOT NULL,
    value_state        vocab_value_state NOT NULL,
    review_status      vocab_review_status NOT NULL,
    hold_reason        vocab_hold_reason,
    review_decision_id text,
    supersedes         text,
    correction_reason  vocab_correction_reason,
    extractor_tool     text NOT NULL CHECK (extractor_tool <> ''),
    extractor_version  text NOT NULL CHECK (extractor_version <> ''),
    prompt_version     text,
    origin             vocab_assertion_origin NOT NULL,
    onto_version       text NOT NULL CHECK (onto_version ~ '^onto-[0-9]+\.[0-9]+$'),
    created_by_run     text NOT NULL CHECK (created_by_run ~ '^[^[:space:]]+$'),

    -- 구조 주장의 대상 참조를 타입 있는 열로 푼다. 이 열들이 FK의 근거다(realizes 대상, segment_of, in_segment, edition_of, 판 연결).
    ref_segment  text GENERATED ALWAYS AS (CASE WHEN predicate IN ('realizes', 'segment_of') THEN subject
                                                WHEN predicate = 'in_segment' THEN object END) STORED,
    ref_edition  text GENERATED ALWAYS AS (CASE WHEN predicate IN ('realizes', 'uses_edition', 'in_edition') THEN object
                                                WHEN predicate = 'edition_of' OR (predicate = 'applies_to' AND subject LIKE 'ted:%') THEN subject END) STORED,
    ref_raw      text GENERATED ALWAYS AS (CASE WHEN predicate = 'segment_of' THEN object END) STORED,
    ref_lineage  text GENERATED ALWAYS AS (CASE WHEN predicate = 'edition_of' THEN object END) STORED,
    ref_clause   text GENERATED ALWAYS AS (CASE WHEN predicate = 'in_segment' THEN subject END) STORED,

    CONSTRAINT chk_assertion_object_xor_value CHECK (num_nonnulls(object, value) = 1),
    CONSTRAINT chk_assertion_time_order CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from),
    CONSTRAINT chk_assertion_hold_reason CHECK ((review_status = 'hold') = (hold_reason IS NOT NULL)),
    CONSTRAINT chk_assertion_correction CHECK ((supersedes IS NULL) = (correction_reason IS NULL)),
    -- 아래 둘이 §8.2 B2·B3: accepted는 검수 결정 없이 존재하지 못하고, 픽스처는 accepted가 될 수 없다.
    CONSTRAINT chk_accepted_needs_decision CHECK (review_status <> 'accepted' OR review_decision_id IS NOT NULL),
    CONSTRAINT chk_fixture_never_accepted CHECK (origin <> 'fixture' OR review_status <> 'accepted'),
    CONSTRAINT fk_assertion_review_decision FOREIGN KEY (review_decision_id) REFERENCES review_decision (id),
    CONSTRAINT fk_assertion_supersedes FOREIGN KEY (supersedes) REFERENCES assertion (id),
    CONSTRAINT fk_realizes_segment FOREIGN KEY (ref_segment) REFERENCES document_segment (id),    -- realizes·segment_of 주체, in_segment 대상
    CONSTRAINT fk_realizes_edition FOREIGN KEY (ref_edition) REFERENCES terms_edition (id),       -- realizes 대상 등 본문 판 참조
    CONSTRAINT fk_segment_of_raw FOREIGN KEY (ref_raw) REFERENCES raw_asset (id),
    CONSTRAINT fk_edition_of_lineage FOREIGN KEY (ref_lineage) REFERENCES terms_lineage (id),
    CONSTRAINT fk_in_segment_clause FOREIGN KEY (ref_clause) REFERENCES clause (id)
);
CREATE INDEX assertion_realizes_idx ON assertion (ref_segment) WHERE predicate = 'realizes' AND review_status = 'accepted';
CREATE INDEX assertion_supersedes_idx ON assertion (supersedes) WHERE supersedes IS NOT NULL;

-- 구조 주장 목록(onto-0.2). 내용 주장(C0)은 이 밖의 모든 predicate이다.
CREATE FUNCTION structural_predicate(p text) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT p IN ('segment_of', 'realizes', 'edition_of', 'in_edition', 'applies_to', 'application_scope_complete', 'in_segment', 'uses_edition', 'disclosure_of')
$$;

-- 다른 테이블을 보는 제약(CHECK로 쓸 수 없는 것): chk_accepted_needs_decision의 결정 결과, chk_c0_basis, chk_realizes_fingerprint, B9.
CREATE FUNCTION assertion_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  d review_decision%ROWTYPE;
  seg document_segment%ROWTYPE;
  cl clause%ROWTYPE;
  e jsonb;
  has_obs boolean := false;
  has_basis boolean := false;
BEGIN
  IF NEW.review_status = 'accepted' THEN
    SELECT * INTO d FROM review_decision WHERE id = NEW.review_decision_id;
    IF NOT FOUND OR d.outcome <> 'accepted' THEN
      RAISE EXCEPTION 'chk_accepted_needs_decision: accepted needs a review_decision with outcome=accepted' USING ERRCODE = '23514', CONSTRAINT = 'chk_accepted_needs_decision';
    END IF;

    FOR e IN SELECT value FROM jsonb_array_elements(NEW.evidence) LOOP
      IF e ->> 'role' = 'observation' THEN has_obs := true; END IF;
    END LOOP;

    IF structural_predicate(NEW.predicate) THEN
      -- 구조 주장은 관측 근거로 세운다(K1·K14).
      IF NOT has_obs THEN
        RAISE EXCEPTION 'chk_structural_observation: accepted structural assertion needs observation evidence' USING ERRCODE = '23514', CONSTRAINT = 'chk_structural_observation';
      END IF;
    ELSIF NEW.criticality = 'c0' THEN
      -- chk_c0_basis(K1): basis 조항이 있고, 모든 basis 조항의 구획이 약관·특약 약관·별표이며 그 구획에 accepted realizes가 있다.
      FOR e IN SELECT value FROM jsonb_array_elements(NEW.evidence) WHERE value ->> 'role' = 'basis' LOOP
        has_basis := true;
        SELECT * INTO cl FROM clause WHERE id = e ->> 'ref';
        IF NOT FOUND THEN
          RAISE EXCEPTION 'chk_c0_basis: basis clause does not exist' USING ERRCODE = '23514', CONSTRAINT = 'chk_c0_basis';
        END IF;
        SELECT * INTO seg FROM document_segment WHERE id = cl.segment_id;
        IF seg.doc_role NOT IN ('terms', 'rider_terms', 'annex') THEN
          RAISE EXCEPTION 'chk_c0_basis: basis segment doc_role must be terms, rider_terms or annex' USING ERRCODE = '23514', CONSTRAINT = 'chk_c0_basis';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM assertion a WHERE a.predicate = 'realizes' AND a.ref_segment = seg.id AND a.review_status = 'accepted') THEN
          RAISE EXCEPTION 'chk_c0_basis: basis segment has no accepted realizes' USING ERRCODE = '23514', CONSTRAINT = 'chk_c0_basis';
        END IF;
      END LOOP;
      IF NOT has_basis THEN
        RAISE EXCEPTION 'chk_c0_basis: accepted c0 content assertion needs basis evidence' USING ERRCODE = '23514', CONSTRAINT = 'chk_c0_basis';
      END IF;
    END IF;

    IF NEW.predicate = 'realizes' THEN
      -- chk_realizes_fingerprint(K14)·B9: 지문 있는 확정 구획 + 구획 관측(seg:/obs:) 근거. 원본(raw:)만으로는 거부.
      SELECT * INTO seg FROM document_segment WHERE id = NEW.subject;
      IF NOT FOUND OR seg.fingerprint_sha256 IS NULL OR seg.boundary <> 'confirmed' THEN
        RAISE EXCEPTION 'chk_realizes_fingerprint: accepted realizes needs a confirmed segment with a fingerprint' USING ERRCODE = '23514', CONSTRAINT = 'chk_realizes_fingerprint';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.evidence) x WHERE x ->> 'role' = 'observation' AND x ->> 'ref' ~ '^(seg|obs):') THEN
        RAISE EXCEPTION 'chk_realizes_fingerprint: accepted realizes needs segment or observation evidence, not raw only' USING ERRCODE = '23514', CONSTRAINT = 'chk_realizes_fingerprint';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $$;

-- chk_supersedes_linear: 같은 주장을 둘 이상이 대체하면 그 대체 주장 전부를 묶는 Conflict가 있어야 한다. 지연 제약이라 같은 트랜잭션에서 나중에 넣어도 된다.
CREATE TABLE conflict (
    id           text PRIMARY KEY CHECK (id ~ '^conflict:[0-9A-HJKMNP-TV-Z]{26}$'),
    reason       text NOT NULL CHECK (reason <> ''),
    recorded_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE conflict_member (
    conflict_id  text NOT NULL REFERENCES conflict (id),
    assertion_id text NOT NULL REFERENCES assertion (id),
    PRIMARY KEY (conflict_id, assertion_id)
);

CREATE FUNCTION assertion_supersedes_linear() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.supersedes IS NULL THEN RETURN NULL; END IF;
  IF (SELECT count(*) FROM assertion WHERE supersedes = NEW.supersedes) > 1
     AND NOT EXISTS (
       SELECT 1 FROM conflict c
        WHERE NOT EXISTS (
          SELECT 1 FROM assertion s
           WHERE s.supersedes = NEW.supersedes
             AND NOT EXISTS (SELECT 1 FROM conflict_member m WHERE m.conflict_id = c.id AND m.assertion_id = s.id))) THEN
    RAISE EXCEPTION 'chk_supersedes_linear: several assertions supersede % without a conflict row', NEW.supersedes
      USING ERRCODE = '23514', CONSTRAINT = 'chk_supersedes_linear';
  END IF;
  RETURN NULL;
END $$;

CREATE TRIGGER assertion_guard BEFORE INSERT ON assertion FOR EACH ROW EXECUTE FUNCTION assertion_guard();
CREATE CONSTRAINT TRIGGER chk_supersedes_linear AFTER INSERT ON assertion
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assertion_supersedes_linear();

-- ---------------------------------------------------------------------------------------------
-- 가격 관측(불변): premium_observation. 조건 없는 가격 행은 저장하지 못한다(I7). 특약 구성·기준일 공백은 보존하되 비교 자격은 따로 둔다(K13).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE premium_observation (
    id                  text PRIMARY KEY CHECK (id ~ '^premium:[0-9A-HJKMNP-TV-Z]{26}$'),
    evidence            jsonb NOT NULL CHECK (evidence_valid(evidence)),
    raw_amount          bigint NOT NULL CHECK (raw_amount > 0),
    price_basis         vocab_price_basis NOT NULL,
    observed_at         timestamptz NOT NULL,
    source_published_at timestamptz,
    source_as_of        date,
    payment_cycle       text CHECK (payment_cycle ~ '^[a-z][a-z0-9_]*$'),
    conditions          jsonb CHECK (jsonb_typeof(conditions) = 'object'),
    condition_sources   jsonb CHECK (jsonb_typeof(condition_sources) = 'object'),
    package_binding     text CHECK (package_binding ~ '^[a-z][a-z0-9_]*$'),
    missing_dimensions  text[] NOT NULL,
    comparison_basis_id text CHECK (comparison_basis_id ~ '^[^[:space:]]+$'),
    comparison_eligible boolean NOT NULL,
    value_state         vocab_value_state NOT NULL,
    review_status       vocab_review_status NOT NULL,
    review_decision_id  text REFERENCES review_decision (id),
    origin              vocab_assertion_origin NOT NULL,
    recorded_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_accepted_needs_decision CHECK (review_status <> 'accepted' OR review_decision_id IS NOT NULL),
    CONSTRAINT chk_fixture_never_accepted CHECK (origin <> 'fixture' OR review_status <> 'accepted'),
    -- I7: 조건이 없는 가격 행은 저장하지 않는다. 구성·기준일 공백은 숨기지 않고 missing_dimensions에 적는다(적은 것과 실제 공백이 다르면 거부).
    CONSTRAINT chk_premium_conditions_required CHECK (conditions IS NOT NULL AND conditions <> '{}'::jsonb),
    CONSTRAINT chk_premium_missing_package CHECK ((package_binding IS NULL) = ('package_binding' = ANY (missing_dimensions))),
    CONSTRAINT chk_premium_missing_as_of CHECK ((source_as_of IS NULL) = ('as_of' = ANY (missing_dimensions))),
    -- I7·K13: 비교 자격은 조건·특약 구성·기준일이 모두 있고 근거(NOT NULL)가 있으며 accepted일 때만 true다.
    CONSTRAINT chk_premium_raw_vs_eligible CHECK (
        NOT comparison_eligible
        OR (coalesce(conditions, '{}'::jsonb) <> '{}'::jsonb
            AND package_binding IS NOT NULL
            AND source_as_of IS NOT NULL
            AND cardinality(missing_dimensions) = 0
            AND review_status = 'accepted')
    )
);

CREATE FUNCTION premium_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d review_decision%ROWTYPE;
BEGIN
  IF NEW.review_status = 'accepted' THEN
    SELECT * INTO d FROM review_decision WHERE id = NEW.review_decision_id;
    IF NOT FOUND OR d.outcome <> 'accepted' THEN
      RAISE EXCEPTION 'chk_accepted_needs_decision: accepted needs a review_decision with outcome=accepted' USING ERRCODE = '23514', CONSTRAINT = 'chk_accepted_needs_decision';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER premium_guard BEFORE INSERT ON premium_observation FOR EACH ROW EXECUTE FUNCTION premium_guard();

-- ---------------------------------------------------------------------------------------------
-- 공백과 확보 작업. 공백은 릴리스 안(불변), 확보 작업은 운영 상태라 릴리스 밖(가변).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE gap (
    id           text PRIMARY KEY CHECK (id ~ '^gap:[0-9A-HJKMNP-TV-Z]{26}$'),
    subject      text NOT NULL CHECK (subject ~ '^[^[:space:]]+$'),
    status       vocab_acquisition_status NOT NULL,
    supersedes   text REFERENCES gap (id),
    recorded_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE acquisition_task (
    id           text PRIMARY KEY CHECK (id ~ '^task:[0-9A-HJKMNP-TV-Z]{26}$'),
    gap_id       text NOT NULL REFERENCES gap (id),
    state        text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'done', 'failed', 'cancelled')),
    attempts     integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------------------------
-- 릴리스 manifest: 구성원 목록 + 규칙 파일 해시 + 내용 해시로 고정(K15). 고정 뒤에는 철회 표시 외에 바뀌지 않는다.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE release_manifest (
    release_id                text PRIMARY KEY CHECK (release_id ~ '^rel:[0-9]{8}-[0-9]+$'),
    release_kind              text NOT NULL CHECK (release_kind IN ('production', 'test')),   -- test 릴리스는 공개 API가 읽지 않는다(B10)
    created_at                timestamptz NOT NULL,
    frozen_at                 timestamptz NOT NULL,
    members                   jsonb NOT NULL,
    rule_files                jsonb NOT NULL CHECK (jsonb_typeof(rule_files) = 'object'),
    input_stage_edition       text NOT NULL CHECK (input_stage_edition ~ '^[A-Za-z0-9._-]+$'),
    content_sha256            text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    onto_version              text NOT NULL CHECK (onto_version ~ '^onto-[0-9]+\.[0-9]+$'),
    vocabulary_version        text NOT NULL CHECK (vocabulary_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
    label_dictionary_version  text NOT NULL CHECK (label_dictionary_version ~ '^[A-Za-z0-9._-]+$'),
    schema_version            text NOT NULL CHECK (schema_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
    extractor_versions        jsonb NOT NULL CHECK (jsonb_typeof(extractor_versions) = 'array'),
    model_versions            jsonb NOT NULL CHECK (jsonb_typeof(model_versions) = 'array'),   -- [{provider_family_label, model_ref_hash, prompt_version}]
    engine_version            text NOT NULL CHECK (engine_version ~ '^[A-Za-z0-9._-]+$'),
    rule_schema_versions      jsonb NOT NULL CHECK (jsonb_typeof(rule_schema_versions) = 'array'),
    capability_table_hash     text NOT NULL CHECK (capability_table_hash ~ '^[0-9a-f]{64}$'),
    explain_template_hash     text NOT NULL CHECK (explain_template_hash ~ '^[0-9a-f]{64}$'),
    shadow_compare_report_id  text NOT NULL CHECK (shadow_compare_report_id <> ''),
    constraint_report_id      text NOT NULL CHECK (constraint_report_id <> ''),
    superseded_by             text REFERENCES release_manifest (release_id),
    withdrawn_at              timestamptz,
    withdrawal_reason         text,
    CONSTRAINT chk_release_frozen_order CHECK (frozen_at >= created_at),
    CONSTRAINT chk_release_withdrawal_pair CHECK ((withdrawn_at IS NULL) = (withdrawal_reason IS NULL)),
    CONSTRAINT chk_release_members_shape CHECK (
        jsonb_typeof(members) = 'object'
        AND members ?& ARRAY['raw_assets', 'segments', 'terms_editions', 'terms_lineages', 'clauses', 'nodes', 'assertions', 'conflicts', 'gaps', 'premium_observations']
        AND (NOT members ? 'criteria_release_ref' OR members ->> 'criteria_release_ref' ~ '^crel:[0-9]{8}-[0-9]+$')
    )
);

-- 구성원 검사(K15·I3, B3·B5·B10): 구성원 목록은 정렬된 유일한 ID이고 모두 저장소에 있어야 한다.
-- production 릴리스에는 픽스처 행과 environment=test 결정이 섞이지 못한다.
CREATE FUNCTION release_manifest_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  k text; tbl text; bad text; ids text[];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'append_only: DELETE on release_manifest is not allowed; withdraw instead' USING ERRCODE = '55000', CONSTRAINT = 'append_only';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF (to_jsonb(NEW) - 'superseded_by' - 'withdrawn_at' - 'withdrawal_reason') IS DISTINCT FROM
       (to_jsonb(OLD) - 'superseded_by' - 'withdrawn_at' - 'withdrawal_reason') THEN
      RAISE EXCEPTION 'append_only: a frozen release changes only superseded_by and withdrawal fields' USING ERRCODE = '55000', CONSTRAINT = 'append_only';
    END IF;
    RETURN NEW;
  END IF;

  FOR k, tbl IN VALUES ('raw_assets', 'raw_asset'), ('segments', 'document_segment'), ('terms_editions', 'terms_edition'), ('terms_lineages', 'terms_lineage'),
                       ('clauses', 'clause'), ('nodes', 'node'), ('assertions', 'assertion'), ('conflicts', 'conflict'), ('gaps', 'gap'),
                       ('premium_observations', 'premium_observation') LOOP
    IF jsonb_typeof(NEW.members -> k) IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION 'chk_release_members: members.% must be an array', k USING ERRCODE = '23514', CONSTRAINT = 'chk_release_members';
    END IF;
    ids := ARRAY(SELECT jsonb_array_elements_text(NEW.members -> k));
    IF ids IS DISTINCT FROM (SELECT coalesce(array_agg(DISTINCT x COLLATE "C" ORDER BY x COLLATE "C"), '{}') FROM unnest(ids) AS x) THEN
      RAISE EXCEPTION 'chk_release_members: members.% must be sorted and unique', k USING ERRCODE = '23514', CONSTRAINT = 'chk_release_members';
    END IF;
    EXECUTE format('SELECT m FROM unnest($1) AS m WHERE NOT EXISTS (SELECT 1 FROM %I t WHERE t.id = m) LIMIT 1', tbl) INTO bad USING ids;
    IF bad IS NOT NULL THEN
      RAISE EXCEPTION 'chk_release_members: members.% references a row that is not stored: %', k, bad USING ERRCODE = '23503', CONSTRAINT = 'chk_release_members';
    END IF;
  END LOOP;

  IF NEW.release_kind = 'production' THEN
    SELECT a.id INTO bad
      FROM assertion a LEFT JOIN review_decision d ON d.id = a.review_decision_id
     WHERE a.id IN (SELECT jsonb_array_elements_text(NEW.members -> 'assertions'))
       AND (a.origin = 'fixture' OR d.environment = 'test') LIMIT 1;
    IF bad IS NULL THEN
      SELECT p.id INTO bad
        FROM premium_observation p LEFT JOIN review_decision d ON d.id = p.review_decision_id
       WHERE p.id IN (SELECT jsonb_array_elements_text(NEW.members -> 'premium_observations'))
         AND (p.origin = 'fixture' OR d.environment = 'test') LIMIT 1;
    END IF;
    IF bad IS NOT NULL THEN
      RAISE EXCEPTION 'chk_release_production_clean: production release contains fixture or test-environment row %', bad USING ERRCODE = '23514', CONSTRAINT = 'chk_release_production_clean';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER release_manifest_guard BEFORE INSERT OR UPDATE OR DELETE ON release_manifest FOR EACH ROW EXECUTE FUNCTION release_manifest_guard();

-- ---------------------------------------------------------------------------------------------
-- 트리거 일괄 부착: 이 시점의 모든 공개 테이블에 K8(chk_no_private_ids)을, 불변 테이블에 append_only를 건다.
-- 새 테이블은 test.sh의 "모든 테이블에 K8 트리거" 시험이 빠뜨림을 잡는다.
-- ---------------------------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('CREATE TRIGGER chk_no_private_ids BEFORE INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION chk_no_private_ids()', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['raw_asset', 'observation', 'document_segment', 'clause', 'terms_edition', 'terms_lineage', 'node', 'code_system',
                           'review_decision', 'assertion', 'premium_observation', 'conflict', 'conflict_member', 'gap'] LOOP
    EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION forbid_mutation()', t);
    EXECUTE format('CREATE TRIGGER append_only_truncate BEFORE TRUNCATE ON public.%I FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()', t);
  END LOOP;
  EXECUTE 'CREATE TRIGGER append_only_truncate BEFORE TRUNCATE ON public.release_manifest FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()';
END $$;
