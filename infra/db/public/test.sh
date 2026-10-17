#!/usr/bin/env bash
# 공개·개인·기준 스키마의 제약 시험 (T-CT-05). 실제 PostgreSQL에서 마이그레이션을 적용하고 제약이 거부해야 할 것을 거부하는지 본다.
#
# 서버 선택(순서대로):
#   1) ONJEON_DB_ADMIN_URL=postgresql://<관리 역할>@host:port/postgres — 이미 떠 있는 서버(예: infra/compose의 공개 영역 DB). 관리 역할은 슈퍼유저여야 한다
#      (SET ROLE로 네 역할을 흉내 내고 임시 DB를 만든다). 비밀번호는 PGPASSWORD로 준다. 기존 DB는 건드리지 않고 임시 DB 둘을 만들었다 지운다.
#   2) PATH 또는 ONJEON_PG_BIN에 initdb·pg_ctl·psql이 있으면 임시 클러스터를 띄운다(소켓 전용, 시험 뒤 삭제).
#      PATH에 없으면 Debian/Ubuntu 배치(/usr/lib/postgresql/<판>/bin, 가장 높은 판)를 찾아 쓴다. 어느 바이너리를 썼는지 첫 줄에 적는다.
#   3) 둘 다 없으면 실패한다(건너뛰지 않는다: 시험하지 않은 것은 통과가 아니다).
#
# 각 거부 시험은 "실패했다"만 보지 않고 제약 이름 등 이유 문구가 맞는지도 본다. 마지막의 변이 시험은 제약을 일부러 풀면 같은 입력이 통과함을 보여 시험이 실제로 그 제약을 보고 있음을 증명한다.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
db_dir="$(cd "$here/.." && pwd)"
repo_root="$(cd "$db_dir/../.." && pwd)"

pass=0; fail=0
tmp_cluster=""
suffix="$$"
PUB="onjeon_dbtest_pub_$suffix"; PRV="onjeon_dbtest_prv_$suffix"; MUT="onjeon_dbtest_mut_$suffix"
admin_base=""

