#!/usr/bin/env bash
# Compatibility check of packages/schemas against a previous contracts tag (02_구현계약 §5).
#
#   bash packages/schemas/codegen/check_compat.sh contracts-0.1.0   # compare with that tag
#   ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest  # CI
#   bash packages/schemas/codegen/check_compat.sh --selftest         # prove the check fails on a deleted field
#
# 1. structural diff (compat.py): field/type/enum removal, newly required -> needs a new major
# 2. compile probe: use the generated files committed at the tag to read or type-check
#    documents from the new schemas. Rust runs by default. ONJ_COMPAT_ALL_CLIENTS=1
#    also requires TypeScript and Dart. Declared major breaks skip the probes.
#    Each probe crate has its own name (probes share CARGO_TARGET_DIR, so a shared name would let two
#    concurrent runs execute each other's binary) and, when the repository has a Cargo.lock, that
#    lockfile pins serde (no fresh resolution; no registry access once the crates are cached).
# Exit: 0 compatible or first-release self-test passes, 1 incompatible, 2 usage or setup error.
#
# --latest requires full history and selects the highest version tag strictly before HEAD.
# When there is no baseline, run the self-test and report why a tagged check did not run.
# ONJ_REQUIRE_BASELINE=1 makes missing baselines a setup error.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
schemas="$(cd "$here/.." && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$repo/target/compat-probe}"
lock=()
[ -f "$repo/Cargo.lock" ] && lock=(--lock "$repo/Cargo.lock")
compat() { python3 -I "$here/compat.py" "$@"; }

# probe <prev_dir> <new_dir> [--all-clients]: 0 all requested probes pass,
# 1 a probe rejected the documents, 2 a setup error
probe() {
  local out rc=0
  out="$(mktemp -d "$tmp/probe.XXXXXX")" || return 2
  compat --probe "$out" --prev "$1" --new "$2" "${@:3}" ${lock[@]+"${lock[@]}"} >/dev/null || return 2
  (cd "$out" && cargo run --quiet) || rc=$?
  case "$rc" in
    0) ;;
    1) return 1 ;;
    *) echo "error: compile probe could not be built or run (cargo exit $rc)" >&2; return 2 ;;
  esac
  if [ "${3:-}" = "--all-clients" ]; then
    local tsc_cmd=(tsc)
    if [ -n "${TSC:-}" ]; then read -r -a tsc_cmd <<<"$TSC"; fi
    if ! command -v "${tsc_cmd[0]:-}" >/dev/null || ! command -v dart >/dev/null; then
      echo "error: the full tagged probe requires tsc and dart" >&2
      return 2
    fi
    echo "== TypeScript: type-check documents against the tagged client"
    "${tsc_cmd[@]}" -p "$out/ts/tsconfig.json" || return 1
    echo "== Dart: read documents with the tagged client"
    (cd "$out/dart" && dart pub get --offline) || return 2
    (cd "$out/dart" && dart analyze --fatal-infos --fatal-warnings lib bin && dart run bin/compat.dart "$out/docs") || return 1
  fi
}

selftest() {
  echo "== self-test: a deleted field must fail the check"
  local mut="$tmp/mutant" log="$tmp/selftest.log" rc
  compat --make-mutant "$mut" --prev "$schemas" --drop Assertion.created_by_run
  if ! compat --prev "$schemas" --new "$schemas" >"$log" 2>&1; then
    cat "$log"; echo "self-test FAILED: identical schemas were reported incompatible"; return 1
  fi
  if compat --prev "$schemas" --new "$mut" >"$log" 2>&1; then
    cat "$log"; echo "self-test FAILED: deleting Assertion.created_by_run was not detected"; return 1
  fi
  grep -q "field removed: Assertion.created_by_run" "$log" || { cat "$log"; echo "self-test FAILED: wrong reason"; return 1; }
  echo "   structural diff: deleted field detected"
  rc=0; probe "$schemas" "$schemas" >"$log" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    cat "$log"; echo "self-test FAILED: probe rejected identical schemas (exit $rc)"; return 1
  fi
  grep -q "^ok   Assertion" "$log" || { cat "$log"; echo "self-test FAILED: probe did not read Assertion"; return 1; }
  rc=0; probe "$schemas" "$mut" >"$log" 2>&1 || rc=$?
  if [ "$rc" -ne 1 ]; then
    cat "$log"; echo "self-test FAILED: compile probe did not reject a document without Assertion.created_by_run (exit $rc)"; return 1
  fi
  grep -q "FAIL Assertion: missing field .created_by_run." "$log" || { cat "$log"; echo "self-test FAILED: probe failed for another reason"; return 1; }
  echo "   compile probe: previous client cannot read documents without the deleted field"
  echo "self-test ok"
}

