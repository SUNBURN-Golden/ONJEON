#!/usr/bin/env bash
# bootstrap-sample-build (T-CT-07): build and test a sample task in a clone that contains only the
# outputs of that task's declared dependencies (plus base files no tasks.json task produced).
#
#   phase A  clone ref -> peel every landed merge outside the task's declared-dependency
#            closure: the task, its transitive prereq_tasks, and the transitive producers of
#            the artifacts they declare in consumes (tasks.json is the source of truth)
#            -> cargo build + cargo test -p <crate>
#   phase B  clone ref -> drop exactly one landed non-prerequisite task's outputs -> same commands
#
# The test passes when both phases succeed, and the whole run is recorded under reports/.
# On failure an automatic diagnosis restores peeled merges inside the sample crate's
# dependency closure one trial build at a time and names the non-prerequisite task
# merges the keep set actually needs (prune.py diagnose).
#
#   bash tools/ci/bootstrap_sample/run.sh --task T-TW-01 [--ref origin/main] [--repo DIR] [--keep-tmp]
# Exit: 0 pass, 1 a phase failed or the clone could not be pruned, 2 usage.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK="" REF="" REPO="" KEEP_TMP=0
usage() { sed -n '2,15p' "${BASH_SOURCE[0]}"; exit "${1:-2}"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --task|--ref|--repo)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || usage 2
      case "$1" in
        --task) TASK="$2";;
        --ref) REF="$2";;
        --repo) REPO="$2";;
      esac
      shift 2;;
    --keep-tmp) KEEP_TMP=1; shift;;
    -h|--help) usage 0;;
    *) usage 2;;
  esac
done
[[ "$TASK" =~ ^T-[A-Z]{2}-[0-9]{2}$ ]] || usage 2

REPO="${REPO:-$(git -C "$HERE" rev-parse --show-toplevel)}"
REPO="$(cd "$REPO" && pwd)" || exit 2
TASKS_PATH="docs/blueprint/proposals/설계검토_결과/tasks.json"
if [[ -z "$REF" ]]; then
  for c in origin/main main HEAD; do
    if git -C "$REPO" rev-parse --verify --quiet "$c" >/dev/null; then REF="$c"; break; fi
  done
fi
SHA="$(git -C "$REPO" rev-parse --verify "$REF^{commit}")" || { echo "cannot resolve ref $REF"; exit 2; }
mkdir -p "$HERE/reports" || exit 1
LOG="$(mktemp "$HERE/reports/bootstrap-sample-build_${TASK}_${SHA:0:12}.XXXXXX.log")" || exit 1
TMP="$(mktemp -d "$HERE/.run.XXXXXX")" || exit 1
[[ $KEEP_TMP == 1 ]] || trap 'rm -rf "$TMP"' EXIT
exec > >(tee "$LOG") 2>&1
TASKS_JSON="$TMP/tasks.json"
git -C "$REPO" show "$SHA:$TASKS_PATH" > "$TASKS_JSON" || exit 1
CRATE="$(python3 -I "$HERE/prune.py" crate --task "$TASK" --tasks "$TASKS_JSON")" || exit 1
sha256sum "$HERE/run.sh" "$HERE/prune.py" "$TASKS_JSON"
rustc --version
cargo --version

echo "== bootstrap-sample-build =="
echo "task: $TASK   crate: $CRATE"
echo "repo: $REPO   ref: $REF ($SHA)"
echo "keep set (self + transitive prereq_tasks + declared consumes producers):"
python3 -I "$HERE/prune.py" keep --task "$TASK" --tasks "$TASKS_JSON" --repo "$REPO" --ref "$SHA" | sed 's/^/  /'
echo "tmp: $TMP  log: $LOG"
echo

phase() { # $1 = clone dir, $2 = extra prune args
  local dir="$1"; shift
  git clone --quiet --no-hardlinks --no-checkout "$REPO" "$dir" || return 1
  git -C "$dir" checkout --quiet --detach "$SHA" || return 1
  [[ -z "$(git -C "$dir" status --porcelain)" ]] || return 1
  python3 -I "$HERE/prune.py" prune --repo "$dir" --ref "$SHA" --task "$TASK" --tasks "$TASKS_JSON" "$@" || return 1
  (cd "$dir" && export CARGO_TARGET_DIR="$dir/target" &&
    echo "+ cargo build -p $CRATE" && cargo build -p "$CRATE" &&
    echo "+ cargo test -p $CRATE" && cargo test -p "$CRATE")
}

echo "== phase A: clean clone, prerequisites only =="
if phase "$TMP/pruned"; then A=PASS; else A=FAIL; fi
echo "phase A: $A"
echo

DROP="$(python3 -I "$HERE/prune.py" pick --task "$TASK" --repo "$REPO" --ref "$SHA" --tasks "$TASKS_JSON")" || { echo "bootstrap-sample-build: FAIL (pick failed)"; exit 1; }
echo "== phase B: drop one non-prerequisite output ($DROP), keep the rest =="
if phase "$TMP/single" --only "$DROP"; then B=PASS; else B=FAIL; fi
echo "phase B: $B"
echo

if [[ "$A" == FAIL ]]; then
  echo "== diagnosis: which peeled merges does the keep set actually need? =="
  python3 -I "$HERE/prune.py" diagnose --task "$TASK" --repo "$REPO" --ref "$SHA" \
    --tasks "$TASKS_JSON" --workdir "$TMP/diag" || echo "diagnosis: no peeled-merge set restores the build"
  echo
elif [[ "$B" == FAIL ]]; then
  echo "== diagnosis =="
  echo "$DROP was dropped alone and the build failed: $TASK depends on the outputs of a"
  echo "task outside its declared prerequisites. $DROP is an undeclared prerequisite."
  echo
fi

if [[ "$A" == PASS && "$B" == PASS ]]; then
  echo "bootstrap-sample-build: PASS ($TASK builds and tests on prerequisite outputs only; dropping $DROP changes nothing)"
  exit 0
fi
echo "bootstrap-sample-build: FAIL (phase A=$A, phase B=$B)"
exit 1
