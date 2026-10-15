#!/usr/bin/env bash
# Real executor verification (T-OP-09). Usage:
#   bash tools/daemon/runner_verify/run.sh --remote auto --report docs/vm_check/<date>/runner_verify.json [--scenario R1,R5] [--no-cli]
# --remote auto provisions a throwaway bare repository; a path must be a repository this tool created. Exit 1 on a failed check.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 -I "$HERE/cli.py" "$@"