say() { printf '%s\n' "$*"; }
ok() { pass=$((pass + 1)); say "PASS  $1"; }
bad() { fail=$((fail + 1)); say "FAIL  $1"; [ $# -ge 2 ] && printf '%s\n' "$2" | sed 's/^/        /' | head -12; }

cleanup() {
  if [ -n "${admin_base:-}" ] || [ -n "${tmp_cluster:-}" ]; then
    for d in "$PUB" "$PRV" "$MUT"; do psql_admin postgres -c "DROP DATABASE IF EXISTS \"$d\"" >/dev/null 2>&1; done
  fi
  if [ -n "$tmp_cluster" ]; then
    "$PG_CTL" -D "$tmp_cluster/data" -m immediate stop >/dev/null 2>&1
    rm -rf "$tmp_cluster"
  fi
}
trap cleanup EXIT

# --- 서버 준비 ------------------------------------------------------------------------------------
pgbin="${ONJEON_PG_BIN:-}"
if [ -z "$pgbin" ] && [ -z "${ONJEON_DB_ADMIN_URL:-}" ] && ! command -v initdb >/dev/null 2>&1; then
  # Debian/Ubuntu는 initdb·pg_ctl을 PATH에 두지 않는다(psql 래퍼만). 설치된 판 중 가장 높은 것을 쓴다.
  for d in $(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -t/ -k5,5n -r); do
    [ -x "$d/initdb" ] && [ -x "$d/pg_ctl" ] && [ -x "$d/psql" ] && { pgbin="$d"; break; }
  done
fi
[ -n "$pgbin" ] && PATH="$pgbin:$PATH"
if [ -n "${ONJEON_DB_ADMIN_URL:-}" ]; then
  admin_base="${ONJEON_DB_ADMIN_URL%/*}"
  command -v psql >/dev/null 2>&1 || { say "psql not found"; exit 1; }
  psql_admin() { local d="$1"; shift; psql -X -q -v ON_ERROR_STOP=1 --dbname "$admin_base/$d" "$@"; }
elif command -v initdb >/dev/null 2>&1 && command -v pg_ctl >/dev/null 2>&1 && command -v psql >/dev/null 2>&1; then
  PG_CTL="$(command -v pg_ctl)"
  tmp_cluster="$(mktemp -d /tmp/onjeon-dbtest.XXXXXX)"
  initdb -D "$tmp_cluster/data" -A trust -U postgres >/dev/null 2>&1 || { say "initdb failed"; exit 1; }
  "$PG_CTL" -D "$tmp_cluster/data" -o "-c listen_addresses='' -k $tmp_cluster -c fsync=off" -l "$tmp_cluster/log" -w start >/dev/null 2>&1 || { say "pg_ctl start failed"; exit 1; }
  export PGHOST="$tmp_cluster" PGUSER=postgres
  psql_admin() { local d="$1"; shift; psql -X -q -v ON_ERROR_STOP=1 --dbname "$d" "$@"; }
else
  say "no PostgreSQL available: set ONJEON_DB_ADMIN_URL (compose DB) or put initdb/pg_ctl/psql on PATH (ONJEON_PG_BIN)."
  say "RESULT: NOT RUN (this is not a pass)"
  exit 1
fi

# --- 도우미 --------------------------------------------------------------------------------------
# run_sql DB ROLE SQL  → 출력은 $out, 종료 코드는 $rc
run_sql() {
  local db="$1" role="$2" sql="$3" pre=""
  [ "$role" != "admin" ] && pre="SET ROLE $role;"
  out="$(printf '%s\n%s\n' "$pre" "$sql" | psql_admin "$db" -f - 2>&1)"; rc=$?
}
must_ok() { # NAME DB ROLE SQL
  run_sql "$2" "$3" "$4"
  if [ $rc -eq 0 ]; then ok "$1"; else bad "$1 (expected success)" "$out"; fi
}
must_fail() { # NAME DB ROLE EXPECT SQL  — EXPECT는 오류 출력에 들어 있어야 하는 문구(제약 이름 등)
  run_sql "$2" "$3" "$5"
  if [ $rc -eq 0 ]; then bad "$1 (expected rejection, but it succeeded)"
  elif printf '%s' "$out" | grep -qF -- "$4"; then ok "$1"
  else bad "$1 (rejected for the wrong reason; wanted '$4')" "$out"; fi
}
q() { psql_admin "$1" -At -c "$2" 2>&1; }

rep() { printf "$1%.0s" $(seq 1 "$2"); }
uid() { printf '%026d' "$1"; }
SHA_A="$(rep a 64)"; SHA_B="$(rep b 64)"; SHA_C="$(rep c 64)"
RAW="raw:sha256:$SHA_A"
SEG="seg:aaaaaaaaaaaa:p1-3:terms:segrule-1"
SEG_NOFP="seg:aaaaaaaaaaaa:p4-6:terms:segrule-1"
SEG_SUM="seg:aaaaaaaaaaaa:p7-8:summary:segrule-1"
CL="clause:$SEG/art1#p1:docproc-text@1.0"
CL_SUM="clause:$SEG_SUM/s1#p7:docproc-text@1.0"
TED="ted:$(uid 1)"; LIN="tl:$(uid 1)"
RD_OK="rd:$(uid 1)"; RD_TEST="rd:$(uid 2)"; RD_HOLD="rd:$(uid 3)"
EV_OBS_SEG="[{\"ref\":\"$SEG\",\"role\":\"observation\"}]"
EV_OBS_RAW="[{\"ref\":\"$RAW\",\"role\":\"observation\"}]"
EV_BASIS="[{\"ref\":\"$CL\",\"role\":\"basis\"}]"
EV_BASIS_SUM="[{\"ref\":\"$CL_SUM\",\"role\":\"basis\"}]"

# A ID SUBJECT PREDICATE OBJECT_SQL STATUS CRIT ORIGIN DECISION_SQL EVIDENCE_JSON [SUPERSEDES_SQL CORRECTION_SQL HOLD_SQL]
A() {
  local id="a:$(uid "$1")" sup="${10:-NULL}" cr="${11:-NULL}" hold="${12:-NULL}"
  printf "INSERT INTO assertion (id,subject,predicate,object,scope,recorded_at,observed_at,evidence,criticality,value_state,review_status,hold_reason,review_decision_id,supersedes,correction_reason,extractor_tool,extractor_version,origin,onto_version,created_by_run) VALUES ('%s','%s','%s',%s,'{}',now(),now(),'%s'::jsonb,'%s','observed','%s',%s,%s,%s,%s,'tool','1','%s','onto-0.2','run-1');\n" \
    "$id" "$2" "$3" "$4" "$9" "$6" "$5" "$hold" "$8" "$sup" "$cr" "$7"
}
# P ID ELIGIBLE STATUS ORIGIN DECISION_SQL CONDITIONS_SQL BINDING_SQL ASOF_SQL MISSING_SQL
P() {
  printf "INSERT INTO premium_observation (id,evidence,raw_amount,price_basis,observed_at,source_as_of,conditions,package_binding,missing_dimensions,comparison_eligible,value_state,review_status,review_decision_id,origin) VALUES ('premium:%s','%s'::jsonb,12000,'table_derived',now(),%s,%s,%s,%s,%s,'observed','%s',%s,'%s');\n" \
    "$(uid "$1")" "$EV_OBS_RAW" "$8" "$6" "$7" "$9" "$2" "$3" "$5" "$4"
}
members() { printf '{"raw_assets":[],"segments":[],"terms_editions":[],"terms_lineages":[],"clauses":[],"nodes":[],"assertions":%s,"conflicts":[],"gaps":[],"premium_observations":%s}' "$1" "${2:-[]}"; }
# R RELEASE_NUM KIND MEMBERS_JSON
R() {
  printf "INSERT INTO release_manifest (release_id,release_kind,created_at,frozen_at,members,rule_files,input_stage_edition,content_sha256,onto_version,vocabulary_version,label_dictionary_version,schema_version,extractor_versions,model_versions,engine_version,rule_schema_versions,capability_table_hash,explain_template_hash,shadow_compare_report_id,constraint_report_id) VALUES ('rel:20260101-%s','%s',now(),now(),'%s'::jsonb,'{}','case-0.2','%s','onto-0.2','1.6.0','dict-1','0.1.0','[]','[]','engine-1','[]','%s','%s','shadow-1','constraints-1');\n" \
    "$1" "$2" "$3" "$SHA_A" "$SHA_B" "$SHA_C"
}

say "server: $(psql_admin postgres -At -c 'SHOW server_version')${tmp_cluster:+ (temporary cluster, binaries: $(dirname "$PG_CTL"))}"
say "== 마이그레이션 적용 =="
psql_admin postgres -c "CREATE DATABASE \"$PUB\"" && psql_admin postgres -c "CREATE DATABASE \"$PRV\"" || { say "cannot create test databases"; exit 1; }
# apply.sh는 psql 환경 변수/URL로 접속한다. 같은 접속 설정으로 임시 DB에 적용한다.
apply() { # DB SCRIPT
  if [ -n "${ONJEON_DB_ADMIN_URL:-}" ]; then bash "$2" "$admin_base/$1"; else bash "$2" "$1"; fi
}
if apply "$PUB" "$db_dir/public/apply.sh" >/tmp/onjeon-dbtest-pub.$$ 2>&1; then ok "public + criteria migrations apply"; else bad "public migrations apply" "$(cat /tmp/onjeon-dbtest-pub.$$)"; exit 1; fi
if apply "$PRV" "$db_dir/personal/apply.sh" >/tmp/onjeon-dbtest-prv.$$ 2>&1; then ok "personal migrations apply"; else bad "personal migrations apply" "$(cat /tmp/onjeon-dbtest-prv.$$)"; exit 1; fi
rm -f /tmp/onjeon-dbtest-pub.$$ /tmp/onjeon-dbtest-prv.$$
if apply "$PUB" "$db_dir/public/apply.sh" >/dev/null 2>&1; then bad "re-applying must fail loudly (migrations are not idempotent)"; else ok "re-applying the schema is refused (no silent drift)"; fi

say "== 구조: 모든 공개 테이블에 K8 트리거, 정본 대조 =="
n_tables="$(q "$PUB" "SELECT count(*) FROM pg_tables WHERE schemaname IN ('public','criteria')")"
n_k8="$(q "$PUB" "SELECT count(DISTINCT tgrelid) FROM pg_trigger WHERE tgname='chk_no_private_ids'")"
[ "$n_tables" = "$n_k8" ] && [ "$n_tables" -ge 19 ] && ok "chk_no_private_ids on every public/criteria table ($n_tables)" || bad "K8 trigger missing on some table" "tables=$n_tables k8=$n_k8"
for t in raw_asset observation document_segment terms_edition terms_lineage clause node assertion premium_observation release_manifest review_decision conflict gap acquisition_task code_system; do
  [ "$(q "$PUB" "SELECT to_regclass('public.$t') IS NOT NULL")" = "t" ] && : || bad "missing public table $t"
done
for t in criterion criterion_version criterion_source; do
  [ "$(q "$PUB" "SELECT to_regclass('criteria.$t') IS NOT NULL")" = "t" ] && : || bad "missing criteria table $t"
done
for t in profile consent upload contract_snapshot user_assumption evaluation conclusion_dependency plan deletion_job; do
  [ "$(q "$PRV" "SELECT to_regclass('personal.$t') IS NOT NULL")" = "t" ] && : || bad "missing personal table $t"
done
ok "all 15 public + 3 criteria + 9 personal tables exist"
for c in fk_assertion_review_decision fk_segment_raw fk_clause_segment fk_realizes_segment fk_realizes_edition fk_segment_of_raw fk_in_segment_clause fk_edition_of_lineage; do
  [ "$(q "$PUB" "SELECT count(*) FROM pg_constraint WHERE conname='$c' AND contype='f'")" = "1" ] && ok "FK $c exists" || bad "FK $c missing"
done
if python3 -I "$here/tests/test_vocab_sync.py" "$repo_root"; then ok "vocabulary domains match packages/schemas/vocabulary.json (and node kinds ⊆ tbox classes)"; else bad "vocabulary sync"; fi

say "== 준비 데이터 (관리 역할) =="
must_ok "seed: raw, segments, clause, edition, lineage, decisions" "$PUB" admin "
INSERT INTO raw_asset (id,sha256,byte_length,media_type,storage_key) VALUES ('$RAW','$SHA_A',1000,'application/pdf','archive/a');
INSERT INTO document_segment (id,raw_asset_id,page_from,page_to,doc_role,seg_rule_ver,fingerprint_rule,fingerprint_sha256) VALUES
  ('$SEG','$RAW',1,3,'terms','segrule-1','fp-0.1','$SHA_B'),
  ('$SEG_NOFP','$RAW',4,6,'terms','segrule-1',NULL,NULL),
  ('$SEG_SUM','$RAW',7,8,'summary','segrule-1','fp-0.1','$SHA_C');
INSERT INTO clause (id,segment_id,page,quote_sha256) VALUES ('$CL','$SEG',1,'$SHA_C'),('$CL_SUM','$SEG_SUM',7,'$SHA_C');
INSERT INTO terms_edition (id,label,parts) VALUES ('$TED','edition-1','[{\"role\":\"body\",\"fingerprint\":{\"rule\":\"fp-0.1\",\"sha256\":\"$SHA_B\"}}]');
INSERT INTO terms_lineage (id,org_id,label) VALUES ('$LIN','org:test-insurer','lineage-1');
INSERT INTO review_decision (id,environment,outcome,provider_family_labels,families_count,code_checks_passed,redteam_counterexamples,cross_doc_conflict_free,prompt_version,audit_log_sha256,decided_at) VALUES
  ('$RD_OK','production','accepted','{family_a,family_b}',2,true,0,true,'p1','$SHA_A',now()),
  ('$RD_TEST','test','accepted','{mock_a,mock_b}',2,true,0,true,'p1','$SHA_A',now()),
  ('$RD_HOLD','production','hold','{family_a,family_b}',2,true,1,false,'p1','$SHA_A',now());"
must_fail "review_decision with one model family is refused" "$PUB" admin "chk_review_families" "
INSERT INTO review_decision (id,environment,outcome,provider_family_labels,families_count,code_checks_passed,redteam_counterexamples,cross_doc_conflict_free,prompt_version,audit_log_sha256,decided_at) VALUES
  ('rd:$(uid 9)','production','accepted','{family_a}',1,true,0,true,'p1','$SHA_A',now());"
must_fail "review_decision accepted with a red-team counterexample is refused" "$PUB" admin "chk_review_accepted_complete" "
INSERT INTO review_decision (id,environment,outcome,provider_family_labels,families_count,code_checks_passed,redteam_counterexamples,cross_doc_conflict_free,prompt_version,audit_log_sha256,decided_at) VALUES
  ('rd:$(uid 9)','production','accepted','{family_a,family_b}',2,true,1,true,'p1','$SHA_A',now());"
must_fail "segment id that lies about its page range is refused" "$PUB" admin "chk_segment_id_fields" "
INSERT INTO document_segment (id,raw_asset_id,page_from,page_to,doc_role,seg_rule_ver) VALUES ('seg:aaaaaaaaaaaa:p9-9:terms:segrule-1','$RAW',1,2,'terms','segrule-1');"

say "== I7: 가격 =="
must_fail "I7 price row claiming comparison_eligible without conditions is rejected" "$PUB" knowledge_writer "chk_premium_raw_vs_eligible" \
  "$(P 1 true accepted pipeline "'$RD_OK'" "'{}'::jsonb" "'none'" "'2026-01-01'" "'{conditions}'")"
must_fail "I7 eligible row without package binding is rejected" "$PUB" knowledge_writer "chk_premium_raw_vs_eligible" \
  "$(P 2 true accepted pipeline "'$RD_OK'" "'{\"age\":\"40\"}'::jsonb" "NULL" "'2026-01-01'" "'{package_binding}'")"
must_fail "I7 eligible row without as-of date is rejected" "$PUB" knowledge_writer "chk_premium_raw_vs_eligible" \
  "$(P 3 true accepted pipeline "'$RD_OK'" "'{\"age\":\"40\"}'::jsonb" "'none'" "NULL" "'{as_of}'")"
must_fail "I7 eligible row that is still pending is rejected" "$PUB" knowledge_writer "chk_premium_raw_vs_eligible" \
  "$(P 4 true pending pipeline NULL "'{\"age\":\"40\"}'::jsonb" "'none'" "'2026-01-01'" "'{}'")"
must_fail "I7 raw row that hides its blank conditions is rejected" "$PUB" data_writer "chk_premium_missing_conditions" \
  "$(P 5 false pending pipeline NULL "'{}'::jsonb" "'none'" "'2026-01-01'" "'{}'")"
must_fail "price row without evidence is rejected" "$PUB" data_writer "evidence" \
  "INSERT INTO premium_observation (id,raw_amount,price_basis,observed_at,missing_dimensions,comparison_eligible,value_state,review_status,origin) VALUES ('premium:$(uid 6)',12000,'table_derived',now(),'{conditions,package_binding,as_of}',false,'observed','pending','pipeline');"
must_fail "accepted price row without review_decision is rejected" "$PUB" knowledge_writer "chk_accepted_needs_decision" \
  "$(P 7 false accepted pipeline NULL "'{\"age\":\"40\"}'::jsonb" "'none'" "'2026-01-01'" "'{}'")"
must_ok "raw price row with honest missing_dimensions is preserved, not eligible (02 §1.2)" "$PUB" data_writer \
  "$(P 8 false pending pipeline NULL "'{}'::jsonb" "NULL" "NULL" "'{conditions,package_binding,as_of}'")"
must_ok "complete accepted price row is eligible" "$PUB" knowledge_writer \
  "$(P 9 true accepted pipeline "'$RD_OK'" "'{\"age\":\"40\"}'::jsonb" "'none'" "'2026-01-01'" "'{}'")"

say "== K8: 공개 스키마에 개인 식별자 접두어 =="
for pfx in contract person upload del consent assume; do
  must_fail "K8 node.label with '$pfx:' is rejected" "$PUB" knowledge_writer "chk_no_private_ids" \
    "INSERT INTO node (id,kind,label,onto_version,origin) VALUES ('n:k8$pfx','Condition','$pfx:$(uid 1)','onto-0.2','pipeline');"
done
must_fail "K8 prefix hidden inside jsonb is rejected" "$PUB" knowledge_writer "chk_no_private_ids" \
  "INSERT INTO node (id,kind,attrs,onto_version,origin) VALUES ('n:k8json','Condition','{\"a\":{\"b\":[\"x\",\"person:$(uid 1)\"]}}','onto-0.2','pipeline');"
must_fail "K8 prefix hidden in a text[] column is rejected" "$PUB" data_writer "chk_no_private_ids" \
  "$(P 20 false pending pipeline NULL "'{}'::jsonb" "NULL" "NULL" "'{conditions,package_binding,as_of,upload:x}'")"
must_fail "K8 prefix in an assertion evidence ref is rejected" "$PUB" knowledge_writer "chk_no_private_ids" \
  "$(A 30 "n:x" has_condition "'n:y'" pending c1 pipeline NULL '[{"ref":"obs:src:a/2026-01-01T00:00:00Z/aaaaaaaaaaaaaaaa contract:1","role":"observation"}]')"
must_fail "K8 prefix in a gap subject is rejected" "$PUB" data_writer "chk_no_private_ids" \
  "INSERT INTO gap (id,subject,status) VALUES ('gap:$(uid 1)','consent:$(uid 1)','not_found');"
must_ok "K8 does not fire on 'model:' (contains 'del:' but is not a prefix)" "$PUB" knowledge_writer \
  "INSERT INTO node (id,kind,label,onto_version,origin) VALUES ('n:k8ok','Condition','model:abc','onto-0.2','pipeline');"

say "== accepted ⇒ ReviewDecision, fixture ⇒ not accepted =="
must_fail "accepted without review_decision_id is rejected" "$PUB" knowledge_writer "chk_accepted_needs_decision" \
  "$(A 40 "n:x" has_condition "'n:y'" accepted c1 pipeline NULL "$EV_OBS_SEG")"
must_fail "accepted with an unknown review_decision is rejected" "$PUB" knowledge_writer "chk_accepted_needs_decision" \
  "$(A 41 "n:x" has_condition "'n:y'" accepted c1 pipeline "'rd:$(uid 99)'" "$EV_OBS_SEG")"
must_fail "accepted pointing at a hold decision is rejected" "$PUB" knowledge_writer "chk_accepted_needs_decision" \
  "$(A 42 "n:x" has_condition "'n:y'" accepted c1 pipeline "'$RD_HOLD'" "$EV_OBS_SEG")"
must_fail "origin=fixture accepted is rejected (even with a decision)" "$PUB" knowledge_writer "chk_fixture_never_accepted" \
  "$(A 43 "n:x" has_condition "'n:y'" accepted c1 fixture "'$RD_OK'" "$EV_OBS_SEG")"
must_ok "origin=fixture pending is allowed" "$PUB" knowledge_writer \
  "$(A 44 "n:x" has_condition "'n:y'" pending c1 fixture NULL "$EV_OBS_SEG")"
must_ok "origin=fixture hold and rejected are allowed" "$PUB" knowledge_writer \
  "$(A 45 "n:x" has_condition "'n:y'" hold c1 fixture NULL "$EV_OBS_SEG" NULL NULL "'extraction_uncertain'")$(A 46 "n:x" has_condition "'n:y'" rejected c1 fixture NULL "$EV_OBS_SEG")"
must_fail "hold without hold_reason is rejected" "$PUB" knowledge_writer "chk_assertion_hold_reason" \
  "$(A 47 "n:x" has_condition "'n:y'" hold c1 pipeline NULL "$EV_OBS_SEG")"
must_fail "assertion with both object and value is rejected" "$PUB" knowledge_writer "chk_assertion_object_xor_value" \
  "INSERT INTO assertion (id,subject,predicate,object,value,scope,recorded_at,observed_at,evidence,criticality,value_state,review_status,extractor_tool,extractor_version,origin,onto_version,created_by_run) VALUES ('a:$(uid 48)','n:x','p','n:y','{\"raw\":\"1\"}','{}',now(),now(),'$EV_OBS_SEG','c1','observed','pending','t','1','pipeline','onto-0.2','r');"
must_fail "evidence with an unknown role is rejected" "$PUB" knowledge_writer "assertion_evidence_check" \
  "$(A 49 "n:x" has_condition "'n:y'" pending c1 pipeline NULL "[{\"ref\":\"$SEG\",\"role\":\"assumed\"}]")"
must_fail "basis evidence that is not a clause is rejected" "$PUB" knowledge_writer "assertion_evidence_check" \
  "$(A 50 "n:x" has_condition "'n:y'" pending c1 pipeline NULL "[{\"ref\":\"$RAW\",\"role\":\"basis\"}]")"
must_fail "assertion with empty evidence is rejected" "$PUB" knowledge_writer "assertion_evidence_check" \
  "$(A 51 "n:x" has_condition "'n:y'" pending c1 pipeline NULL '[]')"

say "== FK: realizes 대상, 구획→원본, 조항→구획 =="
must_fail "realizes to a missing edition is rejected" "$PUB" knowledge_writer "fk_realizes_edition" \
  "$(A 60 "$SEG" realizes "'ted:$(uid 99)'" pending c1 pipeline NULL "$EV_OBS_SEG")"
must_fail "realizes from a missing segment is rejected" "$PUB" knowledge_writer "fk_realizes_segment" \
  "$(A 61 "seg:bbbbbbbbbbbb:p1-1:terms:segrule-1" realizes "'$TED'" pending c1 pipeline NULL "$EV_OBS_SEG")"
must_fail "segment_of a missing raw asset is rejected" "$PUB" knowledge_writer "fk_segment_of_raw" \
  "$(A 62 "$SEG" segment_of "'raw:sha256:$(rep d 64)'" pending c1 pipeline NULL "$EV_OBS_SEG")"
must_fail "edition_of a missing lineage is rejected" "$PUB" knowledge_writer "fk_edition_of_lineage" \
  "$(A 63 "$TED" edition_of "'tl:$(uid 99)'" pending c1 pipeline NULL "$EV_OBS_SEG")"
must_fail "document_segment with a missing raw asset is rejected" "$PUB" data_writer "fk_segment_raw" \
  "INSERT INTO document_segment (id,raw_asset_id,page_from,page_to,doc_role,seg_rule_ver) VALUES ('seg:dddddddddddd:p1-1:terms:segrule-1','raw:sha256:$(rep d 64)',1,1,'terms','segrule-1');"
must_fail "clause with a missing segment is rejected" "$PUB" data_writer "fk_clause_segment" \
  "INSERT INTO clause (id,segment_id,page,quote_sha256) VALUES ('clause:seg:dddddddddddd:p1-1:terms:segrule-1/a#p1:docproc-text@1.0','seg:dddddddddddd:p1-1:terms:segrule-1',1,'$SHA_C');"
must_ok "valid pending realizes is stored" "$PUB" knowledge_writer \
  "$(A 64 "$SEG" realizes "'$TED'" pending c1 pipeline NULL "$EV_OBS_SEG")"

say "== K1·K14: C0 basis, realizes 지문 =="
must_fail "accepted c0 content assertion without accepted realizes on the segment is rejected" "$PUB" knowledge_writer "chk_c0_basis" \
  "$(A 70 "n:cov1" has_condition "'n:y'" accepted c0 pipeline "'$RD_OK'" "$EV_BASIS")"
must_fail "accepted realizes on a segment without fingerprint is rejected" "$PUB" knowledge_writer "chk_realizes_fingerprint" \
  "$(A 71 "$SEG_NOFP" realizes "'$TED'" accepted c1 pipeline "'$RD_OK'" "[{\"ref\":\"$SEG_NOFP\",\"role\":\"observation\"}]")"
must_fail "accepted realizes whose only evidence is the raw file hash is rejected (K14)" "$PUB" knowledge_writer "chk_realizes_fingerprint" \
  "$(A 72 "$SEG" realizes "'$TED'" accepted c1 pipeline "'$RD_OK'" "$EV_OBS_RAW")"
must_fail "accepted structural assertion without observation evidence is rejected" "$PUB" knowledge_writer "chk_structural_observation" \
  "$(A 73 "n:sc1" uses_edition "'$TED'" accepted c1 pipeline "'$RD_OK'" "$EV_BASIS")"
must_ok "accepted realizes with fingerprinted segment + segment observation + review decision" "$PUB" knowledge_writer \
  "$(A 74 "$SEG" realizes "'$TED'" accepted c1 pipeline "'$RD_OK'" "$EV_OBS_SEG")"
must_fail "accepted c0 whose basis clause is in a summary segment is rejected" "$PUB" knowledge_writer "chk_c0_basis" \
  "$(A 75 "n:cov1" has_condition "'n:y'" accepted c0 pipeline "'$RD_OK'" "$EV_BASIS_SUM")"
must_fail "accepted c0 with only cross_check evidence is rejected" "$PUB" knowledge_writer "chk_c0_basis" \
  "$(A 76 "n:cov1" has_condition "'n:y'" accepted c0 pipeline "'$RD_OK'" "[{\"ref\":\"$CL\",\"role\":\"cross_check\"}]")"
must_fail "accepted c0 whose basis clause does not exist is rejected" "$PUB" knowledge_writer "chk_c0_basis" \
  "$(A 77 "n:cov1" has_condition "'n:y'" accepted c0 pipeline "'$RD_OK'" "[{\"ref\":\"clause:$SEG/nope#p1:docproc-text@1.0\",\"role\":\"basis\"}]")"
must_ok "accepted c0 with a terms clause basis + accepted realizes + decision" "$PUB" knowledge_writer \
  "$(A 78 "n:cov1" has_condition "'n:y'" accepted c0 pipeline "'$RD_OK'" "$EV_BASIS")"
must_ok "c0 pending needs no basis yet" "$PUB" knowledge_writer \
  "$(A 79 "n:cov2" has_condition "'n:y'" pending c0 pipeline NULL "$EV_OBS_SEG")"

say "== 정정 사슬, 불변성 =="
must_fail "correction without correction_reason is rejected" "$PUB" knowledge_writer "chk_assertion_correction" \
  "$(A 80 "n:cov1" has_condition "'n:z'" pending c1 pipeline NULL "$EV_OBS_SEG" "'a:$(uid 78)'" NULL)"
must_fail "two assertions superseding the same one without a conflict are rejected at commit" "$PUB" knowledge_writer "chk_supersedes_linear" \
  "BEGIN;
$(A 81 "n:cov1" has_condition "'n:z'" pending c1 pipeline NULL "$EV_OBS_SEG" "'a:$(uid 44)'" "'error_correction'")
$(A 82 "n:cov1" has_condition "'n:w'" pending c1 pipeline NULL "$EV_OBS_SEG" "'a:$(uid 44)'" "'error_correction'")
COMMIT;"
must_ok "two superseders are fine when one Conflict row groups them (deferred)" "$PUB" knowledge_writer \
  "BEGIN;
$(A 83 "n:cov1" has_condition "'n:z'" pending c1 pipeline NULL "$EV_OBS_SEG" "'a:$(uid 45)'" "'error_correction'")
$(A 84 "n:cov1" has_condition "'n:w'" pending c1 pipeline NULL "$EV_OBS_SEG" "'a:$(uid 45)'" "'error_correction'")
INSERT INTO conflict (id,reason) VALUES ('conflict:$(uid 1)','competing corrections');
INSERT INTO conflict_member (conflict_id,assertion_id) VALUES ('conflict:$(uid 1)','a:$(uid 83)'),('conflict:$(uid 1)','a:$(uid 84)');
COMMIT;"
must_fail "UPDATE of an assertion is refused (append-only)" "$PUB" admin "append_only" "UPDATE assertion SET review_status='rejected' WHERE id='a:$(uid 44)';"
must_fail "DELETE of an assertion is refused (append-only, even for the owner)" "$PUB" admin "append_only" "DELETE FROM assertion WHERE id='a:$(uid 44)';"
must_fail "TRUNCATE of an assertion is refused" "$PUB" admin "append_only" "TRUNCATE assertion CASCADE;"
must_fail "UPDATE of a raw asset is refused" "$PUB" admin "append_only" "UPDATE raw_asset SET byte_length=1;"

say "== 릴리스 manifest (K15, B3·B5·B10) =="
must_ok "seed: clean production-eligible assertion and a test-environment one" "$PUB" knowledge_writer \
  "$(A 90 "n:cov3" has_condition "'n:y'" accepted c1 pipeline "'$RD_OK'" "$EV_OBS_SEG")$(A 91 "n:cov3" has_condition "'n:t'" accepted c1 pipeline "'$RD_TEST'" "$EV_OBS_SEG")"
must_fail "production release with a fixture assertion is rejected" "$PUB" knowledge_writer "chk_release_production_clean" \
  "$(R 1 production "$(members "[\"a:$(uid 44)\"]")")"
must_fail "production release with a test-environment decision is rejected (B10)" "$PUB" knowledge_writer "chk_release_production_clean" \
  "$(R 2 production "$(members "[\"a:$(uid 91)\"]")")"
must_fail "release naming a row that is not stored is rejected (I3)" "$PUB" knowledge_writer "chk_release_members" \
  "$(R 3 production "$(members "[\"a:$(uid 98)\"]")")"
must_fail "release members must be sorted and unique" "$PUB" knowledge_writer "chk_release_members" \
  "$(R 4 production "$(members "[\"a:$(uid 91)\",\"a:$(uid 90)\"]")")"
must_ok "test release may contain test-environment and fixture rows" "$PUB" knowledge_writer \
  "$(R 5 test "$(members "[\"a:$(uid 44)\",\"a:$(uid 91)\"]")")"
must_ok "clean production release is stored" "$PUB" knowledge_writer "$(R 6 production "$(members "[\"a:$(uid 90)\"]")")"
must_fail "frozen release content cannot be changed" "$PUB" knowledge_writer "permission denied" "UPDATE release_manifest SET engine_version='x' WHERE release_id='rel:20260101-6';"
must_fail "even the owner cannot change frozen release content" "$PUB" admin "append_only" "UPDATE release_manifest SET engine_version='x' WHERE release_id='rel:20260101-6';"
must_ok "withdrawal mark is allowed" "$PUB" knowledge_writer "UPDATE release_manifest SET withdrawn_at=now(), withdrawal_reason='error confirmed' WHERE release_id='rel:20260101-6';"
must_fail "release rows cannot be deleted" "$PUB" admin "append_only" "DELETE FROM release_manifest;"

say "== CodeSystem (B8) =="
must_fail "service CodeSystem without official source raw asset is rejected" "$PUB" knowledge_writer "chk_code_system_official_source" \
  "INSERT INTO code_system (id,name,revision,origin) VALUES ('codesys:kcd-9','KCD','9','pipeline');"
must_fail "fixture CodeSystem must carry the fixture- name" "$PUB" knowledge_writer "chk_code_system_fixture_name" \
  "INSERT INTO code_system (id,name,revision,origin) VALUES ('codesys:kcd-approx','approx','0','fixture');"
must_ok "fixture CodeSystem needs no source" "$PUB" knowledge_writer "INSERT INTO code_system (id,name,revision,origin) VALUES ('codesys:fixture-kcd-approx','approx','0','fixture');"
must_ok "official CodeSystem with raw asset + code list hash" "$PUB" knowledge_writer "INSERT INTO code_system (id,name,revision,raw_asset_id,codes_sha256,origin) VALUES ('codesys:kcd-9','KCD','9','$RAW','$SHA_B','pipeline');"

say "== 판단 기준(criteria) =="
CRIT_V1="crit:need-test@1"
must_ok "criterion + version 1 + source in one transaction" "$PUB" criteria_writer \
  "BEGIN;
INSERT INTO criteria.criterion (id,kind,label,scope) VALUES ('crit:need-test','priority_rule','label','{\"situations\":[],\"subjects\":[]}');
INSERT INTO criteria.criterion_version (id,criterion_id,version,valid_from,rationale,origin) VALUES ('$CRIT_V1','crit:need-test',1,'2026-01-01','why','pipeline');
INSERT INTO criteria.criterion_source (criterion_version_id,ref,evidence_kind) VALUES ('$CRIT_V1','raw:sha256:$SHA_A','public_statistic');
COMMIT;"
must_fail "criterion version without a source cannot commit" "$PUB" criteria_writer "chk_criterion_version_has_source" \
  "BEGIN;
INSERT INTO criteria.criterion (id,kind,label,scope) VALUES ('crit:nosrc','priority_rule','label','{\"situations\":[],\"subjects\":[]}');
INSERT INTO criteria.criterion_version (id,criterion_id,version,valid_from,rationale,origin) VALUES ('crit:nosrc@1','crit:nosrc',1,'2026-01-01','why','pipeline');
COMMIT;"
must_fail "version 2 that does not supersede version 1 is rejected" "$PUB" criteria_writer "chk_criterion_supersedes" \
  "BEGIN;
INSERT INTO criteria.criterion_version (id,criterion_id,version,valid_from,rationale,origin) VALUES ('crit:need-test@2','crit:need-test',2,'2026-01-01','why','pipeline');
INSERT INTO criteria.criterion_source (criterion_version_id,ref,evidence_kind) VALUES ('crit:need-test@2','raw:sha256:$SHA_A','statute');
COMMIT;"
must_fail "unknown source kind is rejected" "$PUB" criteria_writer "vocab_criterion_source_kind" \
  "BEGIN;
INSERT INTO criteria.criterion_version (id,criterion_id,version,valid_from,rationale,origin,supersedes,correction_reason) VALUES ('crit:need-test@2','crit:need-test',2,'2026-01-01','why','pipeline','$CRIT_V1','error_correction');
INSERT INTO criteria.criterion_source (criterion_version_id,ref,evidence_kind) VALUES ('crit:need-test@2','raw:sha256:$SHA_A','opinion');
COMMIT;"
must_ok "correction = new version superseding the old one (v1 stays)" "$PUB" criteria_writer \
  "BEGIN;
INSERT INTO criteria.criterion_version (id,criterion_id,version,valid_from,rationale,origin,supersedes,correction_reason) VALUES ('crit:need-test@2','crit:need-test',2,'2026-01-01','why','pipeline','$CRIT_V1','error_correction');
INSERT INTO criteria.criterion_source (criterion_version_id,ref,evidence_kind) VALUES ('crit:need-test@2','raw:sha256:$SHA_A','editorial');
COMMIT;"
[ "$(q "$PUB" "SELECT count(*) FROM criteria.criterion_version")" = "2" ] && ok "v1 was not erased by the correction" || bad "v1 missing after correction"
must_fail "a version cannot be superseded twice" "$PUB" criteria_writer "criterion_version_supersedes_key" \
  "BEGIN;
INSERT INTO criteria.criterion_version (id,criterion_id,version,valid_from,rationale,origin,supersedes,correction_reason) VALUES ('crit:need-test@3','crit:need-test',3,'2026-01-01','why','pipeline','$CRIT_V1','error_correction');
INSERT INTO criteria.criterion_source (criterion_version_id,ref,evidence_kind) VALUES ('crit:need-test@3','raw:sha256:$SHA_A','editorial');
COMMIT;"
must_fail "criterion version cannot be updated" "$PUB" admin "append_only" "UPDATE criteria.criterion_version SET rationale='x';"
must_fail "criterion text with a private prefix is rejected (K8)" "$PUB" criteria_writer "chk_no_private_ids" \
  "INSERT INTO criteria.criterion (id,kind,label,scope) VALUES ('crit:k8','priority_rule','assume:$(uid 1)@1','{\"situations\":[],\"subjects\":[]}');"

say "== I12: 역할 권한 (공개 DB) =="
must_fail "I12 personal cannot insert into a public table" "$PUB" personal "permission denied for table node" "INSERT INTO node (id,kind,onto_version,origin) VALUES ('n:p','Condition','onto-0.2','pipeline');"
must_fail "I12 personal cannot insert an assertion" "$PUB" personal "permission denied for table assertion" "$(A 120 "n:x" has_condition "'n:y'" pending c1 pipeline NULL "$EV_OBS_SEG")"
must_fail "I12 personal cannot update a public table" "$PUB" personal "permission denied" "UPDATE release_manifest SET withdrawn_at=now(), withdrawal_reason='x';"
must_fail "I12 personal cannot delete from a public table" "$PUB" personal "permission denied" "DELETE FROM gap;"
must_fail "I12 personal cannot truncate a public table" "$PUB" personal "permission denied" "TRUNCATE node;"
must_fail "I12 personal cannot create objects in the public schema" "$PUB" personal "permission denied for schema public" "CREATE TABLE sneaky (x int);"
must_fail "I12 personal cannot insert into criteria" "$PUB" personal "permission denied" "INSERT INTO criteria.criterion (id,kind,label,scope) VALUES ('crit:p','priority_rule','l','{\"situations\":[],\"subjects\":[]}');"
must_ok "personal may read released knowledge" "$PUB" personal "SELECT count(*) FROM release_manifest; SELECT count(*) FROM assertion;"
must_fail "personal cannot read raw archive rows" "$PUB" personal "permission denied for table raw_asset" "SELECT * FROM raw_asset;"
must_fail "data_writer cannot write judgements (assertion)" "$PUB" data_writer "permission denied for table assertion" "$(A 121 "n:x" has_condition "'n:y'" pending c1 pipeline NULL "$EV_OBS_SEG")"
must_fail "data_writer cannot write criteria" "$PUB" data_writer "permission denied" "INSERT INTO criteria.criterion (id,kind,label,scope) VALUES ('crit:d','priority_rule','l','{\"situations\":[],\"subjects\":[]}');"
must_fail "knowledge_writer cannot write raw archive rows" "$PUB" knowledge_writer "permission denied for table raw_asset" "INSERT INTO raw_asset (id,sha256,byte_length,media_type,storage_key) VALUES ('raw:sha256:$(rep e 64)','$(rep e 64)',1,'application/pdf','k');"
must_fail "criteria_writer cannot write public knowledge" "$PUB" criteria_writer "permission denied for table node" "INSERT INTO node (id,kind,onto_version,origin) VALUES ('n:c','Condition','onto-0.2','pipeline');"
must_ok "data_writer writes observations" "$PUB" data_writer "INSERT INTO raw_asset (id,sha256,byte_length,media_type,storage_key) VALUES ('raw:sha256:$(rep e 64)','$(rep e 64)',1,'application/pdf','k');"
must_fail "nobody can delete (data_writer)" "$PUB" data_writer "permission denied" "DELETE FROM raw_asset;"
must_ok "acquisition tasks (operational state) can change" "$PUB" data_writer \
  "INSERT INTO gap (id,subject,status) VALUES ('gap:$(uid 2)','n:sc1','unqueried'); INSERT INTO acquisition_task (id,gap_id) VALUES ('task:$(uid 1)','gap:$(uid 2)'); UPDATE acquisition_task SET state='running', attempts=1;"

say "== 개인 영역 DB =="
PID="person:$(uid 1)"
must_ok "personal writes profile, consent, upload" "$PRV" personal \
  "INSERT INTO personal.profile (person_id) VALUES ('$PID');
INSERT INTO personal.consent (id,person_id,purpose,granted_at,version) VALUES ('consent:$(uid 1)','$PID','document_processing',now(),'v1');
INSERT INTO personal.upload (id,person_id,received_at,byte_length,sha256,storage_ref) VALUES ('upload:$(uid 1)','$PID',now(),10,'$SHA_A','priv/obj1');"
must_fail "unknown consent purpose is rejected" "$PRV" personal "consent_purpose_check" \
  "INSERT INTO personal.consent (id,person_id,purpose,granted_at,version) VALUES ('consent:$(uid 2)','$PID','marketing',now(),'v1');"
must_fail "snapshot 'matched' without a release/sales config is rejected" "$PRV" personal "chk_snapshot_match_has_config" \
  "INSERT INTO personal.contract_snapshot (id,person_id,version_match) VALUES ('contract:$(uid 1)','$PID','matched');"
must_fail "snapshot component with an unknown fact_source is rejected" "$PRV" personal "vocab_fact_source" \
  "INSERT INTO personal.contract_snapshot (id,person_id,version_match,components) VALUES ('contract:$(uid 1)','$PID','unmatched','[{\"cov_ref\":\"c\",\"insured_amount_krw\":1,\"fact_source\":\"guess\",\"confirm_party\":\"user\",\"as_of\":\"2026-01-01\"}]');"
must_ok "snapshot with vocabulary-valid components (contract: ids are legal here)" "$PRV" personal \
  "INSERT INTO personal.contract_snapshot (id,person_id,upload_id,version_match,components) VALUES ('contract:$(uid 1)','$PID','upload:$(uid 1)','unmatched','[{\"cov_ref\":\"c\",\"insured_amount_krw\":1000,\"fact_source\":\"pdf_extracted\",\"confirm_party\":\"document\",\"as_of\":\"2026-01-01\"}]');"
must_ok "assumption v1 then v2 superseding v1" "$PRV" personal \
  "INSERT INTO personal.user_assumption (id,version,person_id,kind,value,scope,recorded_at) VALUES ('assume:$(uid 1)',1,'$PID','income','{\"v\":1}','{}',now());
INSERT INTO personal.user_assumption (id,version,person_id,kind,value,scope,recorded_at,supersedes_version) VALUES ('assume:$(uid 1)',2,'$PID','income','{\"v\":2}','{}',now(),1);"
must_fail "assumption v2 without supersedes is rejected" "$PRV" personal "chk_assumption_supersedes_older" \
  "INSERT INTO personal.user_assumption (id,version,person_id,kind,value,scope,recorded_at) VALUES ('assume:$(uid 1)',3,'$PID','income','{}','{}',now());"
must_fail "an assumption cannot be an 'actual' fact" "$PRV" personal "user_assumption_fact_kind_check" \
  "INSERT INTO personal.user_assumption (id,version,person_id,kind,value,scope,recorded_at,fact_kind) VALUES ('assume:$(uid 2)',1,'$PID','income','{}','{}',now(),'actual');"
must_fail "evaluation without release_id is rejected (I16)" "$PRV" personal "release_id" \
  "INSERT INTO personal.evaluation (id,person_id,input_hash,result,input_freshness,knowledge_freshness,usage_restriction,reproducible,computed_at) VALUES ('eval:$(uid 1)','$PID','$SHA_A','{}','fresh','fresh','none',true,now());"
must_fail "evaluation with an unknown usage_restriction is rejected" "$PRV" personal "vocab_usage_restriction" \
  "INSERT INTO personal.evaluation (id,person_id,release_id,input_hash,result,input_freshness,knowledge_freshness,usage_restriction,reproducible,computed_at) VALUES ('eval:$(uid 1)','$PID','rel:20260101-6','$SHA_A','{}','fresh','fresh','blocked',true,now());"
must_ok "evaluation + dependency record" "$PRV" personal \
  "INSERT INTO personal.evaluation (id,person_id,release_id,input_hash,result,input_freshness,knowledge_freshness,usage_restriction,reproducible,computed_at) VALUES ('eval:$(uid 1)','$PID','rel:20260101-6','$SHA_A','{}','fresh','withdrawn','hold',true,now());
INSERT INTO personal.conclusion_dependency (conclusion_id,evaluation_id,deps,unknown_overlap,produced_by,computed_at) VALUES ('concl:1','eval:$(uid 1)','{\"assertions\":[],\"facts\":[],\"rules\":[],\"criteria\":[]}','[{\"ref\":\"n:x\",\"state\":\"ambiguous\"}]','engine_trace',now());"
must_fail "dependency with an unknown overlap state is rejected" "$PRV" personal "unknown_overlap" \
  "INSERT INTO personal.conclusion_dependency (conclusion_id,evaluation_id,deps,unknown_overlap,produced_by,computed_at) VALUES ('concl:2','eval:$(uid 1)','{\"assertions\":[],\"facts\":[],\"rules\":[],\"criteria\":[]}','[{\"ref\":\"n:x\",\"state\":\"maybe\"}]','compose',now());"
must_fail "plan item with an unknown action is rejected" "$PRV" personal "vocab_plan_action" \
  "INSERT INTO personal.plan (id,person_id,release_id,items) VALUES ('plan:$(uid 1)','$PID','rel:20260101-6','[{\"action\":\"cancel\"}]');"
must_ok "plan with vocabulary actions" "$PRV" personal "INSERT INTO personal.plan (id,person_id,release_id,items) VALUES ('plan:$(uid 1)','$PID','rel:20260101-6','[{\"action\":\"keep\"},{\"action\":\"add\"}]');"
must_fail "deletion step with an unknown target is rejected" "$PRV" personal "steps" \
  "INSERT INTO personal.deletion_job (id,person_id,requested_at,steps) VALUES ('del:$(uid 1)','$PID',now(),'[{\"target\":\"backup\",\"state\":\"pending\"}]');"
must_ok "deletion job starts" "$PRV" personal "INSERT INTO personal.deletion_job (id,person_id,requested_at,steps) VALUES ('del:$(uid 1)','$PID',now(),'[{\"target\":\"raw\",\"state\":\"pending\"}]');"
must_fail "write after deletion started is rejected (ONJ-PS-S-031)" "$PRV" personal "ONJ-PS-S-031" \
  "INSERT INTO personal.upload (id,person_id,received_at,byte_length,sha256,storage_ref) VALUES ('upload:$(uid 2)','$PID',now(),10,'$SHA_A','priv/obj2');"
must_fail "late evaluation write is rejected too" "$PRV" personal "ONJ-PS-S-031" \
  "INSERT INTO personal.evaluation (id,person_id,release_id,input_hash,result,input_freshness,knowledge_freshness,usage_restriction,reproducible,computed_at) VALUES ('eval:$(uid 2)','$PID','rel:20260101-6','$SHA_A','{}','fresh','fresh','none',true,now());"
must_fail "the deletion record itself cannot be deleted" "$PRV" personal "permission denied" "DELETE FROM personal.deletion_job;"
for r in data_writer knowledge_writer criteria_writer; do
  must_fail "I12 $r cannot read personal data" "$PRV" "$r" "permission denied" "SELECT * FROM personal.profile;"
  must_fail "I12 $r cannot write personal data" "$PRV" "$r" "permission denied" "INSERT INTO personal.profile (person_id) VALUES ('person:$(uid 7)');"
done
must_fail "personal DB has no public knowledge tables" "$PRV" personal "does not exist" "SELECT * FROM assertion;"

say "== 변이 시험: 제약을 풀면 같은 입력이 통과해야 한다 (시험이 그 제약을 보고 있다는 증거) =="
mutate() { # NAME DB SETUP_SQL VERIFY_SQL ROLE  — 변이마다 새 복제본에서 하나만 푼다
  psql_admin postgres -c "DROP DATABASE IF EXISTS \"$MUT\"" >/dev/null 2>&1
  psql_admin postgres -c "CREATE DATABASE \"$MUT\" TEMPLATE \"$PUB\"" >/dev/null 2>&1 || { bad "mutation '$1': cannot clone database"; return; }
  run_sql "$MUT" admin "$3"
  [ $rc -ne 0 ] && { bad "mutation '$1': setup failed" "$out"; return; }
  run_sql "$MUT" "$5" "$4"
  if [ $rc -eq 0 ]; then ok "mutation '$1': input now passes, so the real constraint was what rejected it"; else bad "mutation '$1': still rejected after removing the constraint" "$out"; fi
}
mutate "chk_fixture_never_accepted" x "ALTER TABLE assertion DROP CONSTRAINT chk_fixture_never_accepted;" "$(A 200 "n:x" has_condition "'n:y'" accepted c1 fixture "'$RD_OK'" "$EV_OBS_SEG")" knowledge_writer
mutate "chk_accepted_needs_decision" x "ALTER TABLE assertion DROP CONSTRAINT chk_accepted_needs_decision; DROP TRIGGER assertion_guard ON assertion;" "$(A 201 "n:x" has_condition "'n:y'" accepted c1 pipeline NULL "$EV_OBS_SEG")" knowledge_writer
mutate "chk_premium_raw_vs_eligible" x "ALTER TABLE premium_observation DROP CONSTRAINT chk_premium_raw_vs_eligible;" "$(P 202 true accepted pipeline "'$RD_OK'" "'{}'::jsonb" "'none'" "'2026-01-01'" "'{conditions}'")" knowledge_writer
mutate "chk_no_private_ids" x "DROP TRIGGER chk_no_private_ids ON node;" "INSERT INTO node (id,kind,label,onto_version,origin) VALUES ('n:mut','Condition','contract:$(uid 1)','onto-0.2','pipeline');" knowledge_writer
mutate "I12 grants" x "GRANT INSERT ON node TO personal;" "INSERT INTO node (id,kind,onto_version,origin) VALUES ('n:mut2','Condition','onto-0.2','pipeline');" personal
mutate "fk_realizes_edition" x "ALTER TABLE assertion DROP CONSTRAINT fk_realizes_edition;" "$(A 203 "$SEG" realizes "'ted:$(uid 99)'" pending c1 pipeline NULL "$EV_OBS_SEG")" knowledge_writer
mutate "chk_c0_basis" x "DROP TRIGGER assertion_guard ON assertion;" "$(A 204 "n:cov9" has_condition "'n:y'" accepted c0 pipeline "'$RD_OK'" "$EV_BASIS_SUM")" knowledge_writer

say "== 정적 검사 =="
sql_files="$(find "$db_dir" \( -name '*.sql' -o -name '*.sh' -o -name '*.py' \) | sort)"
migration_files="$(find "$db_dir" \( -name '*.sql' -o -name 'apply.sh' \) | sort)"
# shellcheck disable=SC2086
if grep -nE 'packages/fixtures|docs/blueprint/' $migration_files >/dev/null; then
  bad "B7: migrations must not reference fixture or blueprint-doc paths"; grep -nE 'packages/fixtures|docs/blueprint/' $migration_files
else ok "B7: no packages/fixtures or docs/blueprint reference in migrations"; fi
# shellcheck disable=SC2086
if grep -nEi '(api[_-]?key|secret|token|passw(or)?d)[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9_-]{8,}' $sql_files >/dev/null; then bad "secret-looking literal found"; else ok "no secret-looking literals"; fi
# shellcheck disable=SC2086
if grep -nEi '\b(claude|gpt|gemini|llama|opus|sonnet|haiku)[-a-z0-9.]*[0-9]' $sql_files >/dev/null; then bad "model identifier found in db files"; else ok "no model identifier strings in db files"; fi

say ""
say "RESULT: passed=$pass failed=$fail"
[ "$fail" -eq 0 ] && { say "DB CONSTRAINTS: PASSED"; exit 0; }
say "DB CONSTRAINTS: FAILED"; exit 1
