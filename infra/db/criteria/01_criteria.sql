-- 판단 기준 스키마 (T-CT-05, 02_구현계약 §1.5). 공개 DB의 별도 스키마 criteria. public/01_schema.sql 뒤에 적용한다(도메인·함수를 쓴다).
-- 기준은 고치지 않는다: 정정은 새 판 + supersedes(+정정 사유). 출처가 없는 판은 기준 릴리스에 들어가지 못한다.
-- 이 파일은 구조·판·출처·정정 이력만 만든다. 기준 릴리스·서비스 적용 승인(criteria_application)은 T-KN-12·T-KN-14의 범위다.
CREATE SCHEMA criteria;

CREATE DOMAIN vocab_criterion_source_kind AS text CHECK (VALUE IN ('public_statistic', 'statute', 'regulator_notice', 'terms_fact', 'editorial'));

CREATE TABLE criteria.criterion (
    id           text PRIMARY KEY CHECK (id ~ '^crit:[a-z0-9_-]+$'),
    kind         text NOT NULL CHECK (kind IN ('priority_rule', 'reference_stat', 'applicability_rule', 'question_rule')),
    label        text NOT NULL CHECK (label <> ''),
    scope        jsonb NOT NULL CHECK (jsonb_typeof(scope) = 'object' AND scope ?& ARRAY['situations', 'subjects']),   -- 적용 상황·대상. 범위 밖이면 평가에 쓰지 않는다
    recorded_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE criteria.criterion_version (
    id                text PRIMARY KEY CHECK (id ~ '^crit:[a-z0-9_-]+@[0-9]+$'),
    criterion_id      text NOT NULL REFERENCES criteria.criterion (id),
    version           integer NOT NULL CHECK (version >= 1),
    valid_from        date NOT NULL,
    valid_to          date,
    rationale         text NOT NULL CHECK (rationale <> ''),
    recorded_at       timestamptz NOT NULL DEFAULT now(),
    supersedes        text,
    correction_reason vocab_correction_reason,
    origin            vocab_assertion_origin NOT NULL,
    UNIQUE (criterion_id, version),
    UNIQUE (supersedes),                                   -- 같은 판을 둘이 대체하지 못한다(선형 이력)
    CONSTRAINT chk_criterion_version_id CHECK (id = criterion_id || '@' || version),
    CONSTRAINT chk_criterion_valid_order CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT chk_criterion_correction CHECK ((supersedes IS NULL) = (correction_reason IS NULL)),
    CONSTRAINT fk_criterion_supersedes FOREIGN KEY (supersedes) REFERENCES criteria.criterion_version (id)
);

-- 출처: ref는 raw:·clause:·obs: 근거(URL 관측 포함)이고 evidence_kind로 종류를 구분한다. 편집 판단(editorial)은 "온전의 판단"으로 표시된다.
CREATE TABLE criteria.criterion_source (
    criterion_version_id text NOT NULL REFERENCES criteria.criterion_version (id),
    ref                  text NOT NULL CHECK (ref ~ '^(raw:sha256:[0-9a-f]{64}|clause:[^[:space:]]+|obs:src:[^[:space:]]+)$'),
    evidence_kind        vocab_criterion_source_kind NOT NULL,
    PRIMARY KEY (criterion_version_id, ref)
);

-- 판은 출처 하나 이상과 함께 커밋된다(지연 제약). 출처 없는 판은 저장되지 못한다.
CREATE FUNCTION criteria.version_needs_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM criteria.criterion_source s WHERE s.criterion_version_id = NEW.id) THEN
    RAISE EXCEPTION 'chk_criterion_version_has_source: % has no criterion_source', NEW.id
      USING ERRCODE = '23514', CONSTRAINT = 'chk_criterion_version_has_source';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER chk_criterion_version_has_source AFTER INSERT ON criteria.criterion_version
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION criteria.version_needs_source();

-- 정정은 같은 기준 안에서 바로 이전 판을 대체한다.
CREATE FUNCTION criteria.version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prev criteria.criterion_version%ROWTYPE;
BEGIN
  IF NEW.supersedes IS NOT NULL THEN
    SELECT * INTO prev FROM criteria.criterion_version WHERE id = NEW.supersedes;
    IF NOT FOUND OR prev.criterion_id <> NEW.criterion_id OR prev.version >= NEW.version THEN
      RAISE EXCEPTION 'chk_criterion_supersedes: a correction supersedes an earlier version of the same criterion'
        USING ERRCODE = '23514', CONSTRAINT = 'chk_criterion_supersedes';
    END IF;
  ELSIF NEW.version > 1 THEN
    RAISE EXCEPTION 'chk_criterion_supersedes: version > 1 must supersede the previous version'
      USING ERRCODE = '23514', CONSTRAINT = 'chk_criterion_supersedes';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER version_guard BEFORE INSERT ON criteria.criterion_version FOR EACH ROW EXECUTE FUNCTION criteria.version_guard();

DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'criteria' LOOP
    EXECUTE format('CREATE TRIGGER chk_no_private_ids BEFORE INSERT OR UPDATE ON criteria.%I FOR EACH ROW EXECUTE FUNCTION public.chk_no_private_ids()', t);
    EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON criteria.%I FOR EACH ROW EXECUTE FUNCTION public.forbid_mutation()', t);
    EXECUTE format('CREATE TRIGGER append_only_truncate BEFORE TRUNCATE ON criteria.%I FOR EACH STATEMENT EXECUTE FUNCTION public.forbid_mutation()', t);
  END LOOP;
END $$;
