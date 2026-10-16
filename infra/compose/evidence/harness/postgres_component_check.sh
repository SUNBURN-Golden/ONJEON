#!/bin/bash
# 실제 PostgreSQL 16으로 zone-init 흐름을 재현(이미지 안의 psql 경로만 시험용으로 바꿈)
set -u
P=/tmp/pgx/pixeltable_pgserver/pginstall/bin; export PATH=$P:$PATH
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../initdb" && pwd)"
B=/tmp/pgrun2; pkill -f "$B/" 2>/dev/null; rm -rf $B; mkdir -p $B
sed "s#/opt/onjeon/zone-init.psql#$SRC/zone-init.psql#" $SRC/10-zone.sh > $B/10-zone.sh
declare -A PORT=([public]=48741 [private]=48742) ADM=([public]=pub_admin [private]=prv_admin) APP=([public]=pub_app [private]=prv_app) DB=([public]=db_public [private]=db_private)
for z in public private; do
  echo -n "adminpw-$z" > $B/pw-$z
  initdb -D $B/$z -U ${ADM[$z]} --pwfile=$B/pw-$z --auth-host=scram-sha-256 --auth-local=trust --data-checksums >/dev/null 2>&1
  extra=""; [ $z = private ] && extra="-c log_statement=none -c log_min_duration_statement=-1 -c log_min_error_statement=panic -c log_error_verbosity=terse -c log_min_messages=log"
  pg_ctl -D $B/$z -o "-p ${PORT[$z]} -c unix_socket_directories=$B -c password_encryption=scram-sha-256 -c listen_addresses=127.0.0.1 $extra" -l $B/log-$z -w start >/dev/null
  psql -h $B -p ${PORT[$z]} -U ${ADM[$z]} -d postgres -qc "create database ${DB[$z]}"
  ( export PGHOST=$B PGPORT=${PORT[$z]} PGPASSWORD=adminpw-$z POSTGRES_USER=${ADM[$z]} POSTGRES_DB=${DB[$z]} APP_DB_USER=${APP[$z]} APP_DB_PASSWORD=apppw-$z ONJEON_ZONE=$z
    sh $B/10-zone.sh >/dev/null 2>$B/err-$z || { echo "INIT FAIL $z"; cat $B/err-$z; } )
done
fail=0
t(){ if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
n(){ if eval "$2" >/dev/null 2>&1; then echo "FAIL $1"; fail=1; else echo "ok   $1"; fi; }
ps_(){ PGPASSWORD="$3" psql -h 127.0.0.1 -p ${PORT[$1]} -U "$2" -d "$4" -v ON_ERROR_STOP=1 -tA -c "$5"; }
qsql="BEGIN; INSERT INTO queue.jobs (queue_name) VALUES ('smoke'); UPDATE queue.jobs SET state = 'running', locked_by = 'smoke', attempts = attempts + 1 WHERE id = (SELECT id FROM queue.jobs WHERE queue_name = 'smoke' AND state = 'ready' AND run_after <= now() ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1); ROLLBACK;"
for z in public private; do
  t "$z zone marker" "[ \"\$(ps_ $z ${APP[$z]} apppw-$z ${DB[$z]} \"SELECT current_setting('onjeon.zone')\")\" = $z ]"
  t "$z queue claim" "ps_ $z ${APP[$z]} apppw-$z ${DB[$z]} \"$qsql\" | grep -qx 'UPDATE 1'"
  n "$z app cannot create table" "ps_ $z ${APP[$z]} apppw-$z ${DB[$z]} 'CREATE TABLE public.probe (x int)'"
  n "$z app cannot reach postgres db" "ps_ $z ${APP[$z]} apppw-$z postgres 'SELECT 1'"
  n "$z app cannot reach template1" "ps_ $z ${APP[$z]} apppw-$z template1 'SELECT 1'"
  t "$z app not superuser" "[ \"\$(ps_ $z ${APP[$z]} apppw-$z ${DB[$z]} 'SELECT rolsuper FROM pg_roles WHERE rolname = current_user')\" = f ]"
  n "$z running without locked_by rejected" "ps_ $z ${APP[$z]} apppw-$z ${DB[$z]} \"INSERT INTO queue.jobs (queue_name,state) VALUES ('x','running')\""
  n "$z oversize payload rejected" "ps_ $z ${APP[$z]} apppw-$z ${DB[$z]} \"INSERT INTO queue.jobs (queue_name,payload) VALUES ('x', to_jsonb(repeat('a',9000)))\""
  n "$z bad queue name rejected" "ps_ $z ${APP[$z]} apppw-$z ${DB[$z]} \"INSERT INTO queue.jobs (queue_name) VALUES ('Bad Name')\""
done
o(){ [ $1 = public ] && echo private || echo public; }
for z in public private; do y=$(o $z)
  n "$z admin creds rejected by $y server" "ps_ $y ${ADM[$z]} adminpw-$z ${DB[$y]} 'SELECT 1'"
  n "$z app creds rejected by $y server"   "ps_ $y ${APP[$z]} apppw-$z ${DB[$y]} 'SELECT 1'"
done
n "app role cannot create role" "ps_ public ${APP[public]} apppw-public ${DB[public]} 'CREATE ROLE evil'"
n "wrong password" "ps_ public ${APP[public]} nope ${DB[public]} 'SELECT 1'"
echo "-- private log leak check (literal in statement should not be in log)"
ps_ private ${APP[private]} apppw-private ${DB[private]} "SELECT 'SECRET-LITERAL-XYZ'" >/dev/null
ps_ private ${APP[private]} apppw-private ${DB[private]} "SELECT 1/0" >/dev/null 2>&1
t "private log has no literal" "! grep -q SECRET-LITERAL $B/log-private"
t "private log has no failing statement" "! grep -q '1/0' $B/log-private"
ps_ private ${APP[private]} apppw-private ${DB[private]} "SELECT 'LEAKMARK-CAST'::int" >/dev/null 2>&1
ps_ private ${APP[private]} apppw-private ${DB[private]} "INSERT INTO queue.jobs (queue_name,state,payload) VALUES ('x','running','{\"k\":\"LEAKMARK-ROW\"}')" >/dev/null 2>&1
t "private log has no value quoted in error text" "! grep -q LEAKMARK $B/log-private"
for z in public private; do pg_ctl -D $B/$z -m fast stop >/dev/null; done
exit $fail
