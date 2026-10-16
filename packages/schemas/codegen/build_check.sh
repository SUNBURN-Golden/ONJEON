#!/usr/bin/env bash
# Build the three generated clients: Rust (cargo), TypeScript (tsc), Dart (dart analyze).
#
#   bash packages/schemas/codegen/build_check.sh           # a missing TypeScript/Dart toolchain is reported as SKIPPED
#   ONJ_REQUIRE_TOOLCHAINS=1 bash .../build_check.sh       # CI: a missing toolchain is a failure
#
# TSC="node /path/to/tsc.js" (or /path/to/tsc) selects the TypeScript compiler (default: tsc on PATH, then `npx --no-install tsc`).
# A SKIPPED language was NOT built; the summary line says so and exits 3 unless nothing is required.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
require="${ONJ_REQUIRE_TOOLCHAINS:-0}"
failed=0; skipped=0

echo "== generated files are up to date"
python3 -I "$here/gen.py" --check || failed=1

echo "== Rust: cargo build -p onjeon-contracts -p onjeon-api-types (default and --features skeleton)"
(cd "$repo" && cargo build -p onjeon-contracts --quiet) && echo "Rust: built" || { echo "Rust: FAILED"; failed=1; }
(cd "$repo" && cargo build -p onjeon-api-types --quiet && cargo build -p onjeon-api-types --features skeleton --quiet) \
  && echo "Rust API: built (default and skeleton feature)" || { echo "Rust API: FAILED"; failed=1; }

echo "== TypeScript: tsc --noEmit"
tsc_cmd=()
if [ -n "${TSC:-}" ]; then read -r -a tsc_cmd <<<"$TSC"
elif command -v tsc >/dev/null 2>&1; then tsc_cmd=(tsc)
elif command -v npx >/dev/null 2>&1 && (cd "$here" && npx --no-install tsc --version >/dev/null 2>&1); then tsc_cmd=(npx --no-install tsc)
fi
if [ "${#tsc_cmd[@]}" -eq 0 ]; then
  echo "TypeScript: SKIPPED (no tsc; set TSC='node /path/to/tsc.js')"; skipped=1
else
  ts_scratch="$(mktemp -d)"
  mkdir -p "$ts_scratch/ts" "$ts_scratch/ts-api"
  cp -R "$here/generated/ts/." "$ts_scratch/ts/"
  cp -R "$here/generated/ts-api/." "$ts_scratch/ts-api/"
  python3 -I "$here/ts_fixtures.py" "$ts_scratch/ts"   # every fixture as a typed constant + two expected type errors
  if "${tsc_cmd[@]}" -p "$ts_scratch/ts/tsconfig.json"; then echo "TypeScript: built, fixtures type-check (${tsc_cmd[*]} $("${tsc_cmd[@]}" --version))"
  else echo "TypeScript: FAILED"; failed=1; fi
  python3 -I "$here/ts_api_fixtures.py" "$ts_scratch/ts-api"   # API fixtures + release_id, enum and skeleton-export errors
  if "${tsc_cmd[@]}" -p "$ts_scratch/ts-api/tsconfig.json"; then echo "TypeScript API: built, fixtures type-check, skeleton not exported by index.ts"
  else echo "TypeScript API: FAILED"; failed=1; fi
  rm -rf "$ts_scratch"
fi

echo "== Dart: dart analyze + fixture round trip"
if command -v dart >/dev/null 2>&1; then
  scratch="$(mktemp -d)"
  cp -R "$here/generated/dart/." "$scratch/"   # pub writes .dart_tool/pubspec.lock; keep them out of the repo
  mkdir -p "$scratch/bin" && cp "$here/tests/dart_roundtrip.dart" "$scratch/bin/roundtrip.dart"
  if (cd "$scratch" && dart pub get --offline >/dev/null 2>&1; dart analyze --fatal-infos --fatal-warnings . && dart run bin/roundtrip.dart "$here/tests/fixtures"); then
    echo "Dart: analyzed and round-tripped ($(dart --version 2>&1))"
  else echo "Dart: FAILED"; failed=1; fi
  rm -rf "$scratch"
  api_scratch="$(mktemp -d)"
  mkdir -p "$api_scratch/dart" "$api_scratch/dart-api"
  cp -R "$here/generated/dart/." "$api_scratch/dart/"
  cp -R "$here/generated/dart-api/." "$api_scratch/dart-api/"
  mkdir -p "$api_scratch/dart-api/bin" && cp "$here/tests/dart_api_roundtrip.dart" "$api_scratch/dart-api/bin/api_roundtrip.dart"
  # a file that uses the skeleton through the default entry point must NOT analyze
  printf "import 'package:onjeon_api/onjeon_api.dart';\nvoid main() { print(skeletonOperations); }\n" > "$api_scratch/dart-api/bin/leak.dart"
  if (cd "$api_scratch/dart-api" && dart pub get --offline >/dev/null 2>&1; \
      dart analyze --fatal-infos --fatal-warnings lib bin/api_roundtrip.dart && dart run bin/api_roundtrip.dart "$here/tests/api_fixtures") \
     && ! (cd "$api_scratch/dart-api" && dart analyze bin/leak.dart >/dev/null 2>&1); then
    echo "Dart API: analyzed, round-tripped, skeleton not exported by onjeon_api.dart"
  else echo "Dart API: FAILED"; failed=1; fi
  rm -rf "$api_scratch"
else
  echo "Dart: SKIPPED (dart SDK not installed)"; skipped=1
fi

if [ "$failed" -ne 0 ]; then echo "RESULT: FAILED"; exit 1; fi
if [ "$skipped" -ne 0 ]; then
  echo "RESULT: incomplete - at least one language was skipped (see above)"
  [ "$require" = "1" ] && exit 1
  exit 3
fi
echo "RESULT: all three languages build"
