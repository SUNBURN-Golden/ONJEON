#!/usr/bin/env python3
"""Report product purpose progress as Markdown. Exit 0 for any progress, 2 for invalid inputs."""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import (BUNDLE, PURPOSE, ROOT, TASKS_STATE, artifact_problem, inspect_item,
                   read_contract, read_manifest, read_task_states, task_state_problems)


def has_task_evidence(directory):
    # Inspect regular files under the task's own directory without opening
    # potentially large or sensitive artifacts.
    if directory.is_symlink():
        return False
    for parent, _, files in os.walk(directory):
        for name in files:
            path = Path(parent) / name
            if not path.is_symlink() and path.is_file() and path.stat().st_size > 0:
                return True
    return False


def report(registry, purpose, tasks_state, directory):
    tasks, rows, features = read_contract(registry, purpose)
    states = read_task_states(tasks_state, tasks)
    merged = {task for task, record in states.items() if record["merge_sha"] is not None}
    manifest = read_manifest(directory, tasks, rows, features)
    problems = task_state_problems(rows.values(), states, directory)
    row_tasks = set().union(*(set(row["tasks"]) for row in rows.values()))
    task_evidence = {task for task in row_tasks if has_task_evidence(directory / task)}

    lines = [
        "| Purpose | Tasks merged | Tasks pending merge | Tasks with evidence files | Row evidence files present | Status |",
        "| --- | ---: | --- | ---: | ---: | --- |",
    ]
    closed_count = 0
    for row_id, row in sorted(rows.items()):
        linked = set(row["tasks"])
        pending = linked - merged
        record = manifest["rows"].get(row_id, {})
        references = record.get("evidence")
        references = references if isinstance(references, list) else []
        present = sum(artifact_problem(directory, reference) is None for reference in references)
        closed = inspect_item(row, record, problems, directory)["status"] == "closed"
        closed_count += closed
        lines.append(
            f"| {row_id} | {len(linked & merged)}/{len(linked)} | "
            f"{', '.join(sorted(pending)) or '—'} | {len(linked & task_evidence)}/{len(linked)} | "
            f"{present}/{len(references)} | {'Closed' if closed else 'Open'} |"
        )

    return "\n".join([
        "## Product purpose progress",
        "",
        f"Closed purpose rows **{closed_count}/{len(rows)}** · Merged tasks **{len(merged)}/{len(tasks)}**",
        "",
        *lines,
        "",
        "Task files show collection progress. Closed rows require recorded merges and pass the "
        "release evidence coverage check. T-OP-08 determines release readiness.",
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=BUNDLE / "tasks.json")
    parser.add_argument("--purpose", type=Path, default=PURPOSE)
    parser.add_argument("--tasks-state", type=Path, default=TASKS_STATE)
    parser.add_argument("--evidence", type=Path, default=ROOT / "docs/release-readiness/evidence")
    args = parser.parse_args(argv)
    try:
        print(report(args.registry, args.purpose, args.tasks_state, args.evidence))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Cannot report product purpose progress: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