no_baseline() {
  if [ "${ONJ_REQUIRE_BASELINE:-0}" = "1" ]; then
    echo "error: $1; ONJ_REQUIRE_BASELINE=1 requires a previous release" >&2
    exit 2
  fi
  echo "BASELINE: $1; nothing to compare with."
  selftest
  exit $?
}

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo "usage: check_compat.sh <prev_tag> | --latest | --selftest" >&2
  exit 2
fi
tag="$1"
if [ "$tag" = "--selftest" ]; then
  selftest
  exit $?
fi

if [ "$tag" = "--latest" ]; then
  shallow="$(git -C "$repo" rev-parse --is-shallow-repository)" || exit 2
  if [ "$shallow" = "true" ]; then
    echo "error: --latest requires a full checkout with tags" >&2
    exit 2
  fi
  tags="$(git -C "$repo" tag --merged HEAD --no-contains HEAD --sort=-version:refname --list 'contracts-*')" || exit 2
  tag="${tags%%$'\n'*}"
  [ -n "$tag" ] || no_baseline "no previous contracts-* tag in HEAD history"
fi

if ! git check-ref-format "refs/tags/$tag"; then
  echo "error: invalid tag '$tag'" >&2
  exit 2
fi
if ! baseline="$(git -C "$repo" rev-parse --verify --quiet "refs/tags/$tag^{commit}")"; then
  tags="$(git -C "$repo" tag --list 'contracts-*')" || exit 2
  [ -n "$tags" ] || no_baseline "no contracts-* tag exists yet (first release)"
  echo "error: tag '$tag' does not exist or does not point to a commit" >&2
  exit 2
fi

prev="$tmp/prev"
mkdir -p "$prev"
paths=(packages/schemas/{json,vocabulary.json,Cargo.toml,src/generated})
clients=()
if [ "${ONJ_COMPAT_ALL_CLIENTS:-0}" = "1" ]; then
  paths+=(packages/schemas/codegen/generated/{ts,dart})
  clients=(--all-clients)
fi
if ! git -C "$repo" archive "$baseline" -- "${paths[@]}" | tar -x -C "$prev" --strip-components=2; then
  echo "error: $tag is missing required schema or generated client files" >&2
  exit 2
fi

echo "== structural diff against $tag ($baseline)"
rc=0
compat --prev "$prev" --new "$schemas" | tee "$tmp/diff.log" || rc=${PIPESTATUS[0]}
[ "$rc" -eq 0 ] || exit "$rc"

if grep -q '^BREAKING' "$tmp/diff.log"; then
  echo "breaking changes are declared by a major version bump; the previous client is expected to break, probe skipped"
  echo "compatible with $tag (breaking, major bumped)"
  exit 0
fi

echo "== compile probe: $tag client reads documents built from the new schemas"
rc=0; probe "$prev" "$schemas" ${clients[@]+"${clients[@]}"} || rc=$?
case "$rc" in
  0) ;;
  1) echo "INCOMPATIBLE: a previous generated client rejected documents of the new schemas" >&2; exit 1 ;;
  *) echo "error: the compile probe could not be prepared or built; fix the setup (see above), this is not a compatibility verdict" >&2; exit 2 ;;
esac
echo "compatible with $tag"
