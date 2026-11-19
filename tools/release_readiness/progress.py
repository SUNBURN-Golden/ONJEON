#!/usr/bin/env python3
"""Report P01–P19 progress as Markdown. Exit 0 for any progress, 2 for invalid inputs."""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import (BUNDLE, PURPOSE, ROOT, artifact_problem, inspect_item, read_contract,
                   read_json, read_manifest, require)


def read_merged(path, tasks):
    merges = read_json(path)
    require(isinstance(merges, dict), "merged inventory must map task IDs to commit SHAs")
    for task, commit in merges.items():
        require(task in tasks, f"unknown merged task: {task}")
        require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit),
                f"{task}: expected a full merge commit SHA")
    return set(merges)


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


def report(registry, purpose, merged_path, directory):
    tasks, rows, features = read_contract(registry, purpose)
    merged = read_merged(merged_path, tasks)
    manifest = read_manifest(directory, tasks, rows, features)
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
        closed = not pending and inspect_item(
            row, record, manifest["task_states"], directory)["status"] == "closed"
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
    parser.add_argument("--merged", type=Path, default=Path(__file__).with_name("merged_tasks.json"))
    parser.add_argument("--evidence", type=Path, default=ROOT / "docs/release-readiness/evidence")
    args = parser.parse_args(argv)
    try:
        print(report(args.registry, args.purpose, args.merged, args.evidence))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Cannot report product purpose progress: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
