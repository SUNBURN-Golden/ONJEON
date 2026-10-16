#!/usr/bin/env bash
# Compatibility check of packages/schemas against a previous contracts tag (02_구현계약 §5).
#
#   bash packages/schemas/codegen/check_compat.sh contracts-0.1.0   # compare with that tag
#   bash packages/schemas/codegen/check_compat.sh --selftest         # prove the check fails on a deleted field
#
# 1. structural diff (compat.py): field/type/enum removal, newly required -> needs a new major
# 2. compile probe: the PREVIOUS tag's generated Rust types must still read minimal documents
#    built from the NEW schemas (a deleted or retyped field makes cargo run fail). Skipped when
#    step 1 found breaking changes and accepted them because the major version was raised.
# Exit: 0 compatible, 1 incompatible, 2 usage or setup error.
#
# With no `contracts-*` tag in the repository (first release) there is nothing to compare
# with: the run says so, runs the self-test, and exits 0. Once a tag exists, an
# unknown <prev_tag> is an error.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
schemas="$(cd "$here/.." && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$repo/target/compat-probe}"
compat() { python3 -I "$here/compat.py" "$@"; }

probe() { # probe <prev_dir> <new_dir> -> exit status of the probe run
  local out="$tmp/probe.$RANDOM"
  compat --probe "$out" --prev "$1" --new "$2" >/dev/null
  (cd "$out" && cargo run --quiet)
}

selftest() {
  echo "== self-test: a deleted field must fail the check"
  local mut="$tmp/mutant" log="$tmp/selftest.log"
  compat --make-mutant "$mut" --prev "$schemas" --drop Assertion.created_by_run
  if ! compat --prev "$schemas" --new "$schemas" >"$log" 2>&1; then
    cat "$log"; echo "self-test FAILED: identical schemas were reported incompatible"; return 1
  fi
  if compat --prev "$schemas" --new "$mut" >"$log" 2>&1; then
    cat "$log"; echo "self-test FAILED: deleting Assertion.created_by_run was not detected"; return 1
  fi
  grep -q "field removed: Assertion.created_by_run" "$log" || { cat "$log"; echo "self-test FAILED: wrong reason"; return 1; }
  echo "   structural diff: deleted field detected"
  if ! probe "$schemas" "$schemas" >"$log" 2>&1; then
    cat "$log"; echo "self-test FAILED: probe rejected identical schemas"; return 1
  fi
  grep -q "^ok   Assertion" "$log" || { cat "$log"; echo "self-test FAILED: probe did not read Assertion"; return 1; }
  if probe "$schemas" "$mut" >"$log" 2>&1; then
    cat "$log"; echo "self-test FAILED: compile probe accepted a document without Assertion.created_by_run"; return 1
  fi
  grep -q "FAIL Assertion: missing field .created_by_run." "$log" || { cat "$log"; echo "self-test FAILED: probe failed for another reason"; return 1; }
  echo "   compile probe: previous client cannot read documents without the deleted field"
  echo "self-test ok"
}

arg="${1:-}"
if [ -z "$arg" ]; then
  echo "usage: check_compat.sh <prev_tag> | --selftest" >&2
  exit 2
fi
if [ "$arg" = "--selftest" ]; then
  selftest
  exit $?
fi

if ! git -C "$repo" rev-parse --verify --quiet "refs/tags/$arg^{commit}" >/dev/null; then
  if [ -z "$(git -C "$repo" tag --list 'contracts-*')" ]; then
    if [ "${ONJ_REQUIRE_BASELINE:-0}" = "1" ]; then
      echo "error: no contracts-* tag found (shallow clone without tags?); ONJ_REQUIRE_BASELINE=1 forbids the first-release pass" >&2
      exit 2
    fi
    echo "BASELINE: no contracts-* tag exists yet (first release); nothing to compare with."
    selftest
    exit $?
  fi
  echo "error: tag '$arg' does not exist" >&2
  exit 2
fi

prev="$tmp/prev"
mkdir -p "$prev"
git -C "$repo" archive "$arg" packages/schemas/json packages/schemas/vocabulary.json packages/schemas/Cargo.toml \
  | tar -x -C "$prev" --strip-components=2 || { echo "error: $arg has no packages/schemas/json" >&2; exit 2; }

echo "== structural diff against $arg"
rc=0
compat --prev "$prev" --new "$schemas" | tee "$tmp/diff.log" || rc=${PIPESTATUS[0]}
[ "$rc" -eq 0 ] || exit "$rc"

if grep -q '^BREAKING' "$tmp/diff.log"; then
  echo "breaking changes are declared by a major version bump; the previous client is expected to break, probe skipped"
  echo "compatible with $arg (breaking, major bumped)"
  exit 0
fi

echo "== compile probe: $arg client reads documents built from the new schemas"
if ! probe "$prev" "$schemas"; then
  echo "INCOMPATIBLE: the previous generated client cannot read documents of the new schemas" >&2
  exit 1
fi
echo "compatible with $arg"
