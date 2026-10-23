#!/usr/bin/env bash
# Disposable local PostgreSQL only. No production URL is accepted.
set -euo pipefail
cd "$(dirname "$0")/../.."
pgbin="${ONJEON_PG_BIN:-}"
if [ -z "$pgbin" ]; then
    for d in /usr/lib/postgresql/*/bin; do
        if [ -x "$d/initdb" ]; then pgbin="$d"; fi
    done
fi
if [ -z "$pgbin" ]; then
    echo 'NOT RUN: PostgreSQL initdb/pg_ctl are required' >&2
    exit 1
fi
cluster="$(mktemp -d /tmp/onjeon-kn04.XXXXXX)"
cleanup() {
    "$pgbin/pg_ctl" -D "$cluster/data" -m immediate stop >/dev/null 2>&1 || true
    rm -rf "$cluster"
}
trap cleanup EXIT
"$pgbin/initdb" -D "$cluster/data" -A trust -U postgres >/dev/null
"$pgbin/pg_ctl" -D "$cluster/data" -o "-c listen_addresses='' -k $cluster -c fsync=off" -l "$cluster/server.log" -w start >/dev/null
export PGHOST="$cluster" PGUSER=postgres PGDATABASE=knowledge_fixture_only
"$pgbin/createdb" "$PGDATABASE"
bash infra/db/public/apply.sh
"$pgbin/psql" -X -q -v ON_ERROR_STOP=1 --single-transaction -f services/knowledge/migrations/001_repository.sql
export ONJEON_KNOWLEDGE_TEST_DB="host=$cluster user=postgres dbname=$PGDATABASE"
echo "PostgreSQL: $("$pgbin/postgres" --version); disposable fixture_only database"
cargo test -p onjeon-knowledge -- --include-ignored --nocapture
