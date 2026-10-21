#!/usr/bin/env bash
# sha256 of the packages/schemas tree WITHOUT codegen/evidence/ (and without Python caches).
# EVIDENCE.md records this value for the tree its logs were produced from; a different value here
# means the logs are stale and must be regenerated with the commands listed there.
#   bash packages/schemas/codegen/tree_hash.sh
set -euo pipefail
schemas="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo="$(git -C "$schemas" rev-parse --show-toplevel)"
cd "$repo"
find packages/schemas -type f -not -path 'packages/schemas/codegen/evidence/*' -not -path '*/__pycache__/*' -print0 \
  | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1
