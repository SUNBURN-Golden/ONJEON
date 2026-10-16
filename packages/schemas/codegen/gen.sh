#!/usr/bin/env bash
# Regenerate the vocabulary schema and the Rust / TypeScript / Dart contract types.
#   bash packages/schemas/codegen/gen.sh          # write
#   bash packages/schemas/codegen/gen.sh --check  # fail if stale (CI)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mode="--write"
[ "${1:-}" = "--check" ] && mode="--check"
exec python3 -I "$here/gen.py" "$mode"
